"""Spike 0.1: time the per-candidate permission check (AD-4). Throwaway.

For each spike user and item-count set it measures, cold and warm:

- AD-4 full check: candidates from `frappe.qb.get_query(ignore_permissions=False)`,
  then `frappe.get_doc` + `frappe.has_permission` per candidate
- shortcut: `has_permission` on a document built from the query row, no load
- preload (amendment option): parents and child tables loaded per batch of 100
  candidates, complete documents built in memory, then `has_permission`
- fill: what one DocWeave page costs, checking candidates until 100 pass or
  the scan budget (200 or 2,000) runs out
- `frappe.get_list` for the same page, in process
- REST over HTTP (the pass/fail target): `/api/resource` list plus one
  `GET /api/resource/Sales Order/<name>` per document, against gunicorn

"cold" means the site's Redis cache and the in-process caches are cleared before
the pass (for REST, gunicorn is also HUPed so its workers start fresh); "warm"
passes follow an unmeasured warm-up pass. MariaDB's buffer
pool is warm in both. Results go to spikes/results/ as JSON and Markdown tables.

Needs the fixtures (spikes/fixtures.py) and gunicorn (gthread) serving the bench on
--http (see the report's rerun section). Run from frappe-bench/sites:
    ../env/bin/python /workspaces/docweave/spikes/time_permission_check.py --site spike.localhost
"""

import argparse
import json
import os
import platform
import signal
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import frappe
import requests

sys.path.insert(0, str(Path(__file__).parent))
from fixtures import ITEM_SETS, PASSWORD, USERS  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"
PAGE = 100
HTTP_TIMEOUT = 60  # seconds; a stuck server fails the run instead of hanging it
REST_SERVER = "gunicorn 23.0.0, gthread, 2 workers x 4 threads, --preload"
SCAN_BUDGET = 2000
FILL_BUDGETS = (100, 150, 200, 300, 500, 2000)  # candidate budgets for filling one page of PAGE documents
FILL_TRIALS = (3, 10)  # (cold, warm)
GUNICORN_PID = Path("/home/vscode/frappe-bench/spike-gunicorn.pid")  # written by serve_rest.sh


def pct(values, p):
	if not values:
		return None
	values = sorted(values)
	k = (len(values) - 1) * p / 100
	lo, hi = int(k), min(int(k) + 1, len(values) - 1)
	return values[lo] + (values[hi] - values[lo]) * (k - lo)


def summary(values):
	return {"n": len(values), "p50": pct(values, 50), "p95": pct(values, 95), "mean": statistics.fmean(values) if values else None}


@contextmanager
def count_queries():
	"""Count frappe.db.sql calls, the IntegrationTestCase.assertQueryCount pattern."""
	box = [0]
	cls = frappe.db.__class__
	orig = cls.sql

	def counted(self, *args, **kwargs):
		box[0] += 1
		return orig(self, *args, **kwargs)

	cls.sql = counted
	try:
		yield box
	finally:
		cls.sql = orig


def new_request(site, user, cold):
	"""Start a fresh Frappe request context; cold also drops every cache layer."""
	if getattr(frappe.local, "site", None):
		frappe.destroy()
	frappe.init(site=site, sites_path=".")
	frappe.connect()
	if cold:
		frappe.clear_cache()
		if frappe.client_cache:
			frappe.client_cache.clear_cache()
		frappe.destroy()
		frappe.init(site=site, sites_path=".")
		frappe.connect()
	frappe.set_user(user)


def candidates(user, size, limit, fields):
	return frappe.qb.get_query(
		"Sales Order",
		fields=fields,
		filters={"po_no": f"spike-{size}"},
		order_by="name asc",
		limit=limit,
		ignore_permissions=False,
		ignore_user_permissions=False,
		user=user,
	).run(as_dict=True)


def full_check_pass(user, size, limit):
	t0 = time.perf_counter()
	rows = candidates(user, size, limit, ["name"])
	t_query = time.perf_counter() - t0
	per, allowed = [], {}
	with count_queries() as q:
		for row in rows:
			s = time.perf_counter()
			doc = frappe.get_doc("Sales Order", row.name)
			allowed[row.name] = bool(frappe.has_permission("Sales Order", "read", doc=doc, user=user))
			per.append((time.perf_counter() - s) * 1000)
	return {
		"query_ms": t_query * 1000,
		"total_ms": (time.perf_counter() - t0) * 1000,
		"per_ms": per,
		"queries": q[0],
		"candidates": len(rows),
		"allowed": allowed,
	}


def fill_pass(user, size, budget):
	"""What a DocWeave page costs: check candidates in order until PAGE are
	allowed or the budget is spent (a short page)."""
	t0 = time.perf_counter()
	rows = candidates(user, size, budget, ["name"])
	scanned = allowed = 0
	per = []
	with count_queries() as q:
		for row in rows:
			s = time.perf_counter()
			doc = frappe.get_doc("Sales Order", row.name)
			allowed += bool(frappe.has_permission("Sales Order", "read", doc=doc, user=user))
			per.append((time.perf_counter() - s) * 1000)
			scanned += 1
			if allowed == PAGE:
				break
	return {
		"total_ms": (time.perf_counter() - t0) * 1000,
		"per_ms": per,
		"queries": q[0],
		"scanned": scanned,
		"returned": allowed,
	}


def shortcut_pass(user, size, limit):
	t0 = time.perf_counter()
	rows = candidates(user, size, limit, ["*"])
	per, allowed = [], {}
	with count_queries() as q:
		for row in rows:
			s = time.perf_counter()
			doc = frappe.get_doc({**row, "doctype": "Sales Order"})
			allowed[row.name] = bool(frappe.has_permission("Sales Order", "read", doc=doc, user=user))
			per.append((time.perf_counter() - s) * 1000)
	return {"total_ms": (time.perf_counter() - t0) * 1000, "per_ms": per, "queries": q[0], "allowed": allowed}


def preload_pass(user, size, limit, batch=PAGE):
	"""Amendment option: load parents and every child table per batch of
	candidates, build complete documents, then has_permission on each. The
	documents match what get_doc loads, so parity should hold. per_ms is each
	candidate's share of its batch load plus its own check."""
	meta = frappe.get_meta("Sales Order")
	t0 = time.perf_counter()
	rows = candidates(user, size, limit, ["*"])
	per, allowed = [], {}
	with count_queries() as q:
		for start in range(0, len(rows), batch):
			chunk = rows[start : start + batch]
			names = [r.name for r in chunk]
			s = time.perf_counter()
			children = {n: {} for n in names}
			for tf in meta.get_table_fields():
				for child in frappe.db.get_all(
					tf.options,
					filters={"parent": ["in", names], "parenttype": "Sales Order", "parentfield": tf.fieldname},
					fields=["*"],
					order_by="idx asc",
				):
					children[child.parent].setdefault(tf.fieldname, []).append(child)
			share = (time.perf_counter() - s) * 1000 / len(chunk)
			for row in chunk:
				s = time.perf_counter()
				doc = frappe.get_doc({**row, **children[row.name], "doctype": "Sales Order"})
				allowed[row.name] = bool(frappe.has_permission("Sales Order", "read", doc=doc, user=user))
				per.append(share + (time.perf_counter() - s) * 1000)
	return {"total_ms": (time.perf_counter() - t0) * 1000, "per_ms": per, "queries": q[0], "allowed": allowed}


def get_list_pass(user, size, limit):
	t0 = time.perf_counter()
	rows = frappe.get_list(
		"Sales Order", filters={"po_no": f"spike-{size}"}, fields=["name"], order_by="name asc", limit=limit
	)
	return {"total_ms": (time.perf_counter() - t0) * 1000, "rows": len(rows)}


def run_trials(fn, site, user, size, limit, cold_trials, warm_trials):
	cold = []
	for _ in range(cold_trials):
		new_request(site, user, cold=True)
		cold.append(fn(user, size, limit))
	new_request(site, user, cold=False)
	fn(user, size, limit)  # warm-up, not measured
	warm = []
	for _ in range(warm_trials):
		new_request(site, user, cold=False)
		warm.append(fn(user, size, limit))
	return cold, warm


def aggregate(passes):
	per = [v for p in passes for v in p["per_ms"]]
	cands = sum(len(p["per_ms"]) for p in passes)
	out = {
		"per_candidate_ms": summary(per),
		"page_total_ms": summary([p["total_ms"] for p in passes]),
		"queries_per_candidate": (sum(p["queries"] for p in passes) / cands) if cands else None,
	}
	if "query_ms" in passes[0]:
		out["candidate_query_ms"] = summary([p["query_ms"] for p in passes])
		out["candidates"] = passes[0]["candidates"]
		out["allowed"] = sum(passes[0]["allowed"].values())
	return out


# --- REST over HTTP ----------------------------------------------------------


class Rest:
	def __init__(self, base, site, user):
		self.base = base
		self.s = requests.Session()
		self.s.headers["Host"] = site
		r = self.s.post(f"{base}/api/method/login", json={"usr": user, "pwd": PASSWORD}, timeout=HTTP_TIMEOUT)
		r.raise_for_status()

	def page(self, size, limit):
		t0 = time.perf_counter()
		r = self.s.get(
			f"{self.base}/api/resource/Sales Order",
			params={
				"filters": json.dumps([["po_no", "=", f"spike-{size}"]]),
				"fields": json.dumps(["name"]),
				"order_by": "name asc",
				"limit_page_length": limit,
			},
			timeout=HTTP_TIMEOUT,
		)
		r.raise_for_status()
		names = [d["name"] for d in r.json()["data"]]
		t_list = (time.perf_counter() - t0) * 1000
		per, allowed = [], {}
		for name in names:
			s = time.perf_counter()
			resp = self.s.get(f"{self.base}/api/resource/Sales Order/{name}", timeout=HTTP_TIMEOUT)
			per.append((time.perf_counter() - s) * 1000)
			if resp.status_code not in (200, 403):
				resp.raise_for_status()
			allowed[name] = resp.status_code == 200
		return {
			"list_ms": t_list,
			"total_ms": (time.perf_counter() - t0) * 1000,
			"per_ms": per,
			"queries": 0,
			"allowed": allowed,
			"names": names,
		}

	def ping_ms(self, n=50):
		out = []
		for _ in range(n):
			s = time.perf_counter()
			self.s.get(f"{self.base}/api/method/ping", timeout=HTTP_TIMEOUT).raise_for_status()
			out.append((time.perf_counter() - s) * 1000)
		return summary(out)


def restart_rest_workers(base, site):
	"""HUP gunicorn so it forks fresh workers: their in-process caches start cold."""
	os.kill(int(GUNICORN_PID.read_text().strip()), signal.SIGHUP)
	time.sleep(2)
	for _ in range(60):
		try:
			if requests.get(f"{base}/api/method/ping", headers={"Host": site}, timeout=5).ok:
				return
		except requests.RequestException:
			pass
		time.sleep(0.5)
	raise RuntimeError("gunicorn did not come back after HUP")


def rest_trials(base, site, user, size, limit, cold_trials, warm_trials):
	cold = []
	for _ in range(cold_trials):
		new_request(site, "Administrator", cold=True)  # flush Redis for the site
		restart_rest_workers(base, site)
		cold.append(Rest(base, site, user).page(size, limit))
	client = Rest(base, site, user)
	client.page(size, limit)  # warm-up
	warm = [client.page(size, limit) for _ in range(warm_trials)]
	return cold, warm


# --- Environment and output --------------------------------------------------


def git_tag(app):
	return subprocess.run(
		["git", "-C", f"../apps/{app}", "describe", "--tags"], capture_output=True, text=True
	).stdout.strip()


def environment(site):
	new_request(site, "Administrator", cold=False)
	cpu = next(
		(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), "unknown"
	)
	mem_kb = next(int(l.split()[1]) for l in open("/proc/meminfo") if l.startswith("MemTotal"))
	return {
		"frappe": git_tag("frappe"),
		"erpnext": git_tag("erpnext"),
		"mariadb": frappe.db.sql("select version()")[0][0],
		"redis": frappe.cache.info("server").get("redis_version"),
		"python": platform.python_version(),
		"cpu": cpu,
		"cores": os.cpu_count(),
		"ram_gb": round(mem_kb / 1024 / 1024, 1),
		"site": site,
		"date": time.strftime("%Y-%m-%d %H:%M %Z"),
	}


def fmt(v, digits=2):
	return "–" if v is None else f"{v:.{digits}f}"


def tables(res):
	ft = res.get("fill_trials", FILL_TRIALS)
	lines = []
	lines.append("### AD-4 full check (get_doc + has_permission) per candidate\n")
	lines.append(
		"| User | Items | Limit | Candidates | Allowed | Cache | p50 ms | p95 ms | Queries/candidate "
		"| Candidate query p95 ms | Page p95 ms |"
	)
	lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
	for r in res["full"]:
		for cache in ("cold", "warm"):
			a = r[cache]
			lines.append(
				f"| {r['user']} | {r['items']} | {r['limit']} | {a['candidates']} | {a['allowed']} | {cache} | "
				f"{fmt(a['per_candidate_ms']['p50'])} | {fmt(a['per_candidate_ms']['p95'])} | "
				f"{fmt(a['queries_per_candidate'], 1)} | {fmt(a['candidate_query_ms']['p95'], 1)} | "
				f"{fmt(a['page_total_ms']['p95'], 0)} |"
			)
	lines.append(f"\n### Target: 100-document page, p95 warm (ms, {res['trials'][str(PAGE)][1]} trials)\n")
	lines.append(
		"| User | Items | REST list + GETs | DocWeave check + 1 round trip | Ratio | get_list only "
		"| Shortcut page | Preload page | REST vs full: different names | REST vs full: allow/deny disagreements |"
	)
	lines.append("|---|---|---|---|---|---|---|---|---|---|")
	for c in res["comparison"]:
		lines.append(
			f"| {c['user']} | {c['items']} | {fmt(c['rest_p95'], 0)} | {fmt(c['docweave_p95'], 0)} | "
			f"{fmt(c['ratio'])} | {fmt(c['get_list_p95'], 1)} | {fmt(c['shortcut_p95'], 0)} | "
			f"{fmt(c['preload_p95'], 0)} | {c.get('rest_name_mismatch', '–')} | {c.get('rest_allow_disagreements', '–')} |"
		)
	lines.append("\n### REST per-document GET (ms)\n")
	lines.append("| User | Items | Cache | p50 | p95 | Page p95 |")
	lines.append("|---|---|---|---|---|---|")
	for r in res["rest"]:
		for cache in ("cold", "warm"):
			a = r[cache]
			lines.append(
				f"| {r['user']} | {r['items']} | {cache} | {fmt(a['per_candidate_ms']['p50'])} | "
				f"{fmt(a['per_candidate_ms']['p95'])} | {fmt(a['page_total_ms']['p95'], 0)} |"
			)
	lines.append("\n### Parity with the full check over the scan budget (2,000 candidates, warm)\n")
	lines.append(
		"| User | Items | Candidates | Full allowed | Shortcut allowed | Shortcut disagreements "
		"| Preload allowed | Preload disagreements | Full p50/p95 ms | Shortcut p50/p95 ms "
		"| Preload p50/p95 ms | Full scan ms | Preload scan ms | Full / preload queries per candidate |"
	)
	lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
	for p in res["parity"]:
		lines.append(
			f"| {p['user']} | {p['items']} | {p['candidates']} | {p['full_allowed']} | {p['shortcut_allowed']} | "
			f"{p['disagreements']} | {p['preload_allowed']} | {p['preload_disagreements']} | "
			f"{fmt(p['full_p50'])} / {fmt(p['full_p95'])} | {fmt(p['shortcut_p50'])} / {fmt(p['shortcut_p95'])} | "
			f"{fmt(p['preload_p50'])} / {fmt(p['preload_p95'])} | {fmt(p['full_scan_ms'], 0)} | "
			f"{fmt(p['preload_scan_ms'], 0)} | {fmt(p.get('full_queries_per_candidate'), 1)} / "
			f"{fmt(p['preload_queries_per_candidate'], 2)} |"
		)
	lines.append(
		f"\n### Filling one page of {PAGE} documents (cold {ft[0]} / warm {ft[1]} trials)\n"
	)
	lines.append(
		"| User | Items | Budget | Scanned | Returned | Short page | Warm p50 ms | Warm p95 ms | Cold p95 ms "
		"| REST page p95 ms | Warm p95 / REST |"
	)
	lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
	for f in res.get("fill", []):
		lines.append(
			f"| {f['user']} | {f['items']} | {f['budget']} | {f['scanned']} | {f['returned']} | "
			f"{'yes' if f['returned'] < PAGE else 'no'} | {fmt(f['warm_p50'], 0)} | {fmt(f['warm_p95'], 0)} | "
			f"{fmt(f['cold_p95'], 0)} | {fmt(f['rest_p95'], 0)} | {fmt(f['ratio'])} |"
		)
	if res.get("fill"):
		lines.extend(equal_readable_tables(res, ft))
	return "\n".join(lines) + "\n"


def equal_readable_tables(res, ft):
	"""Spike 0.2's target reading: time per readable document. REST's 100-row
	page holds denied documents too, so its cost per readable document is its
	page p95 divided by the documents on that page the full check allows."""
	readable = {(f["user"], f["items"]): f["warm"]["allowed"] for f in res["full"] if f["limit"] == PAGE}
	lines = [f"\n### Equal readable documents: warm p95 per document (fill: {ft[1]} warm trials; REST: {res['trials'][str(PAGE)][1]})\n"]
	lines.append(
		"| User | Items | Budget | REST readable per page | REST ms per readable doc | Returned "
		"| DocWeave ms per returned doc | Equal-readable ratio | Literal ratio (fill ÷ REST page) |"
	)
	lines.append("|---|---|---|---|---|---|---|---|---|")
	worst = {}
	for f in res["fill"]:
		rd = readable[(f["user"], f["items"])]
		rest_per, dw_per = f["rest_p95"] / rd, f["warm_p95"] / f["returned"]
		ratio = dw_per / rest_per
		if f["budget"] not in worst or ratio > worst[f["budget"]][0]:
			worst[f["budget"]] = (ratio, f["user"], f["items"])
		lines.append(
			f"| {f['user']} | {f['items']} | {f['budget']} | {rd} | {fmt(rest_per, 1)} | {f['returned']} | "
			f"{fmt(dw_per, 1)} | {fmt(ratio)} | {fmt(f['ratio'])} |"
		)
	lines.append("\n### Equal readable documents: worst case per budget\n")
	lines.append("| Budget | Worst equal-readable ratio | Where |")
	lines.append("|---|---|---|")
	for b in sorted(worst):
		v, u, i = worst[b]
		lines.append(f"| {b} | {fmt(v)} | {u}, {i} items |")
	return lines


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--site", default="spike.localhost")
	parser.add_argument("--http", default="http://127.0.0.1:8001", help="gunicorn serving the bench")
	parser.add_argument("--quick", action="store_true", help="few trials, for a smoke run")
	parser.add_argument("--resume", action="store_true", help="skip users already in the checkpoint")
	parser.add_argument("--out-suffix", default="", help="appended to the result file names, e.g. -0-2")
	parser.add_argument("--tables-from", help="regenerate the Markdown tables from a results JSON; no measuring")
	args = parser.parse_args()

	if args.tables_from:
		src = Path(args.tables_from)
		src.with_suffix(".md").write_text(tables(json.loads(src.read_text())))
		print(f"wrote {src.with_suffix('.md')}")
		return

	# (cold, warm) trials per page size
	trials = {PAGE: (5, 20), SCAN_BUDGET: (2, 3)}
	if args.quick:
		trials = {PAGE: (1, 2), SCAN_BUDGET: (1, 1)}

	RESULTS_DIR.mkdir(exist_ok=True)
	checkpoint = RESULTS_DIR / f"permission-check{args.out_suffix}.partial.json"
	if args.resume and checkpoint.exists():
		res = json.loads(checkpoint.read_text())
		ping = res["http_round_trip_ms"]
	else:
		res = {"env": environment(args.site), "trials": {str(k): v for k, v in trials.items()}, "full": [], "rest": [], "comparison": [], "parity": [], "fill": []}
		res["env"]["rest_server"] = REST_SERVER
		ping = Rest(args.http, args.site, USERS["unrestricted"]).ping_ms()
		res["http_round_trip_ms"] = ping
	res.setdefault("done_users", [])
	fill_trials = (1, 2) if args.quick else FILL_TRIALS
	res.setdefault("fill_trials", fill_trials)  # a resumed run keeps the counts it started with

	for key, user in USERS.items():
		if key in res["done_users"]:
			print(f"{key}: in checkpoint, skipped", flush=True)
			continue
		for size in ITEM_SETS:
			for limit in (PAGE, SCAN_BUDGET):
				ct, wt = trials[limit]
				print(f"{key} items={size} limit={limit}", flush=True)
				cold, warm = run_trials(full_check_pass, args.site, user, size, limit, ct, wt)
				res["full"].append(
					{"user": key, "items": size, "limit": limit, "cold": aggregate(cold), "warm": aggregate(warm)}
				)
				if limit == SCAN_BUDGET:
					_, sc = run_trials(shortcut_pass, args.site, user, size, limit, 0, 1)
					_, pl = run_trials(preload_pass, args.site, user, size, limit, 0, 1)
					full, short, pre = warm[0]["allowed"], sc[0]["allowed"], pl[0]["allowed"]
					full_per = [v for p in warm for v in p["per_ms"]]
					res["parity"].append(
						{
							"user": key,
							"items": size,
							"candidates": len(full),
							"full_allowed": sum(full.values()),
							"shortcut_allowed": sum(short.values()),
							"disagreements": sum(full[n] != short.get(n) for n in full),
							"preload_allowed": sum(pre.values()),
							"preload_disagreements": sum(full[n] != pre.get(n) for n in full),
							"full_p50": pct(full_per, 50),
							"full_p95": pct(full_per, 95),
							"shortcut_p50": pct(sc[0]["per_ms"], 50),
							"shortcut_p95": pct(sc[0]["per_ms"], 95),
							"preload_p50": pct(pl[0]["per_ms"], 50),
							"preload_p95": pct(pl[0]["per_ms"], 95),
							"preload_queries_per_candidate": pl[0]["queries"] / max(len(pre), 1),
							"full_queries_per_candidate": warm[0]["queries"] / max(len(full), 1),
							"full_scan_ms": statistics.fmean(p["total_ms"] for p in warm),
							"preload_scan_ms": pl[0]["total_ms"],
						}
					)

			rc, rw = rest_trials(args.http, args.site, user, size, PAGE, *trials[PAGE])
			res["rest"].append({"user": key, "items": size, "cold": aggregate(rc), "warm": aggregate(rw)})

			_, gl = run_trials(get_list_pass, args.site, user, size, PAGE, 0, trials[PAGE][1])
			_, sc = run_trials(shortcut_pass, args.site, user, size, PAGE, 0, trials[PAGE][1])
			_, pl = run_trials(preload_pass, args.site, user, size, PAGE, 0, trials[PAGE][1])
			full_warm = next(
				r for r in res["full"] if r["user"] == key and r["items"] == size and r["limit"] == PAGE
			)["warm"]
			rest_p95 = pct([p["total_ms"] for p in rw], 95)
			dw_p95 = full_warm["page_total_ms"]["p95"] + ping["p95"]
			# same data? REST list names vs get_query candidates, and allow/deny per name
			new_request(args.site, user, cold=False)
			full_page = full_check_pass(user, size, PAGE)
			rest_page = rw[0]
			name_mismatch = len(set(rest_page["names"]) ^ set(full_page["allowed"]))
			allow_dis = sum(
				rest_page["allowed"][n] != full_page["allowed"][n]
				for n in set(rest_page["allowed"]) & set(full_page["allowed"])
			)
			for budget in FILL_BUDGETS:
				fc, fw = run_trials(fill_pass, args.site, user, size, budget, *fill_trials)
				fwp95 = pct([p["total_ms"] for p in fw], 95) + ping["p95"]
				res["fill"].append(
					{
						"user": key,
						"items": size,
						"budget": budget,
						"scanned": fw[0]["scanned"],
						"returned": fw[0]["returned"],
						"warm_p50": pct([p["total_ms"] for p in fw], 50) + ping["p50"],
						"warm_p95": fwp95,
						"cold_p95": pct([p["total_ms"] for p in fc], 95) + ping["p95"],
						"rest_p95": rest_p95,
						"ratio": fwp95 / rest_p95,
					}
				)
			res["comparison"].append(
				{
					"user": key,
					"items": size,
					"rest_p95": rest_p95,
					"docweave_p95": dw_p95,
					"ratio": dw_p95 / rest_p95,
					"get_list_p95": pct([p["total_ms"] for p in gl], 95),
					"shortcut_p95": pct([p["total_ms"] for p in sc], 95),
					"preload_p95": pct([p["total_ms"] for p in pl], 95),
					"rest_name_mismatch": name_mismatch,
					"rest_allow_disagreements": allow_dis,
				}
			)
		res["done_users"].append(key)
		checkpoint.write_text(json.dumps(res, indent=1, default=str))
	frappe.destroy()

	(RESULTS_DIR / f"permission-check{args.out_suffix}.json").write_text(json.dumps(res, indent=1, default=str))
	# Spike 0.1's evidence is permission-check-tables.md; suffixed runs write permission-check<suffix>.md
	tables_name = f"permission-check{args.out_suffix}.md" if args.out_suffix else "permission-check-tables.md"
	(RESULTS_DIR / tables_name).write_text(tables(res))
	print(tables(res))
	print(json.dumps({"env": res["env"], "http_round_trip_ms": ping}, indent=1))
	checkpoint.unlink()


if __name__ == "__main__":
	main()
