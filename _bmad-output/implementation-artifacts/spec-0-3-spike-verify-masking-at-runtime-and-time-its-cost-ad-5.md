---
title: 'Spike: verify masking at runtime and time its cost (AD-5)'
type: 'chore'
created: '2026-10-24'
status: 'done'
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

- Implemented directly in this session (no implementation subagent).
- First run: the Redis-key check double-prefixed the key (`exists()` applies `make_key` itself), so it read 0 throughout. Fixed. The TTL and the leak-recovery steps were added in the same rerun.
- The masked user is Stock User, because Sales User can read Customer permlevel 1.
- After review the harness gained scenarios (filters, sorting and aggregates; field-level-read documents; ordinary-user session cases; child-row fresh computation and cache reset; Administrator) and a second fixture user (`spike.unmasked@example.com`). Rerun 2026-10-31 21:53 UTC, about 5 s, exit 0. The new leak findings were verified as Administrator: same top 3 and the same SUM and MAX.
- Commits: `e616293` (harness, first results), `d8e1a7e` (report), `a72731f` (review fixes and new evidence).

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | Filters, sorting and aggregates on masked fields untested | high | Rerun: equality and range filters, ordering, SUM and MAX all use real values | patch (scenario; AD-6 clarification) |
| 2 | Fresh computation and cache reset only checked for the parent | medium | Child keys are separate | patch (child columns; `clear_cache(doctype="Sales Order")` step) |
| 3 | Session-user claim rests on Administrator only | medium | Administrator is special-cased | patch (two ordinary-user pairings) |
| 4 | "get_doc is not masked" too broad | medium | `apply_fieldlevel_read_permissions()` masks | patch (scenario; claim narrowed) |
| 5 | Off-run never asserted unmasked | medium | Only the on-run was asserted | patch (assertion) |
| 6 | Overhead as a difference of p95s; no 200-row page; percent overhead not stated | low | Spec for timing | patch (paired diffs, 200 rows, percent) |
| 7 | Fresh cost measured warm only | low | Local cache hit | patch (first-call-of-request timings) |
| 8 | Environment rows not recorded by the harness | low | `environment()` lacked Redis, Python, CPU | patch |
| 9 | Evidence Markdown truncated; types lost | low | `[:900]` slices, `str()` of lists and dates | patch (fenced JSON, typed recursion) |
| 10 | Fresh computation not special-cased for Administrator | medium | Frappe returns `[]` for Administrator | patch (AD-5 clarification 4; recorded value) |
| 11 | Unmask flag not repaired after a partial fixture run | low | Set inside the exists check | patch |
| 12 | No admin guidance for revocation; no upstream note | low | Leak reaches Frappe's own surfaces | patch (report section) |
| 13 | Fixtures change the shared site without saying so | low | Custom DocPerm and Property Setters | patch (docstring, report) |
| 14 | Other fieldtypes, Link and `fetch_from` leaks untested | medium | Matrix scope | patch (limitation); not run |
| 15 | Role changes other than a User save untested | medium | The roles cache could stay stale | patch (limitation); not run |
| 16 | `cached_masked_child_no_parent` result unexplained | low | Masking metadata lives on the child | patch (report sentence) |
| 17 | Paths tied to one machine; no cwd check | low | Documented layout | rejected |
| 18 | `git describe` failure gives empty versions | low | Same as Spike 0.1 | rejected |
| 19 | Exceptions outside `attempt()` abort the run; zero-row results | low | Fails loudly; reruns in 5 s | rejected |
| 20 | Timing method differs from the spec's wording | low | Method stated in the report | rejected |

## Verification

**Commands:**
- `../env/bin/python /workspaces/docweave/spikes/masking_check.py --site spike.localhost` (from `frappe-bench/sites`) -- expected: completes and writes the report tables

**Manual checks (if no CLI):**
- The report covers every matrix row, includes timings, and ends with one decision for AD-5.
