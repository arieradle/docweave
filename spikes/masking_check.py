"""Spike 0.3: observe Frappe v16 masking at runtime and time it (AD-5). Throwaway.

Runs each row of the spec's matrix as the masked user (Stock User, no unmask)
and records the raw values and Python types Frappe returns, then times the
masking overhead. Results go to spikes/results/masking-0-3.{json,md}.

Needs the fixtures (spikes/fixtures.py, which adds the masking setup). Run from
frappe-bench/sites:
    ../env/bin/python /workspaces/docweave/spikes/masking_check.py --site spike.localhost
"""

import argparse
import datetime
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

import frappe

sys.path.insert(0, str(Path(__file__).parent))
from fixtures import MASK_USER, UNMASK_ROLE, UNMASKED_USER, mask_customer_name, order_name  # noqa: E402

RESULTS_DIR = Path(__file__).parent / "results"
PARENT_FIELDS = ["name", "tax_id", "spike_credit", "spike_since", "spike_score", "spike_phone", "spike_email", "spike_note"]
CHILD_FIELDS = ["name", "parent", "item_name", "rate", "qty"]
ONE_CUSTOMER = mask_customer_name(1)
ONE_ORDER = order_name(5, 1)
MASK_LIKE = "Spike Mask Customer %"
TRIALS = 30


def new_request(site, user):
	if getattr(frappe.local, "site", None):
		frappe.destroy()
	frappe.init(site=site, sites_path=".")
	frappe.connect()
	frappe.set_user(user)


def show(v):
	"""A value and its Python type, as JSON. Dates keep their type; lists recurse."""
	if isinstance(v, (datetime.date, datetime.datetime, datetime.time, datetime.timedelta)):
		return {"value": str(v), "type": type(v).__name__}
	if isinstance(v, list):
		return {"value": typed_rows(v), "type": "list"}
	if isinstance(v, (int, float, str, type(None))):
		return {"value": v, "type": type(v).__name__}
	return {"value": str(v), "type": type(v).__name__}


def attempt(fn):
	"""Run fn; return its result or the exception it raised, as data."""
	try:
		return {"ok": True, "result": fn()}
	except Exception as e:
		frappe.db.rollback()
		return {"ok": False, "exception": type(e).__name__, "message": str(e)[:200]}


def customer_query(user, fields=PARENT_FIELDS, ignore_permissions=False, **run):
	return (
		frappe.qb.get_query(
			"Customer", fields=fields, filters={"name": ONE_CUSTOMER},
			ignore_permissions=ignore_permissions, user=user,
		).run(**run)
	)  # fmt: skip


def typed_rows(rows):
	if rows and isinstance(rows[0], dict):
		return [{k: show(v) for k, v in r.items()} for r in rows]
	return [[show(v) for v in r] if isinstance(r, (list, tuple)) else show(r) for r in rows]


def fresh_masked(doctype, user, parenttype=None):
	"""AD-5's fresh computation: masked fields from the user's current roles."""
	meta = frappe.get_meta(doctype)
	levels = set(meta.get_permlevel_access("mask", parenttype, user=user))
	return sorted(df.fieldname for df in meta.fields if df.get("mask") and df.permlevel not in levels)


def cached_masked(doctype, parenttype=None):
	return sorted(df.fieldname for df in frappe.get_meta(doctype).get_masked_fields(parenttype=parenttype))


# --- Matrix scenarios -------------------------------------------------------


def scenario_parent(site):
	new_request(site, MASK_USER)
	out = {
		"as_dict": attempt(lambda: typed_rows(customer_query(MASK_USER, as_dict=True))),
		"as_list": attempt(lambda: typed_rows(customer_query(MASK_USER, as_list=True))),
		"pluck_credit": attempt(lambda: typed_rows(customer_query(MASK_USER, fields=["spike_credit"], pluck=True))),
		"get_list": attempt(
			lambda: typed_rows(frappe.get_list("Customer", filters={"name": ONE_CUSTOMER}, fields=PARENT_FIELDS))
		),
		"get_doc_as_dict": attempt(
			lambda: {k: show(v) for k, v in frappe.get_doc("Customer", ONE_CUSTOMER).as_dict().items() if k in PARENT_FIELDS}
		),
		"get_doc_fieldlevel": attempt(lambda: doc_with_fieldlevel_read()),
	}
	new_request(site, "Administrator")
	out["raw"] = typed_rows(customer_query("Administrator", ignore_permissions=True, as_dict=True))
	return out


def doc_with_fieldlevel_read():
	"""What Frappe's document endpoints (client.get, form load, /api/v2) do."""
	doc = frappe.get_doc("Customer", ONE_CUSTOMER)
	doc.apply_fieldlevel_read_permissions()
	return {k: show(v) for k, v in doc.as_dict().items() if k in PARENT_FIELDS + ["spike_secret"]}


def scenario_hidden_data(site):
	"""Can a masked user learn real values through filters, sorting or aggregates?"""
	new_request(site, MASK_USER)

	def q(**kw):
		return frappe.qb.get_query("Customer", ignore_permissions=False, user=MASK_USER, **kw).run(as_dict=True)

	return {
		"filter_equals_real_tax_id": attempt(lambda: typed_rows(q(fields=["name"], filters={"tax_id": "TAX-000001"}))),
		"filter_credit_gt_49000": attempt(
			lambda: len(q(fields=["name"], filters={"name": ["like", MASK_LIKE], "spike_credit": [">", 49000]}))
		),
		"order_by_credit_desc_top3": attempt(
			lambda: typed_rows(q(fields=["name", "spike_credit"], filters={"name": ["like", MASK_LIKE]}, order_by="spike_credit desc", limit=3))
		),
		"sum_credit": attempt(lambda: typed_rows(q(fields=[{"SUM": "spike_credit", "as": "total"}], filters={"name": ["like", MASK_LIKE]}))),
		"max_since": attempt(lambda: typed_rows(q(fields=[{"MAX": "spike_since", "as": "latest"}], filters={"name": ["like", MASK_LIKE]}))),
		"get_list_filter_real_tax_id": attempt(
			lambda: typed_rows(frappe.get_list("Customer", filters={"tax_id": "TAX-000001"}, fields=["name"]))
		),
		"filter_on_level1_field": attempt(lambda: typed_rows(q(fields=["name"], filters={"spike_secret": "secret 1"}))),
		"real_count_credit_gt_49000": None,  # filled in as Administrator below
	}


def scenario_child(site):
	new_request(site, MASK_USER)

	def child(parent_doctype):
		return typed_rows(
			frappe.qb.get_query(
				"Sales Order Item", fields=CHILD_FIELDS, filters={"parent": ONE_ORDER}, limit=2,
				parent_doctype=parent_doctype, ignore_permissions=False, user=MASK_USER,
			).run(as_dict=True)
		)  # fmt: skip

	def nested():
		return typed_rows(
			frappe.qb.get_query(
				"Sales Order", fields=["name", {"items": ["item_name", "rate", "qty"]}], filters={"name": ONE_ORDER},
				ignore_permissions=False, user=MASK_USER,
			).run(as_dict=True)
		)  # fmt: skip

	return {
		"with_parent_doctype": attempt(lambda: child("Sales Order")),
		"without_parent_doctype": attempt(lambda: child(None)),
		"nested_child_fields": attempt(nested),
		"cached_masked_child": cached_masked("Sales Order Item", "Sales Order"),
		"fresh_masked_child": fresh_masked("Sales Order Item", MASK_USER, "Sales Order"),
		"cached_masked_child_no_parent": cached_masked("Sales Order Item"),
	}


def scenario_ignore_permissions(site):
	new_request(site, MASK_USER)
	return {
		"parent": attempt(lambda: typed_rows(customer_query(MASK_USER, ignore_permissions=True, as_dict=True))),
		"child": attempt(
			lambda: typed_rows(
				frappe.qb.get_query(
					"Sales Order Item", fields=CHILD_FIELDS, filters={"parent": ONE_ORDER}, limit=2,
					parent_doctype="Sales Order", ignore_permissions=True,
				).run(as_dict=True)
			)  # fmt: skip
		),
	}


def scenario_session_user_mismatch(site):
	"""Masking follows the session user or get_query(user=)? Three pairings."""
	out = {}
	for session, arg in (("Administrator", MASK_USER), (UNMASKED_USER, MASK_USER), (MASK_USER, UNMASKED_USER)):
		new_request(site, session)
		out[f"session={session} user={arg}"] = attempt(
			lambda: typed_rows(customer_query(arg, fields=["name", "tax_id", "spike_secret"], as_dict=True))
		)
	new_request(site, "Administrator")
	out["fresh_masked for Administrator"] = fresh_masked("Customer", "Administrator")
	out["get_masked_fields for Administrator"] = cached_masked("Customer")
	return out


def role_state(site, step):
	new_request(site, MASK_USER)
	key = f"masked_fields::Customer::::{MASK_USER}"
	return {
		"step": step,
		"roles_have_unmask": UNMASK_ROLE in frappe.get_roles(MASK_USER),
		"redis_key_present": bool(frappe.cache.exists(key)),  # exists() applies make_key itself
		"redis_ttl_s": frappe.cache.ttl(frappe.cache.make_key(key)),  # -1: no expiry, -2: absent
		"cached_masked": cached_masked("Customer"),
		"fresh_masked": fresh_masked("Customer", MASK_USER),
		"query_tax_id": customer_query(MASK_USER, fields=["tax_id"], pluck=True)[0],
		"child_cached_masked": cached_masked("Sales Order Item", "Sales Order"),
		"child_fresh_masked": fresh_masked("Sales Order Item", MASK_USER, "Sales Order"),
		"child_query_rate": frappe.qb.get_query(
			"Sales Order Item", fields=["rate"], filters={"parent": ONE_ORDER}, limit=1,
			parent_doctype="Sales Order", ignore_permissions=False, user=MASK_USER,
		).run(pluck=True)[0],
	}


def set_unmask(site, on):
	new_request(site, "Administrator")
	user = frappe.get_doc("User", MASK_USER)
	user.add_roles(UNMASK_ROLE) if on else user.remove_roles(UNMASK_ROLE)
	frappe.db.commit()


def scenario_role_change(site):
	new_request(site, "Administrator")
	frappe.clear_cache()
	set_unmask(site, False)
	steps = [role_state(site, "start: no unmask role, caches cleared")]
	set_unmask(site, True)
	steps.append(role_state(site, "unmask role granted, no cache clear"))
	set_unmask(site, False)
	steps.append(role_state(site, "unmask role revoked, no cache clear"))
	new_request(site, "Administrator")
	frappe.clear_cache(user=MASK_USER)
	steps.append(role_state(site, "after frappe.clear_cache(user=...)"))
	new_request(site, "Administrator")
	frappe.clear_cache()
	steps.append(role_state(site, "after frappe.clear_cache()"))
	# Granted state cached, then revoked: does the unmasked view stick?
	set_unmask(site, True)
	new_request(site, "Administrator")
	frappe.clear_cache()
	steps.append(role_state(site, "granted, caches cleared, cache warmed"))
	set_unmask(site, False)
	steps.append(role_state(site, "then revoked, no cache clear"))
	steps.append(role_state(site, "still revoked, next request"))
	new_request(site, "Administrator")
	frappe.clear_cache(user=MASK_USER)
	steps.append(role_state(site, "revoked, after frappe.clear_cache(user=...)"))
	new_request(site, "Administrator")
	frappe.clear_cache(doctype="Sales Order")
	steps.append(role_state(site, "revoked, after frappe.clear_cache(doctype='Sales Order')"))
	new_request(site, "Administrator")
	frappe.clear_cache(doctype="Customer")
	steps.append(role_state(site, "revoked, after frappe.clear_cache(doctype='Customer')"))
	new_request(site, "Administrator")
	frappe.clear_cache()
	steps.append(role_state(site, "revoked, after frappe.clear_cache()"))
	return steps


def scenario_permlevel(site):
	new_request(site, MASK_USER)
	return {
		"query_with_level1_field": attempt(
			lambda: typed_rows(customer_query(MASK_USER, fields=["name", "spike_note", "spike_secret"], as_dict=True))
		),
		"only_level1_field": attempt(
			lambda: typed_rows(customer_query(MASK_USER, fields=["spike_secret"], as_dict=True))
		),
		"get_list_with_level1_field": attempt(
			lambda: typed_rows(
				frappe.get_list("Customer", filters={"name": ONE_CUSTOMER}, fields=["name", "spike_note", "spike_secret"])
			)
		),
	}


# --- Timing ----------------------------------------------------------------


def pct(values, p):
	values = sorted(values)
	k = (len(values) - 1) * p / 100
	lo, hi = int(k), min(int(k) + 1, len(values) - 1)
	return values[lo] + (values[hi] - values[lo]) * (k - lo)


def summary(values):
	return {"n": len(values), "p50": pct(values, 50), "p95": pct(values, 95), "mean": statistics.fmean(values)}


def time_masking(site):
	"""Same query, same user, with Frappe's masking on and patched off: the
	difference is masking's cost. Also the cached and fresh masked-set lookups."""
	from frappe.model.meta import Meta

	fields = PARENT_FIELDS[:-1]
	out = {}
	for limit in (100, 200, 2000):

		def run():
			return frappe.qb.get_query(
				"Customer", fields=fields, filters={"name": ["like", MASK_LIKE]}, order_by="name asc",
				limit=limit, ignore_permissions=False, user=MASK_USER,
			).run(as_dict=True)  # fmt: skip

		new_request(site, MASK_USER)
		run()  # warm-up
		on, off = [], []
		orig = Meta.get_masked_fields
		for _ in range(TRIALS):
			s = time.perf_counter()
			rows = run()
			on.append((time.perf_counter() - s) * 1000)
			Meta.get_masked_fields = lambda self, parenttype=None: []
			try:
				s = time.perf_counter()
				off_rows = run()
				off.append((time.perf_counter() - s) * 1000)
			finally:
				Meta.get_masked_fields = orig
		assert rows[0]["tax_id"] == "XXXXXXXX", "masking did not apply during timing"
		assert off_rows[0]["tax_id"].startswith("TAX-"), "masking was not switched off in the comparison run"
		diffs = [a - b for a, b in zip(on, off)]  # on and off alternate, so pair them per trial
		out[f"query_{limit}"] = {
			"masked": summary(on),
			"unmasked": summary(off),
			"overhead_paired": summary(diffs),
			"overhead_pct_p50": 100 * (pct(on, 50) - pct(off, 50)) / pct(off, 50),
			"rows": len(rows),
		}

	new_request(site, MASK_USER)
	frappe.get_meta("Customer").get_masked_fields()
	warm, cold, fresh = [], [], []
	key = frappe.cache.make_key(f"masked_fields::Customer::::{MASK_USER}")
	for _ in range(TRIALS * 10):
		s = time.perf_counter()
		frappe.get_meta("Customer").get_masked_fields()
		warm.append((time.perf_counter() - s) * 1000)
		s = time.perf_counter()
		fresh_masked("Customer", MASK_USER)
		fresh.append((time.perf_counter() - s) * 1000)
	for _ in range(TRIALS):
		frappe.cache.delete(key)
		frappe.local.cache = {}  # the RedisWrapper's per-request local cache
		s = time.perf_counter()
		frappe.get_meta("Customer").get_masked_fields()
		cold.append((time.perf_counter() - s) * 1000)
	# First call of a request: no per-request local cache, so Redis is hit.
	first_cached, first_fresh = [], []
	for _ in range(TRIALS):
		new_request(site, MASK_USER)
		s = time.perf_counter()
		frappe.get_meta("Customer").get_masked_fields()
		first_cached.append((time.perf_counter() - s) * 1000)
		new_request(site, MASK_USER)
		s = time.perf_counter()
		fresh_masked("Customer", MASK_USER)
		first_fresh.append((time.perf_counter() - s) * 1000)
	out["get_masked_fields_cached"] = summary(warm)
	out["get_masked_fields_cache_miss"] = summary(cold)
	out["fresh_masked_set"] = summary(fresh)
	out["get_masked_fields_first_call_of_request"] = summary(first_cached)
	out["fresh_masked_set_first_call_of_request"] = summary(first_fresh)
	return out


# --- Output ----------------------------------------------------------------


def environment(site):
	new_request(site, "Administrator")
	tag = lambda app: subprocess.run(  # noqa: E731
		["git", "-C", f"../apps/{app}", "describe", "--tags"], capture_output=True, text=True
	).stdout.strip()
	return {
		"frappe": tag("frappe"),
		"erpnext": tag("erpnext"),
		"mariadb": frappe.db.sql("select version()")[0][0],
		"redis": frappe.cache.info("server").get("redis_version"),
		"python": platform.python_version(),
		"cpu": next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), "unknown"),
		"cores": os.cpu_count(),
		"ram_gb": round(next(int(l.split()[1]) for l in open("/proc/meminfo") if l.startswith("MemTotal")) / 1024 / 1024, 1),
		"date": time.strftime("%Y-%m-%d %H:%M %Z"),
		"site": site,
	}


def block(v):
	return "```json\n" + json.dumps(v, indent=1) + "\n```\n"


def cell(v):
	if isinstance(v, dict) and "type" in v:
		return f"`{v['value']!r}` ({v['type']})"
	return f"`{v!r}`"


def md(res):
	L = [f"# Masking observations ({res['env']['frappe']}, ERPNext {res['env']['erpnext']}, {res['env']['date']})\n"]
	p = res["parent"]
	L.append("## Parent fields, as the masked user\n")
	L.append("| Field | Raw value | `get_query` as_dict | `get_query` as_list | `get_list` | `get_doc().as_dict()` |")
	L.append("|---|---|---|---|---|---|")
	for i, f in enumerate(PARENT_FIELDS):
		def at(key, pick):
			r = p[key]
			return f"error: {r['exception']}" if not r["ok"] else cell(pick(r["result"]))
		L.append(
			f"| {f} | {cell(p['raw'][0][f])} | {at('as_dict', lambda r: r[0][f])} | {at('as_list', lambda r: r[0][i])} | "
			f"{at('get_list', lambda r: r[0][f])} | {at('get_doc_as_dict', lambda r: r.get(f, {'value': '(absent)', 'type': '-'}))} |"
		)
	L.append(f"\n`pluck` on `spike_credit`: {json.dumps(p['pluck_credit'])}\n")
	c = res["child"]
	L.append("`get_doc` then `apply_fieldlevel_read_permissions()` (what Frappe's document endpoints do):\n")
	L.append(block(p["get_doc_fieldlevel"]))
	L.append("## Filters, sorting and aggregates on masked fields\n")
	L.append(block(res["hidden_data"]))
	L.append("## Child rows (Sales Order Item, masked `item_name` and `rate`)\n")
	L.append(block(c))
	L.append("## `ignore_permissions=True`\n")
	L.append(block(res["ignore_permissions"]))
	L.append("## Session user and `get_query(user=)`\n")
	L.append(block(res["session_mismatch"]))
	L.append("## Unmask role granted and revoked without clearing caches\n")
	L.append(
		"| Step | Role held | Redis key present | Key TTL (s) | `get_masked_fields` | Fresh computation | Query `tax_id` "
		"| Child cached / fresh | Child query `rate` |"
	)
	L.append("|---|---|---|---|---|---|---|---|---|")
	for s in res["role_change"]:
		L.append(
			f"| {s['step']} | {s['roles_have_unmask']} | {s['redis_key_present']} | {s['redis_ttl_s']} | {len(s['cached_masked'])} fields | "
			f"{len(s['fresh_masked'])} fields | `{s['query_tax_id']}` | {len(s['child_cached_masked'])} / "
			f"{len(s['child_fresh_masked'])} | `{s['child_query_rate']}` |"
		)
	L.append("\n## Field above the user's permlevel\n")
	L.append(block(res["permlevel"]))
	t = res["timing"]
	L.append(f"\n## Timing (ms; {TRIALS} trials per query, {TRIALS * 10} per in-request lookup, {TRIALS} per first call)\n")
	L.append("| Measure | p50 | p95 | Paired overhead p50 | Paired overhead p95 | Overhead % (p50) |")
	L.append("|---|---|---|---|---|---|")
	for limit in (100, 200, 2000):
		q = t[f"query_{limit}"]
		L.append(
			f"| Query {q['rows']} rows, masking on | {q['masked']['p50']:.2f} | {q['masked']['p95']:.2f} | "
			f"{q['overhead_paired']['p50']:.2f} | {q['overhead_paired']['p95']:.2f} | {q['overhead_pct_p50']:.0f}% |"
		)
		L.append(f"| Query {q['rows']} rows, masking patched off | {q['unmasked']['p50']:.2f} | {q['unmasked']['p95']:.2f} | | | |")
	for k in (
		"get_masked_fields_cached", "get_masked_fields_cache_miss", "get_masked_fields_first_call_of_request",
		"fresh_masked_set", "fresh_masked_set_first_call_of_request",
	):  # fmt: skip
		L.append(f"| {k} | {t[k]['p50']:.3f} | {t[k]['p95']:.3f} | | | |")
	return "\n".join(L) + "\n"


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--site", default="spike.localhost")
	args = parser.parse_args()
	res = {"env": environment(args.site)}
	for name, fn in (
		("parent", scenario_parent),
		("child", scenario_child),
		("hidden_data", scenario_hidden_data),
		("ignore_permissions", scenario_ignore_permissions),
		("session_mismatch", scenario_session_user_mismatch),
		("role_change", scenario_role_change),
		("permlevel", scenario_permlevel),
		("timing", time_masking),
	):
		print(name, flush=True)
		res[name] = fn(args.site)
	new_request(args.site, "Administrator")
	res["hidden_data"]["real_count_credit_gt_49000"] = frappe.db.count(
		"Customer", {"name": ["like", MASK_LIKE], "spike_credit": [">", 49000]}
	)
	frappe.destroy()
	RESULTS_DIR.mkdir(exist_ok=True)
	(RESULTS_DIR / "masking-0-3.json").write_text(json.dumps(res, indent=1, default=str))
	(RESULTS_DIR / "masking-0-3.md").write_text(md(res))
	print(md(res))


if __name__ == "__main__":
	main()
