# Currency / Reality-Check Review: DocWeave Architecture Spine

- Reviewer lens: are committed decisions checked against live sources rather than asserted from training data?
- Date: 2026-10-24
- Spine: `../ARCHITECTURE-SPINE.md`
- Sources checked live: `raw.githubusercontent.com/frappe/frappe/version-16/...` (`__version__ = "16.53.0"`), GitHub releases API, PyPI JSON API, `frappe/erpnext@version-16`, `frappe/frappe_docker@main`, docs.frappe.io.

## Verdict

**Mostly verified, with 3 substantive corrections.** Nearly every API, signature and version in the spine checks out against the live v16 source and PyPI. The problems are: (1) the doc_events-only `schema_revision` bump misses metadata changes that Frappe makes with raw `frappe.db.delete`; (2) the built-in Frappe MCP is no longer an open PR, it ships in `version-16`; (3) the endpoint is not restricted to POST, so a mutation sent as GET would skip CSRF checks and be silently rolled back. Several pins are very fresh or unpinned and should be tightened.

## Summary table

| # | Claim | Status | Severity |
|---|---|---|---|
| 1 | Python 3.14 (`requires-python >=3.14,<3.15`) | Verified | - |
| 2 | Frappe v16, "latest 16.x" | Verified (v16.53.0); unpinned | Low |
| 3 | graphql-core 3.3.0 | Verified; breaking changes vs 3.2 not acknowledged | Medium |
| 4 | `frappe.qb.get_query(user=, parent_doctype=, ignore_permissions=, ignore_user_permissions=)` | Verified | - |
| 5 | qb applies masking when `ignore_permissions=False` | Verified | - |
| 6 | `meta.get_masked_fields(parenttype=)` | Verified; semantics caveat | Low |
| 7 | `mask` permission type | Partly wrong wording | Low |
| 8 | `frappe.has_permission(doctype, "read", doc, user)` | Verified | - |
| 9 | `IntegrationTestCase` in v16 | Verified | - |
| 10 | `POST /api/method/docweave.api.graphql`, `allow_guest=False` | Path verified; POST not enforced | **High** |
| 11 | `frappe.cache` API, bump "after commit" | Verified | - |
| 12 | doc_events on DocType / Custom Field / Property Setter catch every schema change | **Wrong (incomplete)** | **High** |
| 13 | `flit_core` in the `bench new-app` template | Verified | - |
| 14 | ERPNext v16 exists | Verified (16.52.1) | - |
| 15 | MariaDB "Frappe v16 supported version" | Unpinned; actual range is 10.6 to 11.8 | Low |
| 16 | Redis "Frappe v16 supported version" | Unpinned; no official minimum found | Low |
| 17 | ruff 0.17.2 | Verified; 2 days old; Frappe itself uses 0.14.10 | Low |
| 18 | frappe-bench 5.31.1 | Verified; 1 day old | Low |
| 19 | Official Frappe MCP is "PR #44431, revisit after v1" | **Out of date** | **Medium** |
| 20 | `bench run-tests --app docweave` | Verified | - |
| 21 | Deferred: built-in child query as a mechanism | Verified caveat | Low |

## Detailed findings

### 1. Python 3.14
- **Claim:** Python 3.14, matching Frappe v16's `requires-python >=3.14,<3.15`.
- **Status:** Verified. The Frappe `pyproject.toml` has `requires-python = ">=3.14,<3.15"` and ruff `target-version = "py314"`. The `bench new-app` boilerplate writes `requires-python = ">=3.14"`. ERPNext v16 also needs `>=3.14`.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/pyproject.toml ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/utils/boilerplate.py
- **Fix:** None. Optionally match Frappe's upper bound (`<3.15`) in DocWeave's `pyproject.toml`.
- **Severity:** -

### 2. Frappe v16, "latest 16.x release"
- **Claim:** `version-16` branch, latest 16.x.
- **Status:** Verified. The latest is v16.53.0, released 2026-10-22, and `frappe/__init__.py` on `version-16` says `16.53.0`. The research addendum cites v16.32.0, which is now about 20 releases behind.
- **Evidence:** https://api.github.com/repos/frappe/frappe/releases ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/__init__.py
- **Fix:** Pin a floor in `[tool.bench.frappe-dependencies]`, for example `frappe = ">=16.53.0,<17.0.0"`. ERPNext uses the same mechanism. Masking in `frappe.qb` and the built-in MCP are recent, fast-moving code, so the floor matters. Record the release `test_masking.py` was validated against.
- **Severity:** Low

### 3. graphql-core 3.3.0
- **Claim:** graphql-core 3.3.0.
- **Status:** Verified that it exists and is stable. It was released 2026-09-27 as "Production/Stable", supports Python 3.10 to 3.15 (3.14 included), is based on GraphQL.js 17.0.2, and is the first stable 3.3 after a long alpha/beta series. Frappe v16 does not depend on graphql-core, so there is no conflict. **However, the spine does not acknowledge the 3.3 breaking changes.** Most examples online and in model training data target 3.2. These breaking changes hit DocWeave's design directly:
  - `ExecutionContext` was renamed to `Executor`, and `execution_context_class` to `executor_class`. This affects `execution/executor.py`.
  - AST nodes are frozen dataclasses, and their collection fields are tuples. This affects `execution/rules.py` (depth/cost validation rules) and `execution/planner.py` (selection-set walking). Code must not mutate AST nodes.
  - Input coercion is stricter, and default values are validated against their types. This affects the custom `Decimal`/`Date`/`Datetime`/`JSON` scalars.
  - An `int` that can't be represented exactly as a float now raises when coerced to `Float`.
  - An explicit `Undefined` variable value is treated as omitted.
  - New features that may be useful: `AbortSignal` with executor hooks (for request timeouts), and `find_schema_changes()` for schema-revision diffs.
- **Evidence:** https://pypi.org/pypi/graphql-core/json ; https://github.com/graphql-python/graphql-core/releases/tag/v3.3.0 ; https://www.graphql-js.org/upgrade-guides/v16-v17/
- **Fix:** Pin `graphql-core~=3.3.0` and add a note to the Stack section: "3.3 API (GraphQL.js 17): use `Executor`/`executor_class`, treat AST as immutable, use 3.3 scalar coercion rules. Do not follow 3.2 examples." Optionally list `AbortSignal` under AD-10 as a timeout mechanism.
- **Severity:** Medium

### 4. `frappe.qb.get_query` signature
- **Claim:** `get_query` accepts `user`, `parent_doctype`, `ignore_permissions` and `ignore_user_permissions`.
- **Status:** Verified. `Engine.get_query(self, table, fields=None, filters=None, order_by=None, group_by=None, limit=None, offset=None, distinct=False, for_update=False, update=False, into=False, delete=False, *, validate_filters=False, skip_locked=False, wait=True, ignore_permissions: bool = True, ignore_user_permissions: bool = False, user: str | None = None, parent_doctype: str | None = None, reference_doctype=None, or_filters=None, db_query_compat=False)`. Note that the **default is `ignore_permissions=True`**, which confirms why AD-2 must set it explicitly. These are keyword-only arguments. `frappe.qb.get_query` is a thin `*args, **kwargs` passthrough to `Engine().get_query`.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/database/query.py (around line 224) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/query_builder/utils.py
- **Fix:** None. Consider passing `validate_filters=True` in `_authorized_query` as defence in depth alongside AD-6.
- **Severity:** -

### 5. Masking in `frappe.qb` (Deferred: "runtime confirmation")
- **Claim:** The source shows masking when `ignore_permissions=False`.
- **Status:** Verified in source. When `apply_permissions` is set, `get_query` stores `_doctype`, `_parent_doctype` and `_fields_list` on the query. At `.run()`, `execute_query` in `query_builder/utils.py` calls `mask_fields(...)`, which uses `get_masked_fields(parenttype=parent_doctype)`, and `mask_child_query_fields` for child queries. The PRD research addendum said there was "no evidence" of this. That is now superseded. Keeping the runtime test is still correct, because docs.frappe.io still labels masking "experimental".
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/database/query.py (around line 350) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/query_builder/utils.py (lines 86-190) ; https://docs.frappe.io/framework/data-masking
- **Fix:** Update the addendum or the spine to say qb returns *already-masked placeholder values*, which the adapter then replaces with the `MASKED` sentinel based on metadata (as AD-5 intends). State that the feature is officially experimental.
- **Severity:** -

### 6. `meta.get_masked_fields(parenttype=)`
- **Claim:** The masked set comes from `meta.get_masked_fields(parenttype=...)`.
- **Status:** Verified. The signature is `def get_masked_fields(self, parenttype=None)`. Caveats from the source:
  - It always evaluates **`frappe.session.user`**. There is no `user` parameter, and it returns `[]` for Administrator. This is consistent with AD-2, which uses the session user, but it means the adapter cannot compute masking for another user.
  - The result is cached in `frappe.cache` under `masked_fields::{doctype}::{parenttype}::{user}`.
  - It returns deep-copied `DocField`s, not fieldnames.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/model/meta.py (line 195)
- **Fix:** In AD-5, say the masked set comes from `get_masked_fields`, which already applies the role's `mask` permission per permlevel. Do not apply the mask permission a second time.
- **Severity:** Low

### 7. "`mask` permission type"
- **Claim:** "the user's `mask` permission".
- **Status:** Partly wrong wording. `mask` is a **DocPerm/Custom DocPerm checkbox column**. Having it checked at a permlevel lets the role see unmasked values. It is read via `meta.get_permlevel_access("mask", parenttype)`. It is **not** in `std_rights`, so it is not a ptype you pass to `frappe.has_permission(..., "mask")`.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/permissions.py (`std_rights`, lines 13-28) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/core/doctype/docperm/docperm.json ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/model/meta.py (`get_permlevel_access`, line 731)
- **Fix:** Reword to "the role's DocPerm `mask` (unmask) flag per permlevel, as applied by `get_masked_fields`". Make sure nobody calls `has_permission` with `ptype="mask"`.
- **Severity:** Low

### 8. `frappe.has_permission` signature
- **Claim:** `frappe.has_permission(doctype, "read", doc, user)`.
- **Status:** Verified. The signature is `has_permission(doctype=None, ptype="read", doc=None, user=None, throw=False, *, parent_doctype=None, debug=False, ignore_share_permissions=False)`. Positional `(doctype, "read", doc, user)` binds correctly.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/__init__.py (line 603) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/permissions.py (line 81)
- **Fix:** Use keyword arguments (`ptype="read", doc=doc, user=user`) to avoid positional drift. For child rows pass `parent_doctype=` (keyword-only). AD-7 needs this for parent-aware checks.
- **Severity:** -

### 9. `IntegrationTestCase` in v16
- **Status:** Verified. It is importable as `from frappe.tests import IntegrationTestCase` (re-exported from `frappe/tests/classes/`). It subclasses `UnitTestCase` and rolls back the database during class cleanup.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/tests/__init__.py ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/tests/classes/integration_test_case.py
- **Fix:** None. Note that rollback cleanup interacts with AD-11's "bump after commit": tests of `schema_revision` must commit explicitly or trigger `frappe.db.after_commit` by hand.
- **Severity:** -

### 10. Whitelisted endpoint path and HTTP method
- **Claim:** `POST /api/method/docweave.api.graphql`, whitelisted with `allow_guest=False`.
- **Status:** The path is verified. The v1 rules include `/method/<path:method>`, mounted at both `/api` and `/api/v1`. v2 also exposes `/api/v2/method/<method>`. **But `frappe.whitelist()` allows `["GET", "POST", "PUT", "DELETE"]` by default**, and two Frappe behaviours apply:
  - CSRF is validated only for `UNSAFE_HTTP_METHODS` (POST/PUT/DELETE/PATCH) (`auth.py`).
  - The request commits only for unsafe methods, and rolls back otherwise (`app.py` around line 445).
  
  So a mutation sent via GET would skip CSRF validation **and** be silently rolled back after reporting success. This contradicts AD-9 ("Frappe commits on success") and AD-12.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/api/v1.py ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/api/v2.py ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/__init__.py (`whitelist`, line 439) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/app.py ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/auth.py
- **Fix:** In AD-12 require `@frappe.whitelist(methods=["POST"])` for `graphql` (or reject mutation operations on non-POST requests). Make `sdl` GET-only and admin-checked. State which API version is supported (`/api/method` and/or `/api/v2/method`).
- **Severity:** High

### 11. `frappe.cache` API and "bump after commit"
- **Status:** Verified. `frappe.cache` is a `RedisWrapper` with `get_value(key, generator=None, user=None, expires=False, shared=False)`, `set_value(key, val, user=None, expires_in_sec=None, shared=False)` and `delete_value`. `frappe.db.after_commit` is a `CallbackManager` (`database.py`), so "after commit" can be implemented natively. Caveat: a full `frappe.clear_cache()` deletes all non-persistent site keys. If `schema_revision` is stored in `frappe.cache` it will be wiped, unless it is registered under the `persistent_cache_keys` hook or stored in the database.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/utils/redis_wrapper.py ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/database/database.py ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/cache_manager.py (line 297)
- **Fix:** In AD-11, say where `schema_revision` lives (a DocWeave Settings field, or a Redis key covered by `persistent_cache_keys`) and that the bump uses `frappe.db.after_commit.add(...)`.
- **Severity:** -

### 12. doc_events hooks for DocType / Custom Field / Property Setter
- **Claim:** `schema_revision` is bumped whenever DocWeave Settings, DocType, Custom Field or Property Setter changes, via `doc_events` in `hooks.py`.
- **Status:** **Wrong (incomplete).** doc_events fire only through the Document API (`Document.run_method`). Several v16 metadata paths use raw `frappe.db.delete`, which fires no doc_events:
  - `customize_form.py` around line 652 (reset field order): `frappe.db.delete("Property Setter", {...})`.
  - `customize_form.py` lines 463-465 (`clear_removed_items`): raw deletes of custom child rows such as actions and links.
  - `property_setter.py` around line 157: `delete_property_setter(..., bypass_hooks=True)` uses `frappe.db.delete("Property Setter", filters)`.
  
  In each case Frappe calls `frappe.clear_cache(doctype=...)` instead. Migrate's DocType sync uses `doc.insert()` with flags, so doc_events do fire there.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/custom/doctype/customize_form/customize_form.py ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/custom/doctype/property_setter/property_setter.py ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/cache_manager.py (lines 297-346) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/modules/import_file.py
- **Fix:** Do not rely on doc_events alone. Frappe calls `reset_metadata_version()` on every per-DocType and global cache clear. It writes a fresh hash to `frappe.client_cache["metadata_version"]`. Options:
  - (a) Include that `metadata_version` in the schema cache key (`docweave:schema:{settings_rev}:{metadata_version}`). This needs a runtime check that the value is visible across workers.
  - (b) Also add a `Customize Form` doc_event and a `clear_cache` hook. Note that the `clear_cache` hook runs only on a full clear, not on a per-DocType clear.
  
  Add a negative test: "reset field order in Customize Form invalidates schema".
- **Severity:** High (a stale schema exposes removed or renamed fields, or hides new mandatory ones)

### 13. `flit_core` in the bench new-app template
- **Status:** Verified. `boilerplate.py` writes `requires = ["flit_core >=3.4,<4"]` and `build-backend = "flit_core.buildapi"`.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/utils/boilerplate.py (lines 345-354)
- **Fix:** None.
- **Severity:** -

### 14. ERPNext v16
- **Status:** Verified. The `version-16` branch has `__version__ = "16.52.1"`, `requires-python >=3.14`, and `frappe = ">=16.50.0,<17.0.0"`.
- **Evidence:** https://raw.githubusercontent.com/frappe/erpnext/version-16/erpnext/__init__.py ; https://raw.githubusercontent.com/frappe/erpnext/version-16/pyproject.toml
- **Fix:** In CI, install ERPNext `version-16` and pin the same Frappe floor.
- **Severity:** -

### 15. MariaDB "Frappe v16 supported version"
- **Status:** Unverified as stated, because the spine names no version. The live source supports **10.6 through 11.8**: `setup_db.check_compatible_versions` warns below 10.6 and above 11.8. Frappe's own CI uses `mariadb:11.8`, and frappe_docker uses `mariadb:11.8`.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/database/mariadb/setup_db.py ; https://raw.githubusercontent.com/frappe/frappe/version-16/.github/workflows/_base-server-tests.yml ; https://raw.githubusercontent.com/frappe/frappe_docker/main/overrides/compose.mariadb.yaml
- **Fix:** Stack: "MariaDB 11.8 (CI); Frappe v16 supports 10.6 to 11.8." Use `mariadb:11.8` in GitHub Actions.
- **Severity:** Low

### 16. Redis "Frappe v16 supported version"
- **Status:** Unverified. No minimum server version is published in source. The Python client pin is `redis~=7.1.0`. Frappe CI installs the distro `redis-server` via apt. frappe_docker uses `redis:8.6-alpine`.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/pyproject.toml ; https://raw.githubusercontent.com/frappe/frappe/version-16/.github/actions/setup/action.yml ; https://raw.githubusercontent.com/frappe/frappe_docker/main/overrides/compose.redis.yaml
- **Fix:** Pin a concrete CI image (for example `redis:7` or `redis:8.6-alpine`, matching frappe_docker) and record it.
- **Severity:** Low

### 17. ruff 0.17.2
- **Status:** Verified that it exists. It was released 2026-10-22, two days before the spine, and is the latest. Frappe v16's own `.pre-commit-config.yaml` pins `ruff-pre-commit` **v0.14.10**. "Frappe-style config" copied from Frappe may format or lint differently across three minor versions, since ruff minors can change style and rule sets.
- **Evidence:** https://pypi.org/pypi/ruff/json ; https://raw.githubusercontent.com/frappe/frappe/version-16/.pre-commit-config.yaml
- **Fix:** Either keep 0.17.2 and own the config (do not claim parity with Frappe), or pin v0.14.10 to match Frappe exactly. A brand-new patch release is acceptable for a dev tool, but write down the choice.
- **Severity:** Low

### 18. frappe-bench 5.31.1
- **Status:** Verified that it exists. It was released 2026-10-23, **one day** before the spine, and is the latest. The previous release is 5.31.0 (2026-06-16).
- **Evidence:** https://pypi.org/pypi/frappe-bench/json
- **Fix:** Acceptable, but a one-day-old release has had no soak time. Consider `frappe-bench>=5.31.0,<6` in CI with a lock, or fall back to 5.31.0 if CI breaks.
- **Severity:** Low

### 19. Official Frappe MCP status (Deferred item)
- **Claim:** "Coexistence with the official Frappe MCP (PR #44431): revisit after v1." The addendum says "merge status unknown".
- **Status:** **Out of date.** A built-in MCP server ships in `version-16`. `frappe/api/v2.py` routes `Rule("/mcp", methods=["POST","GET","DELETE"], endpoint=handle_mcp)`. `frappe/mcp/` exists with a README: "Frappe exposes 14 tools at `/api/v2/mcp` ... The endpoint is enabled by default and uses the authenticated site user's permissions." It supports MCP protocol versions 2025-11-25 and 2026-07-28. v2 also has `/api/v2/discovery/*` schema endpoints.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/api/v2.py ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/mcp/README.md ; https://api.github.com/repos/frappe/frappe/contents/frappe/mcp?ref=version-16
- **Fix:** Move this out of Deferred. Add a short positioning note tied to FR-12 to FR-15 (MCP readiness): DocWeave complements the built-in `/api/v2/mcp` with batched, field-selective, typed reads. Consider whether DocWeave should register a GraphQL tool with the built-in MCP instead of only exporting SDL. Update the PRD addendum.
- **Severity:** Medium

### 20. `bench run-tests --app docweave`
- **Status:** Verified. The `run-tests` command has an `--app` option.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/commands/testing.py
- **Severity:** -

### 21. Deferred: "Frappe's built-in child query versus explicit batched loads"
- **Status:** Verified caveat. The built-in `ChildQuery.get_query` (`database/query.py` around line 2205) calls `frappe.qb.get_query(self.doctype, fields=..., filters=..., order_by="idx asc")` **without** `user` or `ignore_permissions=False`, so it runs with the default `ignore_permissions=True`. Masking for children is applied afterwards by `mask_child_query_fields`, but row-level permission conditions are not.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/database/query.py ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/query_builder/utils.py
- **Fix:** Note in the Deferred item that the built-in child query relies on parent authorization only. That is acceptable under AD-7 because children load only for parents that passed AD-4, but security tests should cover it.
- **Severity:** Low

## Items not independently verifiable
- Frappe Cloud compatibility (no source check possible). Treat it as an assumption.
- Runtime masking behaviour on the exact installed release. The spine already gates this on `test_masking.py`. Keep that gate.
- Whether `frappe.client_cache["metadata_version"]` is visible to every worker immediately (relevant to the fix for finding 12). It needs a runtime check.
