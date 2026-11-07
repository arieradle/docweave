---
title: 'Installable app with CI and boundary guard'
type: 'feature'
created: '2026-11-01'
status: 'done'
baseline_commit: 'cd5c12665210c90e70229a728c76326a8c6e0bfe'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** No DocWeave app exists yet: there's nothing to install, no CI, and nothing that stops later stories from reading data outside `adapter/` and bypassing permissions (AD-1).

**Approach:** Make the repo root a Frappe v16 app in the `bench new-app` layout, with the spine's packages. Add `test_boundaries.py`, an AST allowlist checker for AD-1. Add a GitHub Actions workflow that runs the app's tests in the dev image against MariaDB 11.8 and Redis service containers.

## Boundaries & Constraints

**Always:**
- Pins: Frappe v16.53.0, ERPNext v16.52.1, `graphql-core~=3.3.0`, ruff 0.14.10, MariaDB 11.8, Python >=3.14.
- One install path, `scripts/install-app.sh`, used by both the codespace and CI. It is idempotent, and if `apps/docweave` exists and isn't its symlink, it stops instead of deleting anything.
- CI uses the image named in `.devcontainer/docker-compose.yml`, or the image built in the PR when the PR changes `.devcontainer/`. CI has no `bench init`, no `get-app`, no second image and no second set of pins. Actions are pinned to commit SHAs.
- The boundary rules are AD-1, word for word. The checker is an allowlist: any `frappe.*` name not listed for a file fails.
- A boundary failure names the file, line and dotted name.

**Decision (scope):** only Story 1.1's ACs. The three CI items in `deferred-work.md` become one future "devcontainer checks" story on `dev-image.yml`.
**Decision (dev install):** `devcontainer.json` runs `scripts/install-app.sh` after `post-create.sh`. `post-create.sh` isn't changed, so the dev image needs no new tag or digest.
**Decision (triggers):** CI runs on push to `main`, on `pull_request` and on `workflow_dispatch`. Pushes to PR branches are tested through `pull_request`.

**Never:**
- No endpoint, no DocWeave Settings DocType, and no modules from later stories (`core/types.py` and so on). Packages hold only `__init__.py`.
- Don't edit `.devcontainer/post-create.sh`, `Dockerfile`, `docker-compose.yml`, `dev-image.yml` or the architecture spine.
- Don't change GitHub settings. The README says which check to make required.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Allowed name | `frappe.get_meta("X")` in `schema/` | passes | N/A |
| Banned call | `frappe.get_all(...)` in `schema/builder.py` | fails: `docweave/schema/builder.py:<line>: frappe.get_all` banned | N/A |
| Aliases | `from frappe import get_all as ga`; `import frappe as f; f.db.sql()` | both fail as `frappe.get_all` / `frappe.db.sql` | N/A |
| Allowed in one file only | `frappe.db.rollback()` in `api.py` / in `execution/` | passes / fails (not allowed here) | N/A |
| Not listed | `frappe.qb` outside `adapter/` | fails (not on allowlist) | N/A |
| Dynamic access | `getattr(frappe, "get_all")`, `__import__`/`importlib.import_module`, `from frappe import *`, bare `x = frappe` | fails (dynamic access refused) | N/A |
| Adapter rules | banned name in `adapter/`; `get_doc`/`has_permission` outside `adapter/permission.py`; `get_single` other than `("DocWeave Settings")` or outside `adapter/settings.py` | fails | N/A |
| Real package | the whole `docweave/` package | passes | N/A |
| Install rerun | `install-app.sh` run twice | second run changes nothing | stops if `apps/docweave` is a foreign directory |

</frozen-after-approval>

## Code Map

- `.devcontainer/post-create.sh` -- read only. The image stage already writes `db_host=mariadb`, `redis_cache` and `redis_queue` into the image's `common_site_config.json`, so CI needs service hostnames `mariadb`, `redis-cache` and `redis-queue`. Reuse its `new-site` flags (`--mariadb-user-host-login-scope=%`, root password `123`).
- `.devcontainer/docker-compose.yml` -- the source of the image reference. MariaDB command flags: utf8mb4 / utf8mb4_unicode_ci.
- `.github/workflows/dev-image.yml` -- copy its SHA pins (checkout v4.2.2, setup-buildx v3.11.1, build-push v6.18.0), its PR diff check and its compose `sed` (line 69). The image is public (Story 0.4), so no GHCR login is needed.
- `~/frappe-bench/apps/frappe/frappe/utils/boilerplate.py` -- the `bench new-app` templates: pyproject (flit_core, dynamic version), hooks, patches, the `modules.txt` module folder with `.frappe`, the pre-commit config and the ruff config.
- `~/frappe-bench/apps/frappe/frappe/testing/discovery.py` -- walks the whole app for `test_*.py`. Inline the boundary fixtures as strings so the walker doesn't pick them up.
- Frappe's own CI sets `character_set_server` and `collation_server` with `SET GLOBAL`, because GitHub service containers can't take `command:` flags.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `.pre-commit-config.yaml` -- `bench new-app` template. Depends on `graphql-core~=3.3.0`. Frappe's ruff config. Pre-commit hooks (pre-commit-hooks v6.0.0, ruff v0.14.10) limited to `^docweave/` and the two config files. No prettier.
- [x] `docweave/__init__.py` (`__version__ = "0.0.1"`), `hooks.py` (only the metadata block: app_name, title "DocWeave", publisher, description, email `arieradle@gmail.com`, license mit), `patches.txt`, `modules.txt` (`DocWeave`), `docweave/docweave/{__init__.py,.frappe}`, `core/`, `schema/`, `execution/`, `adapter/`, `tests/` (each an `__init__.py` with a one-line docstring), `api.py` (docstring only) -- the spine's package layout.
- [x] `docweave/tests/test_boundaries.py` -- the AD-1 checker plus `UnitTestCase` tests. It scans the real package and the matrix cases as inline sources -- NFR-1 gate.
- [x] `scripts/install-app.sh [SITE]` -- symlink `apps/docweave` to the repo (derived from the script's path), `env/bin/pip install -e`, add `docweave` to `sites/apps.txt` if missing, and `install-app` on the site if it isn't installed yet. Idempotent.
- [x] `scripts/ci-test.sh` -- runs inside the image: wait for MariaDB, `SET GLOBAL` charset, `new-site` (`$DOCWEAVE_CI_SITE`, default `test`) with ERPNext, `install-app.sh`, `allow_tests`, `run-tests --app docweave`.
- [x] `.github/workflows/ci.yml` -- job `tests`. Services `mariadb` (11.8, healthcheck, root password 123), `redis-cache` and `redis-queue` (`redis:7-alpine`). Steps: checkout; pick the image (compose reference, or build `docweave-dev:pr` with the gha cache when the PR diff touches `^\.devcontainer/`); `chmod -R a+rwX` the workspace; `docker run --rm --user vscode --network ${{ job.services.mariadb.network }} -v $GITHUB_WORKSPACE:/workspaces/docweave` running `ci-test.sh`; `pipx run pre-commit==4.3.0 run --all-files`. Timeout 60 minutes. Cancel superseded PR runs.
- [x] `.devcontainer/devcontainer.json` -- append `&& bash scripts/install-app.sh` to `onCreateCommand` and `postCreateCommand`.
- [x] `README.md` -- a "DocWeave app" section: install, run tests, pre-commit, the AD-1 rule, CI, and adding `tests` as a required check.
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- mark the three CI items as grouped into the future "devcontainer checks" story on `dev-image.yml`.

**Acceptance Criteria:**
- Given this codespace, when `install-app.sh dev.localhost` runs, then `bench --site dev.localhost list-apps` shows docweave, and `run-tests --app docweave` passes.
- Given a fresh site, when `bench get-app <repo>` and `install-app docweave` run, then the app installs (checked once by hand, then the symlink is restored).
- Given a PR, when CI runs, then `tests` passes on the compose image, or on the PR-built image if `.devcontainer/` changed.

## Design Notes

- Name resolution: track aliases from `import`/`from` statements, then take the longest pure `Attribute` chain rooted in a frappe alias. Prefix match: `frappe.local.request.method` matches `frappe.local.request`, and `frappe.cache.get_value(...)` matches `frappe.cache` (in v16 `frappe.cache` is an attribute, not a function). The banned list is checked first. `from frappe import x` counts as using `frappe.x` on the import line.
- Scope: every `docweave/**/*.py` except `docweave/tests/`. Test fixtures need Frappe freely, and test code is not a production data path. Per-file paths are relative to the inner package.
- Known effect on 1.2: the Settings DocType controller will import `frappe.model.document.Document`, which AD-1 doesn't list. 1.2 must settle that (a spine change through correct-course), not 1.1.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.
- `bash scripts/install-app.sh dev.localhost` run twice -- expected: the second run reports nothing to do.
- Throwaway check: `DOCWEAVE_CI_SITE=ci-check.localhost bash scripts/ci-test.sh`, then `bench drop-site ci-check.localhost --db-root-password 123 --force` -- expected: green.
- `uvx pre-commit==4.3.0 run --all-files` -- expected: passes.
- Temporarily add `frappe.get_all("User")` to `docweave/schema/__init__.py` -- expected: the boundary test fails, naming the file, line and call. Then revert.

## Implementation Notes

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Route | Evidence |
|---|---------|---------|-------|----------|
| 1 | `from frappe import utils` container-import branch untested | medium | patch | Added `test_container_import_allowed_only_for_allowed_children`; 13 tests pass. |
| 2 | `list-apps \| grep -q` under pipefail may SIGPIPE, breaking idempotency | low | patch | Real race; now captured to a variable first. Rerun prints "Nothing to do". |
| 3 | `trailing-whitespace` exclude regex unanchored (`.*md`, `.*csv`) | low | patch | Anchored to file extensions. |
| 4 | Pre-commit step skipped when tests fail | low | patch | Added `if: ${{ !cancelled() }}`. |
| 5 | `install-app.sh` refusal and rerun paths have no automated test | medium | defer | Verified by hand (second run "Nothing to do"); automating needs a bench fixture. Deferred. |
| 6 | Adapter is denylist inside `adapter/` (qb, local.db, sql_ddl pass) | false | rejected | Matches AD-1 and the matrix, which only bans names in `adapter/`; widening BANNED is a spine change. |
| 7 | `getattr(frappe.db, ...)`, `d = frappe.db` aliasing | low | rejected | Fix adds a scope-aware checker; not met in everyday use. |
| 8 | `f = frappe.get_single` bare reference bypasses literal check | low | rejected | Adapter-only file, one reviewer-visible line; fix adds branches. |
| 9 | Aliased `import_module as im` bypass | low | rejected | Outside matrix; fix adds complexity. |
| 10 | Module-wide alias collection, shadowing | low | rejected | Fails loudly (false positive), no silent miss. |
| 11 | `scan_package` aborts on SyntaxError / could pass vacuously | low | rejected | `check-ast` hook and import catch syntax errors; vacuity unlikely. |
| 12 | `uvx pre-commit==4.3.0` invalid syntax | false | rejected | The command ran and passed here. |
| 13 | `hooks.py` allowlist entry meaningless / widens hooks | false | rejected | AD-1 verbatim. |
| 14 | CI adds new pins (mariadb:11.8, redis:7-alpine) | false | rejected | Pins mandated by the spec. |
| 15 | No Redis healthcheck; compose `sed` brittle; hardcoded passwords; fork cache; chmod/safe.directory | low | rejected | Matches dev image's own conventions; MariaDB wait outlasts Redis start; fixes add complexity. |
| 16 | No install smoke test | false | rejected | `ci-test.sh` installs on a fresh site and `install-app` failure aborts it. |
| 17 | pyproject/ruff/README/flit/LICENSE/modules.txt newline nits | false | rejected | bench new-app boilerplate; LICENSE exists. |
| 18 | Devcontainer site missing skips install silently | low | rejected | `post-create.sh` creates the site first. |
