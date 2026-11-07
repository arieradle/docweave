---
title: 'Authorized single-document read'
type: 'feature'
created: '2026-11-01'
status: 'draft'
baseline_commit: 'cd5c12665210c90e70229a728c76326a8c6e0bfe'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The schema answers introspection, but `salesOrder(name:)` always returns `null`. No data path exists yet. The first one must enforce Frappe's permissions exactly, with no bypass (FR-4, FR-6, FR-14, NFR-1).

**Approach:** Build the first pass of two-phase execution: plan root `salesOrder` nodes, preload through a `DataAdapter`, assemble a result graph keyed by response key, then let graphql-core resolve from it. The Frappe adapter reads only through `_authorized_query` (AD-2). It then runs the AD-4 document check (`get_doc` plus `has_permission`, cached per request) and maps exceptions in one place (AD-15).

## Boundaries & Constraints

**Always:**
- `_authorized_query(doctype, *, fields, filter=None, order=None, after=None, limit=None, parent_doctype=None, parentfield=None, parent_names=None, keys=None)` is closed (no `**kwargs`). It calls `frappe.qb.get_query(..., ignore_permissions=False, ignore_user_permissions=False, user=frappe.session.user)` and runs it. If the user the adapter was built for isn't `frappe.session.user`, it raises (a `raise`, not an `assert`). Until Epic 2, `filter`, `order` and `after` must be `None`.
- `frappe.qb` appears only inside `_authorized_query`. `get_doc` and `has_permission` appear only in `adapter/permission.py`, which returns names and booleans, never documents.
- Returned values come from the Stage 1 query row, never from the loaded document.
- A user without DocType-level `read` (select-only, or no permission at all) gets `NOT_FOUND` with no candidate query.
- An unreadable document and a missing one give identical responses: `salesOrder: null` with `NOT_FOUND`.
- `adapter/errors.py` is the only exception mapper. `DoesNotExistError` and `PermissionError` become `NOT_FOUND`; `ValidationError` becomes `VALIDATION` with the class name and a sanitized message; anything else becomes `INTERNAL` with a generic message. `INTERNAL` entries are recorded as standard tracebacks with no locals, then written in api.py's `finally` after the rollback, through `frappe.log_error(title, message, defer_insert=True)`.
- Resolvers do no I/O. They read the graph by `info.path.key` and turn a `Sentinel` into a `GraphQLError` carrying `extensions.code`.

**Never:**
- No masking or `FORBIDDEN` logic (1.6). No Link or child loads (1.7); `xDoc` and Table fields resolve to `null`. No lists, filters or cursors (Epic 2).
- Never switch the session user. Never use `ignore_permissions=True`. Never fall back to the document's values.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Allowed | Sales User; `salesOrder(name:"SO-1"){name grandTotal}` | both fields | N/A |
| Missing name | `name:"NOPE"` | `null` + `NOT_FOUND` | N/A |
| User Permission on Customer | SO-1's customer isn't permitted | identical to missing | N/A |
| `permission_query_conditions` / `has_permission` hook | the hook excludes or denies SO-1 | identical to missing | N/A |
| Child-row Warehouse UP, share, `if_owner` | parity matrix | equals `get_list` membership plus `has_permission` | N/A |
| Select-only | role with only `select` | `NOT_FOUND`; `_authorized_query` not called | N/A |
| Document differs from the row | `get_doc` patched to change `grand_total` | Stage 1 value returned | N/A |
| Aliases | `a: salesOrder(name:"SO-1") b: salesOrder(name:"SO-2")` | two nodes, each its own result | N/A |
| Variables | `query($n: String!){salesOrder(name:$n){name}}` | bound before planning | bad variables → `VALIDATION` |
| Session switched | session user changed after the adapter was built | the load raises | → `INTERNAL` |
| Closed parameters | `_authorized_query(..., ignore_permissions=True)` | `TypeError` | N/A |
| Unexpected error | the adapter raises `KeyError` | 200, `INTERNAL`, no traceback in the body; one deferred Error Log entry with no locals | logged |

</frozen-after-approval>

## Code Map

- `docweave/core/types.py` (created in 1.2) -- `ErrorCode`, `SettingsView`, `GraphQLRequest`. Extended here.
- `docweave/schema/builder.py` (created in 1.3) -- `extensions["docweave"]` tags: type `{doctype, is_child}`; field `{fieldname, kind, target}`; root `{kind: "root_one", doctype}`. Here, attach `core.resolver.resolve_field` to every DocType and root field.
- `docweave/execution/executor.py` (created in 1.3) -- `execute(schema, request, root_value=None)`. Here it becomes `execute(schema, request, adapter)`.
- `docweave/schema/cache.py` (created in 1.4) -- `get_schema(settings)`. `docweave/api.py` (1.2) -- `_run(request, settings)` and the `finally` block.
- `docweave/tests/test_boundaries.py` (created in 1.1) -- add the rule that `frappe.qb` is allowed only inside `_authorized_query`.
- `~/frappe-bench/apps/frappe/frappe/database/query.py:224-248` -- the `get_query` keywords. `query_builder/utils.py:136-160` -- `run()` applies masking.
- `~/frappe-bench/apps/frappe/frappe/__init__.py:603` -- `has_permission(doctype, ptype, doc, user, ...)`. Use `ptype="read"` with no `doc` for the DocType-level check.
- graphql-core 3.3 public API -- `get_variable_values`, `get_argument_values`, `get_directive_values` (for `@skip`/`@include`). Don't use `execution.collect_fields`, which is internal.
- `~/frappe-bench/apps/erpnext/erpnext/selling/doctype/sales_order/test_sales_order.py:3473` -- `make_sales_order(**args)`. `frappe.tests` `IntegrationTestCase.patch_hooks` and `set_user`. `spikes/fixtures.py` shows how the Warehouse UP, share and `if_owner` users are built.

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/core/types.py` -- frozen `Sentinel(code)` and the constants `MASKED`, `FORBIDDEN`, `NOT_FOUND`; `LoadKind` (`ROOT_ONE`, `ROOT_CONNECTION`, `LINK`, `CHILDREN`); frozen `LoadRequest(kind, doctype, fields: frozenset[str], filter=None, order=None, first=None, after=None, keys: tuple[str, ...] = (), parent_doctype=None, parentfield=None)`; `Row`, an immutable `Mapping[str, value | Sentinel]` keyed by Frappe fieldname that always holds `name`, with attribute `matched_key: str | None`; `DocWeaveError(code, message)`.
- [ ] `docweave/core/port.py` -- `DataAdapter` Protocol: `load(requests: Sequence[LoadRequest]) -> Sequence[list[Row]]`, aligned with the requests. Epic 2 adds `Page`.
- [ ] `docweave/core/resolver.py` -- `resolve_field(parent, info, **_)`.
- [ ] `docweave/adapter/errors.py` -- `map_exception(exc) -> DocWeaveError`; a `ContextVar` holding the deferred entries; `take_deferred() -> list[tuple[str, str]]`.
- [ ] `docweave/adapter/permission.py` -- `PermissionChecker` per request: `can_read_doctype(doctype) -> bool` and `readable(doctype, names) -> set[str]`, with a per-request cache.
- [ ] `docweave/adapter/frappe_v16.py` -- `_authorized_query`; `FrappeV16Adapter(user, settings)`, which implements `ROOT_ONE` (`keys=(name,)`, `limit=1`, then the Stage 2 check), maps exceptions and raises `DocWeaveError`.
- [ ] `docweave/execution/planner.py` -- `PlanNode` (identity: doctype, parent_doctype, parentfield or link fieldname, argument fingerprint, path; plus response key and the selected fields as response key to fieldname). `plan(schema, document, operation_name, variables)`, with its own field collection over fragments and `@skip`/`@include`.
- [ ] `docweave/execution/graph.py` -- `assemble(nodes, results) -> dict`. No row gives `NOT_FOUND` at the root key.
- [ ] `docweave/execution/executor.py`, `docweave/api.py`, `docweave/schema/builder.py` -- the wiring described above. A `DocWeaveError` during the load gives `{"data": null, "errors": [...]}`.
- [ ] `docweave/tests/utils.py` -- `run_query(query, variables=None, *, user)`, which calls `api._run` in-process, and Sales Order fixture builders.
- [ ] `docweave/tests/test_permissions.py`, `docweave/tests/test_parity.py` -- the matrix. Parity: for each fixture user and SO, DocWeave returns the SO iff it is in `frappe.get_list` and `has_permission` is true for it.

**Acceptance Criteria:**
- Given a permitted user, when `salesOrder` runs, then `get_query` was called with `ignore_permissions=False` and `ignore_user_permissions=False` (spied with `unittest.mock`).
- Given a `has_permission` hook that denies SO-1, when the document check runs twice in one request, then `get_doc` runs once.
- Given the package, when `test_boundaries.py` runs, then `frappe.qb` used outside `_authorized_query` fails.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.
- Manual POST over HTTP: `salesOrder` on a real SO as a Sales User with an API key -- expected: 200 and the selected fields.

## Implementation Notes

## Spec Change Log

## Review Triage Log
