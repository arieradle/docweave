---
title: 'Development environment with Frappe v16 and ERPNext'
type: 'chore'
created: '2026-10-24'
status: 'in-review'
baseline_commit: 'a3be8a4c1198ff8d755ef6cf639fcab2e33f60c7'
route: 'dispatch'
review_loop_iteration: 1
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-0-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The devcontainer has Python 3.14 and Node 24 but no MariaDB, Redis or bench, so nothing Frappe-based can run: not the spikes, not any later story.

**Approach:** Turn the devcontainer into a Docker Compose setup with MariaDB 11.8 and Redis services, and have its setup script install uv, frappe-bench, a Frappe v16.53.0 bench with ERPNext v16.52.1, and a site `dev.localhost`. The bench and databases live in volumes, so rebuilds don't reinstall them.

**Decision:** ERPNext stays (user decision, 2026-10-24). It provides Sales Order, Customer and realistic permission hooks.

## Boundaries & Constraints

**Always:**
- Pin exact versions: Frappe tag v16.53.0, ERPNext tag v16.52.1, frappe-bench 5.31.0, MariaDB 11.8.
- Keep the existing Claude Code feature, Python 3.14, Node 24 and the rtk install.
- Make setup idempotent: rerunning it on an existing bench skips what is already done.
- Development credentials only (MariaDB root and Administrator passwords are fixed dev values, documented as such).

**Never:**
- Commit the bench, sites or database files to the repository.
- Use `latest` or unpinned image or app versions (Redis is pinned to a major version).
- Install the DocWeave app here. Story 1.1 does that.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First build | Fresh clone | Services up; bench, ERPNext and `dev.localhost` installed | Setup fails loudly with the failing step named |
| Rebuild | Existing volumes | Setup detects the bench and site and skips reinstall | N/A |
| Database not ready yet | MariaDB still starting | Setup waits (bounded) before `new-site` | Times out with a clear message |
| Reset | Volumes removed | Next build installs everything again | N/A |

</frozen-after-approval>

## Code Map

- `.devcontainer/devcontainer.json` -- switch from `image` to `dockerComposeFile` + `service`; keep features, `remoteEnv` PATH, `postCreateCommand`; forward ports 8000 (web) and 9000 (socketio).
- `.devcontainer/post-create.sh` -- existing rtk install; extend with system packages, uv, bench, ERPNext and site setup.
- `.devcontainer/docker-compose.yml` -- new. Pattern to follow: `frappe/frappe_docker` `devcontainer-example/docker-compose.yml` (MariaDB 11.8 with utf8mb4 server flags, separate `redis-cache` and `redis-queue`).
- `.gitignore` -- add any local bench or site paths, in case they end up inside the workspace.
- `README.md` -- add a Development environment section.
- Frappe v16.53.0 requires Python `>=3.14,<3.15` and Node `>=24`. It pins both PyMySQL and `mysqlclient==2.2.7`; mysqlclient has no Python 3.14 wheel, so install `libmariadb-dev`, `pkg-config` and `build-essential`, plus `mariadb-client` for bench's console and backup commands.
- Out of scope here: fast start for brand-new codespaces (prebuilt image plus Codespaces prebuilds) is Story 0.3.

## Tasks & Acceptance

**Execution:**
- [x] `.devcontainer/docker-compose.yml` -- define `app` (current base image pinned by digest, workspace mounted, `sleep infinity`), `mariadb` (11.8, utf8mb4 flags, root password, volume), `redis-cache` and `redis-queue` (pinned major), and a named volume for the bench at `/home/vscode/frappe-bench` -- the services and persistence
- [x] `.devcontainer/devcontainer.json` -- point at the Compose file and the `app` service, keep features and settings, forward 8000 and 9000 -- open in Compose mode
- [x] `.devcontainer/post-create.sh` -- install `mariadb-client`, `redis-tools` and the mysqlclient build deps; install uv via its official installer and `frappe-bench==5.31.0` with `uv tool install`; wait until MariaDB accepts the root login (a real query, since `mariadb-admin ping` succeeds even with a wrong password) and both Redis services answer PING, printing the last error on timeout; if no bench exists, `bench init --frappe-branch v16.53.0` with Redis pointed at the two services, then `bench get-app erpnext --branch v16.52.1`; if no `dev.localhost` site exists, create it against the `mariadb` host and install ERPNext; enable `developer_mode` and set `host_name` to `http://localhost:8000` for the site; keep the rtk steps -- idempotent setup (see Design Notes for the safety rules)
- [x] `README.md` -- document opening the container, the site URL and dev logins, `bench start`, rebuild, reset (removing volumes), how to rerun `bash .devcontainer/post-create.sh` after a failed setup, and what to do on a version mismatch -- usability
- [x] `.gitignore` -- ignore local bench and site artifacts if any land in the workspace, scoped to bench paths (no repo-wide `*.sql`) -- keep the repo clean

**Acceptance Criteria:**
- Given a fresh clone, when the devcontainer finishes setup, then `bench --version` reports 5.31.0, and `bench --site dev.localhost list-apps` shows frappe 16.53.0 and erpnext 16.52.1.
- Given the running bench, when `bench start` runs and I open `http://localhost:8000` as Administrator, then the desk loads and a Sales Order opens.
- Given an existing environment, when the container is rebuilt, then setup completes without reinstalling the bench or site.

## Implementation Notes

- Loop 1 rework: setup also completes ERPNext's setup wizard non-interactively (company DocWeave Dev, DWD, United States, USD), because acceptance criterion 2 needs a Company before a Sales Order can open. Skipped when `frappe.is_setup_complete` is true.

- Correction to the Code Map: Frappe v16.53.0 pins `mysqlclient==2.2.7` as well as PyMySQL. mysqlclient has no Python 3.14 wheel and builds from source, so setup also installs `libmariadb-dev`, `pkg-config` and `build-essential`.
- uv is pinned to 0.13.5 (official installer, versioned URL). Redis images are `redis:7-alpine`.
- Setup writes the sentinel file `~/frappe-bench/.docweave-bench-ready` once `bench init` finishes. If it is missing, the bench volume is emptied and initialised again. ERPNext is refetched if it is not in `sites/apps.txt`. If the site exists but `list-apps` fails, `new-site --force` recreates it.
- Bench is initialised with `--skip-redis-config-generation` (so the Procfile has no local redis-server entries) and `--no-backups`. `dev.localhost` is set as the default site so that `localhost:8000` serves it.

## Spec Change Log

- **Loop 1 (review of first implementation).** Triggering findings: destructive recovery (`new-site --force` on a transient failure; wiping the bench volume when the sentinel is missing), version bumps silently ignored, the bench venv bound to the floating base image's Python, no Redis readiness, MariaDB wait that passes on a wrong password, developer mode off, repo-wide `*.sql` ignore. Amended: Code Map, Tasks, Design Notes. Known-bad state avoided: a rebuild that destroys the dev site or bench, or keeps stale versions while claiming the pinned ones. KEEP: the Compose layout modelled on frappe_docker (MariaDB 11.8 with utf8mb4 flags and healthcheck, separate `redis-cache`/`redis-queue` on `redis:7-alpine`, named volumes); pinned versions as constants at the top of the script; named steps with an ERR trap that prints the failing step; uv 0.13.5 via versioned installer URL and `uv tool install frappe-bench==5.31.0`; `bench init --skip-redis-config-generation --no-backups </dev/null`; `set-config -g` for `db_host`, `redis_cache`, `redis_queue`; `new-site --mariadb-user-host-login-scope=%`; `bench use dev.localhost`; README sections for services, logins, rebuild and reset.

## Review Triage Log

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | `new-site --force` runs when `site_healthy` fails transiently, dropping the dev site | high | Any non-zero `list-apps` (Redis or DB hiccup) on an existing site takes the `--force` branch | bad_spec |
| 2 | Missing sentinel wipes a working bench volume with `find -delete` | medium | Recovery keys only on the marker; a deleted marker destroys apps and sites | bad_spec |
| 3 | Frappe/ERPNext tag bumps ignored on an existing bench | medium | Skip checks test existence, not the checked-out tag | bad_spec |
| 4 | Bench venv bound to base image's `/usr/bin/python3.14`; floating tag can break it on rebuild | medium | Verified: `env/bin/python` resolves to `/usr/bin/python3.14`; base image is `:ubuntu` | bad_spec |
| 5 | No wait for Redis services before `new-site`/`list-apps` | medium | Compose waits only for `service_started` on Redis | bad_spec |
| 6 | MariaDB wait passes on wrong password | low | Verified: `mariadb-admin ping` exits 0 with a wrong password | bad_spec (same task) |
| 7 | Wait loop hides the last error on timeout | low | Output sent to /dev/null | bad_spec (same task) |
| 8 | `developer_mode` not enabled | medium | Story 1.1 creates DocTypes, which needs developer mode | bad_spec |
| 9 | Floating image tags (base, redis patch, features) | low | Base image is `:ubuntu`; spec allowed it, now pinned by digest | bad_spec |
| 10 | Repo-wide `*.sql` ignore hides future fixtures | low | Pattern is unanchored | bad_spec (same task) |
| 11 | README lacks recovery instructions | low | Says the log names the step, not how to retry | bad_spec (same task) |
| 12 | `redis_socketio` set though deprecated | low | Harmless in v16; dropped in rework only if unused | patch-in-rework |
| 13 | `grep '^erpnext[[:space:]]'` misses installed ERPNext | false | Verified: `list-apps` always prints a version column | rejected |
| 14 | wkhtmltopdf and fonts missing | low | PDF printing not needed by DocWeave; fix is not a direct correction | rejected |
| 15 | README doesn't explain installing DocWeave | low | Out of scope by intent (Never: install DocWeave); Story 1.1 does it | rejected |
| 16 | Rebuild/recovery paths have no automated test | medium | Verification-gap layer (pre-verified): no CI or shell test harness exists | defer |
| 17 | Spec claim "if no bench exists" vs marker-based wipe | low | Same root cause as #2 | grouped with #2 |

## Design Notes

Safety rules for reruns:
- **Never destroy on doubt.** If the site exists, never run `new-site --force`; if `list-apps` fails, retry after the service waits, then stop with a message. If the bench volume has no sentinel but contains `apps/frappe` and `sites/apps.txt`, adopt it (write the sentinel) instead of wiping. Only a volume without those is emptied.
- **Detect version drift.** Compare `git -C apps/frappe describe --tags` and the same for ERPNext with the pinned tags. On mismatch, stop with a message telling the user to reset the volumes (README).
- **Self-heal the venv.** If `env/bin/python -c 'import frappe'` fails, run `bench setup env` (and `bench setup requirements`) rather than reinitialising the bench.

## Verification

**Commands:**
- `bench --version` -- expected: 5.31.0
- `cd ~/frappe-bench && bench --site dev.localhost list-apps` -- expected: frappe 16.53.0 and erpnext 16.52.1
- `cd ~/frappe-bench && bench --site dev.localhost doctor` -- expected: no errors
- `bash -n .devcontainer/post-create.sh` -- expected: no syntax errors

**Manual checks (if no CLI):**
- After `bench start`, the desk loads at `http://localhost:8000` and a Sales Order opens.
- Rebuild the container once and confirm setup skips the reinstall.
