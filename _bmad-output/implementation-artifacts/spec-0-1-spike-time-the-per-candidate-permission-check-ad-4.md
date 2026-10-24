---
title: 'Spike: time the per-candidate permission check (AD-4)'
type: 'chore'
created: '2026-10-24'
status: 'ready-for-dev'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-0-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** AD-4 checks every candidate by loading it with `frappe.get_doc` and calling `frappe.has_permission`. Nobody has measured what that costs, so Epic 1 could be built on a check that is too slow.

**Approach:** On a real v16.53.0 + ERPNext v16.52.1 site, generate realistic fixtures, time the full check per user and per document size against baselines, and end with a keep-or-amend decision for AD-4.

**Decision (environment):** the spike runs on the bench from Story 0.0, with ERPNext v16.52.1, on a dedicated site `spike.localhost`.

**Decision (target):** AD-4 passes only if DocWeave is on par with or faster than Frappe's REST API returning the same data: a `/api/resource` list call plus one `GET /api/resource/<doctype>/<name>` per document, at p95 with a warm cache, for a 100-document page.

## Boundaries & Constraints

**Always:**
- Record exact Frappe and ERPNext tags, MariaDB version and hardware with every number.
- Measure with a cold and a warm cache. Report p50 and p95, plus queries per candidate.
- Spike code lives in `spikes/`, outside the app package, and runs with the bench's Python against the spike site.

**Never:**
- Ship spike code, or add it to the `docweave` package.
- Change Frappe or ERPNext source.
- Use real or production data.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Unrestricted | System Manager, 100 / 2,000 candidates | All allowed; timings recorded | N/A |
| Parent-link restriction | User Permission on Customer | Only that customer's orders allowed | N/A |
| Child-row restriction | User Permission on Warehouse (item rows) | Orders with other warehouses denied | N/A |
| Owner-only | `if_owner` read | Only own orders allowed | N/A |
| Shared | Access only through DocShare | Shared orders allowed | N/A |
| Large documents | Sets with 5, 20, 100 items | Time per candidate by size | N/A |

</frozen-after-approval>

## Code Map

- No application code exists yet. The repository holds only planning artifacts and the devcontainer.
- `spikes/` -- new, throwaway spike code (fixtures, timing harness).
- `_bmad-output/implementation-artifacts/spikes/` -- new, spike reports.
- Frappe v16.53.0 APIs used: `frappe.get_doc`, `frappe.has_permission(doctype, ptype, doc=, user=, ignore_share_permissions=)`, `frappe.get_list`, `frappe.qb.get_query(..., ignore_permissions=False, user=)`, `frappe.share.add`, `IntegrationTestCase.assertQueryCount` (pattern to reuse for counting queries).

## Tasks & Acceptance

**Execution:**
- [ ] `spikes/fixtures.py` -- generate Customers, Warehouses, Items, the three Sales Order sets (5, 20, 100 items, 2,000 orders each) and the five users with their User Permissions, `if_owner` role and DocShares -- realistic restriction mix; reused by Story 0.2
- [ ] `spikes/time_permission_check.py` -- for each user, set the session user, fetch candidates with `get_query(ignore_permissions=False)`, then time `get_doc` plus `has_permission` per candidate over 100 and 2,000 candidates, cold and warm -- the AD-4 cost
- [ ] `spikes/time_permission_check.py` -- time the baselines over HTTP against the running site, as each user: the REST equivalent (`/api/resource` list plus one `GET /api/resource/<doctype>/<name>` per document) as the pass/fail target; plus in-process `frappe.get_list` and `has_permission` on a document built from the row without loading -- target and overhead comparison
- [ ] `spikes/time_permission_check.py` -- compare allow/deny between the full check and the shortcut per candidate -- confirms the rejected shortcut's errors
- [ ] `_bmad-output/implementation-artifacts/spikes/spike-0-1-permission-check.md` -- report: environment, method, tables, parity differences, decision -- the deliverable

**Acceptance Criteria:**
- Given the fixtures, when the harness runs, then the report has p50/p95 ms per candidate and queries per candidate, per user and item-count set, cold and warm.
- Given the measurements, when compared with the REST baseline for a 100-document page at p95 warm, then the report ends with exactly one decision for AD-4: keep, or amend with a named option (lower scan budget, hybrid check, or per-request preloading of DocShare and child rows).
- Given the report, when someone follows its rerun instructions on the same versions, then they can reproduce the numbers.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

Fixture volume (2,000 orders with 100 items is 200,000 item rows) makes `get_doc().insert()` too slow. Insert fixture rows in bulk directly on the spike site; validation is not under test. Run scripts by initializing Frappe for the site (`frappe.init(site=...)` then `frappe.connect()`) from the bench's Python, so no throwaway Frappe app is needed.

## Verification

**Commands:**
- `../env/bin/python ../../spikes/time_permission_check.py --site spike.localhost` (from `frappe-bench/sites`) -- expected: completes and writes all tables

**Manual checks (if no CLI):**
- The report shows environment details, all tables populated, and one decision for AD-4.
