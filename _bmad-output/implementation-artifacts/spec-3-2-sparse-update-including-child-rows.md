---
title: 'Sparse update, including child rows'
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

**Problem:** After 3.1 clients can create but not change documents. A naive full-document save would overwrite masked or unreadable values with placeholders or nulls, and a client-supplied child row `name` could take over another document's rows (FR-11, AD-9, AD-13).

**Approach:** Add `updateX(name: String!, input: XUpdateInput!)`. The adapter first proves the document readable (the 1.5 path), loads it with `frappe.get_doc`, applies only the fields present in the input, reconciles child rows by verified `name`, and calls `.save()` with no ignore flags. The payload is 3.1's `{ name, doc }`.

## Boundaries & Constraints

**Always:**
- `XUpdateInput` uses 3.1's create-input rules and also drops `set_only_once` fields. All of its fields are optional. Child rows use `XItemUpdateInput`: the create-input rules for the child DocType plus an optional `name`.
- Only keys present in the input change. An explicit `null` sets the field to empty; Frappe's own checks then apply. An absent Table field leaves the table untouched.
- A present Table field is the complete new list: a row with `name` patches only its sent columns on the loaded row (hidden columns keep their stored values), a row without `name` is appended, existing rows left out are removed. Final order is input order.
- A row `name` must be a row of this document's same Table field, checked against the loaded document. Any other `name`, whether it belongs to another document, another Table field, or doesn't exist, is `FORBIDDEN`. A `name` repeated in one list is `VALIDATION`. Nothing is saved in either case.
- 3.1's request-time checks apply to every sent field and sent child column: above the write permlevel or masked is `FORBIDDEN`.
- Readability first: a document unreadable through AD-2/AD-4 is `NOT_FOUND`, identical to a missing one, before any load or validation.
- Loaded documents never leave the write module.

**Never:**
- No delete or submitted-document handling (3.3). No transaction change (3.4).
- Never write a value the client didn't send. Never send a stored, masked or default value back through the input.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Sparse | masked user; `updateSalesOrder(name, input:{deliveryDate})` on an SO with a masked field | only `delivery_date` changes; masked value unchanged in the DB | N/A |
| Patch row | `items:[{name:"r1", qty:5}, {name:"r2"}]`; `rate` masked | `r1.qty` = 5; `r1.rate`, `r2` unchanged | N/A |
| Insert and delete | `items:[{name:"r1"}, {itemCode:"X", qty:1}]` on rows r1, r2 | r1 kept, new row added, r2 removed | N/A |
| Foreign row | `name` of a row of another SO, or of another Table field | `null` + `FORBIDDEN`; no save | N/A |
| Unknown row | `name:"nope"` | `FORBIDDEN` (same as foreign) | N/A |
| Duplicate row | the same `name` twice | `VALIDATION`; no save | N/A |
| Masked or high-permlevel input | sends a masked field or `ignorePricingRule` as Sales User | `FORBIDDEN`; no save | N/A |
| Unreadable doc | User Permission hides the SO; or a missing name | `NOT_FOUND`, identical bodies | N/A |
| `set_only_once` | introspect `SalesOrderUpdateInput` | no `namingSeries` | N/A |
| Explicit null | `{poNo: null}` | `po_no` cleared | N/A |
| Frappe validation | qty negative | `VALIDATION` with class | mapped |

</frozen-after-approval>

## Open Questions

- **Refused write on a readable document.** depends on 3.1 question: "Code for a refused write". `.save()` raises `PermissionError` for a user who can read but not write.
- **Lost updates.** The adapter loads the current document, so `check_if_latest` never fires and the last writer wins on the fields it sent. Options: no concurrency check (simplest; sparse patches limit the damage) / an optional `expectedModified: Datetime` argument, compared before save, mismatch is `VALIDATION` with `TimestampMismatchError` (safe read-modify-write for clients; one more argument).

## Code Map

- 3.1 files (spec draft) -- `WriteRequest(kind, doctype, name, values)`, `DataAdapter.write`, the write module with the permlevel/mask pre-check, the `Mutation` builder, the planner's write plans, `SalesOrderPayload`. Extend; reuse the pre-check unchanged.
- `docweave/schema/naming.py` (1.3, 3.1) -- add `update_field_name`, `update_input_name`, child `XItemUpdateInput`.
- `docweave/adapter/frappe_v16.py` (1.5, 1.6) -- the `ROOT_ONE` read and `masked_fields`; reuse for the readability-first check. `adapter/permission.py` (1.5) -- `PermissionChecker.readable`.
- `~/frappe-bench/apps/frappe/frappe/model/document.py:796` `_save` -- `_restore_masked_fields_from_db` (l.1231) also restores masked values, but only from Frappe's cached masked set; DocWeave's check doesn't rely on it. `:1140` `validate_set_only_once` raises `CannotChangeConstantError`. `:1263` `validate_higher_perm_levels` resets silently.
- `~/frappe-bench/apps/erpnext/erpnext/selling/doctype/sales_order/sales_order.json` -- `naming_series` is `set_only_once`; `delivery_date` and `po_no` are `allow_on_submit` (3.3).

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/schema/naming.py`, `builder.py` -- update input types and `updateX`, tagged `{"kind": "update", "doctype"}`.
- [ ] `docweave/execution/planner.py` -- build an UPDATE `WriteRequest` holding only present keys (absent vs `null` kept apart via graphql-core's coerced input dict).
- [ ] write module -- readability check, `frappe.get_doc(doctype, name)`, pre-check, row verification, patch/append/remove, `.save()`.
- [ ] `docweave/tests/test_mutations_update.py` -- the matrix. Negative tests: spy `save` and assert it is not called for each `FORBIDDEN`, `VALIDATION` and `NOT_FOUND` row; read the DB directly as Administrator to prove hidden values survived.

**Acceptance Criteria:**
- Given a patch of row r1 whose hidden column has a stored value, when the update runs, then that stored value is unchanged.
- Given two SOs A and B, when updating A with B's row name, then neither A nor B changes.

## Design Notes

Dropping `set_only_once` fields from update input matches Frappe, which refuses any change to them after insert (`validate_set_only_once`). Frappe checks it on the parent only, so child update inputs keep such columns. The spine's AD-13 should record the rule.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.

## Implementation Notes

## Spec Change Log

## Review Triage Log
