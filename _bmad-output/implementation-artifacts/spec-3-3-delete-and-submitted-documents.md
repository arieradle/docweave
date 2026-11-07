---
title: 'Delete and submitted documents'
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

**Problem:** Clients can create and update (3.1, 3.2) but can't delete drafts. Updates to submitted documents reach Frappe unchecked, and Frappe's own refusal message quotes the stored value, which may be hidden from the user (FR-11, AD-9, AD-13).

**Approach:** Add `deleteX(name: String!)`, which deletes through `frappe.delete_doc`. Before any update or delete on a submitted document, the write module checks every sent field against `allow_on_submit` and refuses delete, with a DocWeave message that names fields but never values.

## Boundaries & Constraints

**Always:**
- Readability first, for update and delete: a document unreadable through AD-2/AD-4, or missing, is `NOT_FOUND` with identical bodies, before any other check.
- Delete calls `frappe.delete_doc(doctype, name, ignore_missing=False)` and nothing else: no `force`, `ignore_permissions`, `ignore_on_trash` or `flags`. Frappe's own checks (delete permission, links from live records) stay in force; `LinkExistsError` maps to `VALIDATION`.
- `deleteX` returns `DeletePayload { name: String! }`, built by `schema/naming.py`.
- Submitted document (`docstatus` 1), update: a sent field, or a sent column of a child row, that isn't `allow_on_submit` is `VALIDATION`. Sending a Table field that isn't `allow_on_submit` is `VALIDATION`. New rows in an `allow_on_submit` table are allowed, as in Frappe. Nothing is saved.
- Submitted document, delete: refused per the Open Question, with nothing deleted.
- Cancelled document (`docstatus` 2), update: Frappe refuses any save ("Cannot edit cancelled document"); DocWeave pre-checks and returns `VALIDATION` for any update.
- Check order: readability (`NOT_FOUND`), then 3.1's write-permlevel/mask check (`FORBIDDEN`), then `docstatus` (`VALIDATION`), then Frappe.
- DocWeave's messages name the fields, never stored or sent values.

**Never:**
- No submit, cancel or amend mutations (after Epic 3). No transaction change (3.4).
- Never call `delete_doc` with its default `ignore_missing=True`, which silently returns on a missing name.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Draft delete | Sales Manager; draft SO | `{name}`; SO gone | N/A |
| Linked draft | draft SO referenced by a live record | `VALIDATION`, class `LinkExistsError`; not deleted | mapped |
| Unreadable or missing | User Permission hides the SO; or `name:"NOPE"` | `NOT_FOUND`, identical bodies; nothing deleted | N/A |
| Submitted, allowed field | `updateSalesOrder(input:{deliveryDate, poNo})` | saved | N/A |
| Submitted, other field | `input:{customer}` | `VALIDATION` naming `customer`; no save; message has no values | N/A |
| Submitted, child row | `items:[{name:"r1", qty:9}]` (`items` not `allow_on_submit`) | `VALIDATION`; no save | N/A |
| Submitted delete | `deleteSalesOrder` on a submitted SO | refused; still present | per Open Question |
| Cancelled update | any input | `VALIDATION`; no save | N/A |
| Cancelled delete | `deleteSalesOrder` on a cancelled SO | per Open Question | N/A |

</frozen-after-approval>

## Open Questions

- **Code for deleting a submitted document.** The epics say `VALIDATION`; AD-13 says only "delete is refused". Options: `VALIDATION` (Frappe raises `ValidationError` here too, `delete_doc.py:300`, so DocWeave's pre-check and Frappe agree) / `FORBIDDEN` (reads as "not allowed", but AD-15 reserves it for fields).
- **Deleting a cancelled document.** The epics refuse it; Frappe allows it (its check covers `docstatus` 1 only) and AD-13 names only submitted documents. Options: refuse with `VALIDATION` (stricter than Frappe desk; cancelled history can't be removed through DocWeave) / allow it through `delete_doc` as Frappe does (matches desk and REST; the epics' AC changes).
- **Delete refused by permission.** depends on 3.1 question: "Code for a refused write". `delete_doc` raises `PermissionError` for a user who can read but not delete.

## Code Map

- 3.1, 3.2 files (spec drafts) -- `WriteRequest` with kind `DELETE`, `DataAdapter.write`, the write module, the readability-first check, the planner's write plans. Extend; don't fork.
- `docweave/schema/naming.py`, `builder.py` (1.3, 3.1) -- add `delete_field_name` and the shared `DeletePayload`.
- `docweave/adapter/errors.py` (1.5) -- `map_exception`; `LinkExistsError` and `UpdateAfterSubmitError` are `ValidationError` subclasses (`frappe/exceptions.py:152,176`).
- `~/frappe-bench/apps/frappe/frappe/model/delete_doc.py:24` -- `delete_doc(..., ignore_missing=True, ...)` defaults; `:291` `check_permission_and_not_submitted` (delete permission; submitted refusal via `msgprint(raise_exception=True)`).
- `~/frappe-bench/apps/frappe/frappe/model/document.py:1363` `check_docstatus_transition` (cancelled: "Cannot edit cancelled document"); `:3285` `_validate_update_after_submit`, whose message includes the stored value -- the reason for DocWeave's own pre-check.

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/schema/naming.py`, `builder.py` -- `deleteX` and `DeletePayload`, tagged `{"kind": "delete", "doctype"}`.
- [ ] `docweave/execution/planner.py` -- DELETE `WriteRequest`; no payload load.
- [ ] write module -- delete path; `docstatus` pre-checks for update and delete.
- [ ] `docweave/tests/test_boundaries.py` (1.1, 3.1) -- `frappe.delete_doc` allowed in the write module only.
- [ ] `docweave/tests/test_mutations_delete.py` -- the matrix; spy `delete_doc` for `ignore_missing=False` and no other keywords; spy `save` and `delete_doc` to assert neither runs on every refused row; assert refusal messages don't contain the stored value.

**Acceptance Criteria:**
- Given a submitted SO with masked `customer`, when a client sends `customer`, then the result is `FORBIDDEN` and the body never contains the stored value.
- Given `frappe.delete_doc` in `execution/`, when `test_boundaries.py` runs, then it fails.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.

## Implementation Notes

## Spec Change Log

## Review Triage Log
