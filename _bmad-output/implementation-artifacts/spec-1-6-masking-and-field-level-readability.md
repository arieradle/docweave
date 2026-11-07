---
title: 'Masking and field-level readability'
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

**Problem:** After 1.5, a masked field returns Frappe's placeholder (`'XXXXXXXX'`), which breaks `Decimal` and `Date` coercion. A field above the user's permlevel silently comes back `null` with no error, so clients can't tell hidden from empty (FR-7, AD-5).

**Approach:** Before each query, the adapter computes the readable fields and the masked fields for the session user, from metadata and permissions only. Unreadable selected fields become `FORBIDDEN` and masked ones `MASKED` in the `Row`. Neither is queried. The generic resolver from 1.5 turns them into `null` plus the code.

## Boundaries & Constraints

**Always:**
- The masked set is the union of `meta.get_masked_fields(parenttype=...)` and a fresh computation from the user's current roles: fields with `mask` whose permlevel isn't in `meta.get_permlevel_access("mask", parenttype, user=user)`. For Administrator the fresh computation is empty, as in Frappe.
- Readability is computed before the query with `frappe.model.get_permitted_fields(doctype, parenttype=..., user=...)`. Standard fields are always readable and never masked. These checks cover `kind: "scalar"` fields (column fields). Table-field readability and `xDoc` inheritance are in 1.7.
- One code path serves every `Row` the adapter builds, taking `parenttype` as a parameter, so 1.7's Link and child rows reuse it unchanged.
- Results per request are cached by `(doctype, parenttype)`.
- Detection never compares or inspects values.

**Never:**
- Don't select masked or unreadable fields in SQL. Never return a placeholder string.
- Don't clear Frappe's mask cache from DocWeave.
- No filter or order checks (AD-6 for filters is Story 2.1). No Link or child sentinel inheritance (1.7).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Masked Currency | masked user selects the masked Currency field (see Open Question) | `null`; error `{path: [..., "<field>"], extensions.code: "MASKED"}`; no coercion error | N/A |
| Masked Date and Phone | masked user | `null` + `MASKED` each; sibling fields intact | N/A |
| Unmasked user | holds the unmask role | real values | N/A |
| Permlevel 1 | Sales User selects `ignorePricingRule` on Sales Order | `null` + `FORBIDDEN`; `salesOrder` is not nulled | N/A |
| Permlevel 1, allowed | Sales Manager | real value | N/A |
| Revocation | unmask role granted with cache warm, then revoked with no cache clear | `MASKED` on the next request (Frappe would still show the real value) | N/A |
| Grant | unmask granted, no cache clear | still `MASKED` (accepted, AD-5) | N/A |
| Administrator | `allow_administrator` on | no masking | N/A |
| Value is `"XXXXXXXX"` | an unmasked field whose real value is the placeholder string | returned as is | N/A |

</frozen-after-approval>

## Open Questions

- **Fixture for the Currency case.** The epics name "Customer `credit_limit` (Currency)", but ERPNext v16's Customer has no such field. Credit limits are rows of the `credit_limits` child table (Customer Credit Limit), and Customer has no Currency field at all. Options: the test adds a Custom Field `credit_limit` (Currency, `mask=1`) to Customer, as Spike 0.3 did with `spike_credit` (the AC wording stays true, using a test-only field) / mask Sales Order's `grand_total` instead (a native field; the AC text changes to `grandTotal`).

## Code Map

- `docweave/adapter/frappe_v16.py` (created in 1.5) -- `FrappeV16Adapter.load` and `_authorized_query`. Row building gains sentinels here.
- `docweave/core/types.py` (created in 1.5) -- the `MASKED` and `FORBIDDEN` sentinels and `Row`. `docweave/core/resolver.py` (1.5) -- already turns sentinels into coded errors. Reuse; don't change.
- `docweave/tests/utils.py` (created in 1.2, extended in 1.5) -- `make_user`, `set_settings`, `run_query`, Sales Order fixtures.
- `~/frappe-bench/apps/frappe/frappe/model/meta.py:195-214` -- `get_masked_fields` returns `[]` for Administrator and caches per user with no expiry. `l.687-738` -- `get_permitted_fieldnames` and `get_permlevel_access(permission_type, parenttype, *, user)`.
- `~/frappe-bench/apps/frappe/frappe/model/__init__.py:217` -- `get_permitted_fields`.
- `spikes/masking_check.py:80-89` -- the fresh computation that Spike 0.3 checked (`fresh_masked`). `spikes/fixtures.py:58-75` -- the masked and unmask users, the unmask role, and the `mask` Property Setters.
- `~/frappe-bench/apps/erpnext/erpnext/selling/doctype/sales_order/sales_order.json` -- `ignore_pricing_rule` is permlevel 1, readable only by Sales Manager.

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/adapter/frappe_v16.py` -- `readable_fields(doctype, parenttype)` and `masked_fields(doctype, parenttype)`, cached per request. Row building marks unreadable selected fields `FORBIDDEN` and masked ones `MASKED`, and queries only the rest plus `name`.
- [ ] `docweave/tests/test_masking.py` -- the matrix. Build fixtures with Property Setters (`mask=1`) and DocPerm `mask` rows as Spike 0.3 did. Clean up and clear the DocType cache in `tearDown`. The revocation test warms Frappe's cache as the unmask user, revokes the role through `User.remove_roles`, and doesn't clear any cache.
- [ ] `docweave/tests/test_masking.py` -- a negative test: patch `get_masked_fields` to return `[]` and assert the field is still `MASKED` through the fresh computation. Patch the fresh computation to return nothing and assert the cached set still masks.

**Acceptance Criteria:**
- Given any masked or forbidden selection, when it executes, then the masked or forbidden column is absent from the SQL that `_authorized_query` issued (checked with `frappe.db.sql` spying or a `get_query` spy on `fields`).
- Given a masked user, when two aliases select the same masked field, then each alias gets its own `MASKED` error with its own path.

## Design Notes

AD-5 accepts that a newly granted unmask permission stays masked until Frappe's DocType cache is cleared. The admin docs line ("clear the DocType cache after granting or revoking unmask") belongs to Story 4.2/4.3 docs, not here.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.

## Implementation Notes

## Spec Change Log

## Review Triage Log
