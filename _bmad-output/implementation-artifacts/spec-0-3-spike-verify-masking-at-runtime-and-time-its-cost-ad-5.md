---
title: 'Spike: verify masking at runtime and time its cost (AD-5)'
type: 'chore'
created: '2026-10-24'
status: 'in-review'
baseline_commit: 'ef3c2c5f50d3aae8f37b82020a48e46888c880cd'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-0-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** AD-5 relies on Frappe v16 masking values when `frappe.qb.get_query` runs with permissions applied, including child rows in parent context. This was confirmed only by reading source, and Frappe has documented bugs in this area.

**Approach:** On the real v16.53.0 site, observe masking per fieldtype for parent and child rows, the unmasked default, cache behaviour after a role change and permlevel handling, then time the cost and end with a keep-or-amend decision for AD-5.

## Boundaries & Constraints

**Always:**
- Record exact Frappe and ERPNext tags with every observation.
- Configure masking only through Frappe's own settings (field `mask` property and the DocPerm unmask setting).
- Reuse Story 0.1's spike site and fixtures where they fit.

**Never:**
- Detect masking by comparing values to placeholder strings in anything meant to carry into DocWeave. Observing placeholders in the report is fine.
- Ship spike code, or change Frappe or ERPNext source.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Parent fields masked | Customer Data, Currency, Date, Int masked; user lacks unmask | Placeholder recorded per fieldtype | Record any type error |
| Child fields masked | Sales Order Item Currency, Data masked; `parent_doctype="Sales Order"` | Masked or not, recorded | Record if masking is missing |
| Permissions ignored | Same query with `ignore_permissions=True` | Values unmasked | N/A |
| Unmask granted, then revoked | Role with unmask added, then removed; no cache clear | Whether results follow the role change | Record stale results |
| Above permlevel | Permlevel 1 field in `fields`, user lacks level 1 | Dropped, nulled or error, recorded | Record exception type |

</frozen-after-approval>

## Code Map

- `spikes/fixtures.py` -- from Story 0.1; extend with masking configuration on Customer and Sales Order Item fields, an unmask role, and a permlevel-1 custom field.
- `spikes/masking_check.py` -- new, observation and timing harness.
- `_bmad-output/implementation-artifacts/spikes/` -- spike reports.
- Frappe v16.53.0: `frappe/model/meta.py` `get_masked_fields(parenttype)` (line ~195) and `get_permlevel_access(permission_type, parenttype, user=)` (line ~731); `frappe/model/utils/mask.py` `mask_field_value` (placeholders: `XXXXXXXX` default, `XX-XX-XXXX` date, partial phone and email); `frappe/database/query.py` stores masking metadata only when permissions are applied.

## Tasks & Acceptance

**Execution:**
- [x] `spikes/fixtures.py` -- add the masking configuration, the unmask role and a permlevel-1 field -- spike setup
- [x] `spikes/masking_check.py` -- run each matrix scenario and record the raw values returned per fieldtype, for parent and child rows -- runtime evidence for AD-5
- [x] `spikes/masking_check.py` -- grant and revoke the unmask role without clearing caches; compare `get_masked_fields` with a fresh `get_permlevel_access("mask", ...)` computation and with query results -- confirms whether AD-5's fresh computation is needed
- [x] `spikes/masking_check.py` -- over 2,000 Customers, time queries with and without masked fields, and time the fresh masked-set computation -- masking overhead
- [x] `_bmad-output/implementation-artifacts/spikes/spike-0-3-masking.md` -- report: environment, matrix results, timings, decision, architecture text to change -- the deliverable

**Acceptance Criteria:**
- Given each matrix scenario, when the harness runs, then the report records the observed behaviour and exact values or exceptions.
- Given the timing runs, when complete, then the report gives p50/p95 overhead in ms for masked queries and for the fresh computation.
- Given the findings, when compared with AD-5 and AD-2, then the report ends with exactly one decision for AD-5 (keep or amend) and lists any architecture text that must change.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `../env/bin/python /workspaces/docweave/spikes/masking_check.py --site spike.localhost` (from `frappe-bench/sites`) -- expected: completes and writes the report tables

**Manual checks (if no CLI):**
- The report covers every matrix row, includes timings, and ends with one decision for AD-5.
