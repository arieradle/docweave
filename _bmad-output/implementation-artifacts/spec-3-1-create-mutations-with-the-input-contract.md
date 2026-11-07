---
title: 'Create mutations with the input contract'
type: 'feature'
created: '2026-11-01'
status: 'draft'
baseline_commit: 'cd5c12665210c90e70229a728c76326a8c6e0bfe'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

v2 backlog: not implemented in v1.

**Problem:** DocWeave is read-only. It has no `Mutation` root type, so integrators can't create documents through it, and nothing yet defines which fields a client may write (FR-11, AD-9, AD-13).

**Approach:** Add a `Mutation` root with `createX(input: XCreateInput!)` per Exposed DocType. Input types are generated from metadata by AD-13's exclusion rules. The adapter checks the input against the user's write permlevels and masked set, then inserts through `frappe.get_doc(...).insert()`. The payload `{ name, doc }` re-reads `doc` through the normal read planner.

## Boundaries & Constraints

**Always:**
- Input types exclude standard fields (`name`, `owner`, `creation`, `modified`, `modifiedBy`, `docstatus`, `idx`, `_*`, `parent*`), `read_only`, `fetch_from` unless `fetch_if_empty`, `is_virtual`, Password and every display/layout fieldtype. `name` is included only when `meta.autoname` lowercased is `prompt`, and is passed to Frappe as `__newname`. Table fields become `[XItemCreateInput!]` built by the same rules. All names come from `schema/naming.py`.
- Before any write: a sent field (or a sent child column) whose permlevel is not in `meta.get_permlevel_access("write", parenttype, user=)`, or that is in 1.6's masked set for the user, fails the mutation with `FORBIDDEN`, and nothing is inserted. A Table field counts at its own permlevel.
- Inserts use `frappe.get_doc(dict).insert()` with no arguments: no ignore flags. Loaded or created documents never leave the write module; it returns the name only.
- The payload `doc` is a `ROOT_ONE` load of the new name through the 1.5 path (AD-2, AD-4, 1.6 masking). If it is unreadable, `name` is still returned and `doc` is `null` with `NOT_FOUND`.
- Exceptions go through `adapter/errors.py`: `ValidationError` subclasses (for example `MandatoryError`, `LinkValidationError`) become `VALIDATION` with the class and sanitized message.
- The payload's selection is planned and cost-checked before the insert.

**Never:**
- No update or delete (3.2, 3.3). No change to api.py's unconditional rollback (3.4): until then, mutations persist only within the request.
- No `ignore_permissions`, `ignore_mandatory`, `ignore_links`, `set_name` or `flags` overrides. No `frappe.db.commit`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Input shape | introspect `SalesOrderCreateInput` | has `customer`, `deliveryDate`, `items`; lacks `name`, `owner`, `docstatus`, `grandTotal` (read-only), `customerName` (`fetch_from`), Password/Section fields | N/A |
| Prompt autoname | DocType with autoname `Prompt` | `name` present in its create input; doc is inserted with that name | N/A |
| Happy path | Sales User; valid customer, company, date, one item | `{name: "SAL-ORD-…", doc {name grandTotal}}` | N/A |
| Above write permlevel | Sales User sends a permlevel-1 field | `null` + `FORBIDDEN`; no insert | N/A |
| Masked field | masked user sends a masked field | `null` + `FORBIDDEN`; no insert | N/A |
| Masked child column | sends masked `rate` in an item row | `FORBIDDEN`; no insert | N/A |
| Mandatory missing | no `customer` | `null` + `VALIDATION`, class `MandatoryError` | mapped |
| Can create, can't read | `has_permission` hook denies read of new docs | `name` set; `doc: null` + `NOT_FOUND` | N/A |
| No create permission | user with read only | see Open Question 2 | `PermissionError` |

</frozen-after-approval>

## Open Questions

- **Which DocTypes get mutations.** Options: every Exposed DocType, gated only by Frappe permissions (simplest; an admin who exposed a DocType for reads in v1 gets writes on upgrade) / a per-row `allow_writes` check in `DocWeave Exposed DocType`, default off (explicit opt-in; adds a Settings field, a patch and schema-fingerprint input).
- **Code for a refused write.** AD-15 maps every `PermissionError` to `NOT_FOUND`; the epic says "a permission error". Options: keep `NOT_FOUND` (one map, but a create refused for lack of `create` reads as "not found") / `FORBIDDEN` for DocType-level create and for write/delete on a document the user *can* read, `NOT_FOUND` only when it is unreadable (clear to clients; amends AD-15's "FORBIDDEN is for fields" rule) / a new `PERMISSION` code (amends `core`'s code list and Story 4.2's contract).
- **Where write code lives.** The epics name a `writes.py`; the spine has no such module and AD-1 allows `frappe.get_doc` only in `adapter/permission.py`. Options: new `adapter/writes.py`, the only file allowed `frappe.get_doc`/`frappe.delete_doc` for writes, plus a `DataAdapter.write` port method (clean separation; amends AD-1, AD-16 and the structural seed) / put writes in `adapter/frappe_v16.py` (no new module; still amends AD-1 and AD-16, and mixes read and write code).
- **Required fields in input.** Options: every input field nullable, Frappe's mandatory check gives `VALIDATION` (fields Frappe or hooks default, such as `transaction_date`, need not be sent) / `reqd` fields non-null in the input (clients see requirements in the schema, but must send values Frappe would default).

## Code Map

- `docweave/schema/naming.py` (1.3) -- `type_name`, `field_name`, `root_one_name`, reverse map. Add `create_field_name` (`createSalesOrder`), `create_input_name` (`SalesOrderCreateInput`), `payload_name` (`SalesOrderPayload`).
- `docweave/schema/fieldtypes.py` (1.3) -- `FIELDTYPE_MAP`, `EXCLUDED_FIELDTYPES`, `STANDARD_FIELDS`. `docweave/schema/scalars.py` (1.3 output; input coercion from Story 2.1, spec not yet written).
- `docweave/schema/builder.py` (1.3) -- `build_schema`; `extensions["docweave"]` tags. Add the `Mutation` type, tagged `{"kind": "create", "doctype"}`; input fields tagged with `fieldname`.
- `docweave/core/types.py` (1.2, 1.5) -- `ErrorCode`, `Sentinel`, `LoadRequest`, `Row`, `DocWeaveError`. `docweave/core/port.py` (1.5) -- `DataAdapter.load`.
- `docweave/execution/planner.py`, `graph.py`, `executor.py` (1.5, 1.7) -- `plan`, `PlanNode`, `assemble`, `execute(schema, request, adapter)`. Cost check from Story 2.4 (`execution.rules.estimate_cost`).
- `docweave/adapter/frappe_v16.py` (1.5, 1.6) -- `FrappeV16Adapter`, `masked_fields(doctype, parenttype)`. `adapter/permission.py` (1.5) -- `PermissionChecker`. `adapter/errors.py` (1.5) -- `map_exception`.
- `docweave/tests/test_boundaries.py` (1.1) -- the AD-1 allowlist; `frappe.get_doc` is allowed only in `adapter/permission.py` today.
- `~/frappe-bench/apps/frappe/frappe/model/document.py:675` `insert()`; `:977` `__newname` for Prompt; `:1263` `validate_higher_perm_levels` silently resets above-permlevel values (why the request-time check is needed). `model/meta.py:731` `get_permlevel_access`.

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/core/types.py`, `core/port.py` -- frozen `WriteRequest(kind: CREATE | UPDATE | DELETE, doctype, name: str | None, values: Mapping[fieldname, value | tuple[Mapping, ...]])`, keyed by Frappe fieldnames; `DataAdapter.write(request) -> str` (per the location Open Question).
- [ ] `docweave/schema/naming.py`, `builder.py` -- create input types, payload types and the `Mutation` root.
- [ ] `docweave/execution/planner.py`, `executor.py` -- plan mutation fields in document order into `WriteRequest`s plus a `ROOT_ONE` payload node; cost-check, write, then load payloads.
- [ ] write module (per Open Question) -- permlevel/mask pre-check, then `frappe.get_doc(values).insert()`; return the name.
- [ ] `docweave/tests/test_boundaries.py` -- allow the write calls in the write module only; ban `frappe.db.commit` everywhere.
- [ ] `docweave/tests/test_mutations_create.py` -- the matrix; spy `insert` to assert it is called with no arguments.

**Acceptance Criteria:**
- Given a FORBIDDEN input, when the mutation runs, then `insert` is never called (spy).
- Given `frappe.get_doc` in `execution/` or a write call in `adapter/permission.py`, when `test_boundaries.py` runs, then it fails.

## Design Notes

The `name` and `fetch_if_empty` rules extend AD-13's text but match Frappe: only Prompt autoname takes a client name (`document.py:977`), and `fetch_if_empty` keeps a sent value (`document.py:3042`). The spine should record both.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.

## Implementation Notes

## Spec Change Log

## Review Triage Log
