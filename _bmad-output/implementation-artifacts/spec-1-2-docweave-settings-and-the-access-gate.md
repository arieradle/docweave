---
title: 'DocWeave Settings and the access gate'
type: 'feature'
created: '2026-11-01'
status: 'done'
baseline_commit: '81563324c041c4dff04ff29839104e6d48de9c23'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** After 1.1 the app installs but has no configuration and no endpoint. Nothing yet says who may call DocWeave or what it exposes, and nothing keeps Frappe's message envelope out of responses (FR-2, FR-3, AD-12, AD-14).

**Approach:** Add the DocWeave Settings Single DocType and its exposed-DocType child table, a settings reader that returns a frozen `SettingsView`, and `docweave.api.graphql`: POST only, the three-step gate, `try/finally` rollback, and a werkzeug `Response` with GraphQL JSON only. After the gate the endpoint calls one seam, `_run`, which later stories fill in.

## Boundaries & Constraints

**Always:**
- Defaults: `enabled` 0, `allow_administrator` 0, `max_page_size` 100, `scan_budget` 200, `max_depth` 8, `child_fanout_estimate` 50, `max_child_rows` 10000.
- Settings: `issingle`, `track_changes`, and read/write for System Manager only. Exposed-DocType validation rejects `istable=1` DocTypes, Single DocTypes, DocWeave Settings itself and duplicate rows, each with a message that names the DocType and the reason.
- The gate order is AD-12's: disabled, then roles, then Administrator. Every failure is 403 with code `NOT_EXPOSED`. Website Users are always refused: the user must hold `Desk User` (Frappe adds it only for System Users) as well as a role in `allowed_roles`.
- Every body DocWeave writes is `{"data"?, "errors"?}`, with no `_server_messages`, `exc` or `message`. Status is 200 for GraphQL results, 400 for a malformed body (not JSON, `query` not a string, `variables` not an object or null) and 403 for the gate. An unexpected exception becomes 200 with `INTERNAL`, logged through `frappe.log_error`.
- Settings are read only in `adapter/settings.py`, through `frappe.get_single("DocWeave Settings")`.

**Decision (AD-1 and controllers):** amend AD-1 narrowly through correct-course: `frappe.model.document.Document` and `frappe.throw` are allowed in `docweave/docweave/doctype/**` only. `test_boundaries.py` and the spine's AD-1 are updated to match, with matrix cases for allowed and refused use.
**Decision (default roles):** an empty `allowed_roles` means any Desk User; the field description says so. No install-time write.
**Decision (guest and GET):** accept Frappe's own 403 envelope for guests and wrong HTTP methods; the spine's `@frappe.whitelist(methods=["POST"])` stands, and the documented 403 body differs for these two cases only.

**Never:**
- No schema, execution or data reads; `_run` returns `{"data": null}` until 1.3. No `sdl` endpoint (Story 4.1). No revision bump (1.4).
- No test files in the DocType folders. Tests live in `docweave/tests/`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fresh install | any desk user POSTs `{query}` | 403 `NOT_EXPOSED` | N/A |
| Enabled, allowed | Desk user holding an allowed role | 200, `_run` result | N/A |
| GET | enabled, allowed user | refused by Frappe's `methods=["POST"]` | Frappe's 403 |
| Website User | holds an allowed role | 403 `NOT_EXPOSED` | N/A |
| No allowed role | Desk user | 403 `NOT_EXPOSED` | N/A |
| Administrator | `allow_administrator` 0 / 1 | 403 / passes | N/A |
| Malformed body | not JSON; `query` missing or an int | 400 with a GraphQL error | N/A |
| Queued messages | `_run` calls `frappe.msgprint`, or raises via `frappe.throw` | body has only `data`/`errors` keys | throw → `INTERNAL` |
| Bad exposed row | Sales Order Item; DocWeave Settings; System Settings; a duplicate | save rejected with a message naming the DocType | `ValidationError` |

</frozen-after-approval>

## Code Map

- `docweave/tests/test_boundaries.py` (created in 1.1) -- the AD-1 allowlist checker. It gains the `doctype/**` rule here.
- `docweave/core/__init__.py`, `docweave/adapter/__init__.py`, `docweave/api.py` (created in 1.1, docstrings only) -- filled here.
- `~/frappe-bench/apps/frappe/frappe/permissions.py:33-40` -- `SYSTEM_USER_ROLE = "Desk User"`. `get_roles` (l.542) adds it only when `is_system_user(user)`; Administrator gets every role.
- `~/frappe-bench/apps/frappe/frappe/core/doctype/has_role/has_role.json` -- the existing child DocType with a single `role` Link. Reuse it as the `allowed_roles` Table MultiSelect; don't add a third DocType.
- `~/frappe-bench/apps/frappe/frappe/handler.py:46-63,99-110` -- a returned werkzeug `Response` is passed through untouched. A wrong HTTP method gets `throw_permission_error`.
- `~/frappe-bench/apps/frappe/frappe/model/document.py:496-503` -- an unsaved Single loads its JSON defaults, so a fresh install shows the defaults with no install hook.
- `~/frappe-bench/apps/frappe/frappe/tests/test_api.py:41-90` -- `FrappeAPITestCase` and its test client run each request in a separate thread with its own DB connection, so HTTP tests must commit their fixtures and clean up after.

## Tasks & Acceptance

**Execution:**
- [x] `docweave/tests/test_boundaries.py`, spine AD-1 -- add the `docweave/doctype/**` allowance (`Document`, `frappe.throw`) with tests; amend the spine line to match.
- [x] `docweave/core/types.py` -- `ErrorCode` (StrEnum with the spine's nine codes); frozen `SettingsView(enabled, allow_administrator, allowed_roles: frozenset[str], exposed_doctypes: tuple[str, ...], max_page_size, scan_budget, max_depth, child_fanout_estimate, max_child_rows, modified: str)`; frozen `GraphQLRequest(query: str, variables: dict | None, operation_name: str | None)`. No imports from Frappe or DocWeave.
- [x] `docweave/docweave/doctype/docweave_exposed_doctype/` -- `istable` child with `document_type` (Link to DocType, required, in list view); its controller is just a `Document` subclass.
- [x] `docweave/docweave/doctype/docweave_settings/` -- the Single: `enabled`, `allow_administrator`, `allowed_roles` (Table MultiSelect of Has Role), `exposed_doctypes` (Table), the five Int limits with their defaults, `track_changes`, System Manager-only permissions. `validate()` uses `frappe.get_meta` for the AD-14 checks, and rejects duplicates and limits below 1.
- [x] `docweave/adapter/settings.py` -- `get_settings() -> SettingsView`, the only Settings reader.
- [x] `docweave/api.py` -- `graphql()` decorated with `@frappe.whitelist(methods=["POST"])`. Parse the body from `frappe.local.request` into a `GraphQLRequest` (400 when malformed), run `_gate(settings)`, then `_run(request, settings) -> dict`. A `finally` block runs `frappe.db.rollback()` and clears `frappe.local.message_log`. The function always returns `Response(json, status, mimetype="application/json")`.
- [x] `docweave/tests/utils.py` -- `make_user(email, roles, user_type="System User")` with API keys, `auth_headers(user)` and `set_settings(**values)`. These are shared helpers for every later story.
- [x] `docweave/tests/test_access.py` -- the matrix over HTTP (committed fixtures, cleanup in `tearDown`), plus the defaults, the permission flags on Settings and `track_changes`.

**Acceptance Criteria:**
- Given a fresh install, when an admin opens DocWeave Settings, then the limits show 100, 200, 8, 50 and 10000, and the endpoint is disabled.
- Given a non-System Manager desk user, when they read or write DocWeave Settings, then Frappe refuses both.
- Given the whole package, when `test_boundaries.py` runs, then it passes, `Document` and `frappe.throw` pass in `doctype/**` and fail elsewhere.

## Design Notes

- The gate takes `frappe.session.user` and `frappe.get_roles()`. Both are allowed outside `adapter/`.
- `_run` is the seam later stories fill. Tests from 1.5 on call `docweave.api._run` in-process under `frappe.set_user`, so their fixtures need no commit.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass, including `test_access` and `test_boundaries`.
- `bench --site dev.localhost migrate` -- expected: both DocTypes are created with no errors.

## Implementation Notes

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Route | Evidence |
|---|---------|---------|-------|----------|
| 1 | Body parsed before the gate, so malformed bodies get 400 even for refused callers | medium | patch | AD-12 puts the gate first. Gate now runs before parsing. |
| 2 | `get_settings()` / `_gate()` outside the try, so failures escape as non-GraphQL errors | medium | patch | Both now inside the INTERNAL handler. |
| 3 | Nonexistent or empty `document_type` raises `DoesNotExistError` / a raw error in `validate()` | medium | patch | Empty rows skipped (required-field check reports them), unknown names throw a clear message; test case added. |
| 4 | Rollback of writes made in `_run` unverified | medium | patch | `test_writes_in_run_are_rolled_back` covers the success and exception paths. |
| 5 | Administrator with a non-empty `allowed_roles` untested | medium | patch | `test_administrator_with_allowed_roles`. |
| 6 | `operationName` validation untested | low | patch | Case added to `test_malformed_bodies`. |
| 7 | `get_settings()` field mapping unasserted | low | patch | `test_settings_view_maps_fields`. |
| 8 | `test_administrator` leaves Administrator API credentials behind | low | patch | Cleanup restores them when the test created them. |
| 9 | No upper bound or relational checks on limits; no denylist for sensitive DocTypes (User, DocPerm, virtual) | maybe-false | defer | Would be medium if admins are not trusted; settings are System Manager only. Needs a product decision. |
| 10 | Controller's `frappe.get_meta` banned by AD-1 | false | rejected | `frappe.get_meta` is allowed everywhere outside `adapter/`; `test_real_package_passes` passes. |
| 11 | Settings read from DB on every request, no cache | false | rejected | Caching is Story 1.4. |
| 12 | `except Exception` turns ValidationError/PermissionError into INTERNAL | false | rejected | Spec: an unexpected exception becomes INTERNAL. |
| 13 | No explicit Guest check in the gate | false | rejected | Decided in the spec: Frappe's whitelist refuses guests. |
| 14 | `allowed_roles` may hold `All` or `Guest` | false | rejected | The gate also requires `Desk User`, so these cannot admit non-desk users. |
| 15 | `Sales Order Item` in a test needs ERPNext | false | rejected | CI installs ERPNext; the spec names that row. |
| 16 | Empty query, oversized body, rollback or log_error raising in `finally`, empty `{}` body, null limits, deleted exposed DocType, dead loop code in the boundary test, `log_error` unasserted, test cleanup overwriting dev settings, `patch.object` | low | rejected | Unlikely in everyday use; fixes add guards or branches. |
