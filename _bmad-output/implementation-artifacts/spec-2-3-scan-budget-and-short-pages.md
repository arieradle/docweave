---
title: 'Scan budget and short pages'
type: 'feature'
created: '2026-11-01'
status: 'draft'
baseline_commit: 'cd5c12665210c90e70229a728c76326a8c6e0bfe'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** After 2.2, a page scans one chunk of `first` candidates. A user who can read few of them gets mostly empty pages. Nothing ties a request's cost to the measured AD-4 budget of 200 checks (FR-8, FR-9, FR-10, AD-4, AD-8).

**Approach:** Replace the one-chunk scan with a fill loop. It fetches keyset chunks after the last checked position and checks candidates one at a time through AD-4. It stops when the page has `first` edges, when candidates are known to be exhausted, or when `scan_budget` checks are spent. In that last case it returns a short page with `scanLimitReached` and a continuation cursor, never an error.

## Boundaries & Constraints

**Always:**
- The budget is `SettingsView.scan_budget` (default 200). It applies per connection plan node, so each alias has its own. No argument or variable can set it.
- "Scanned" means checked through `PermissionChecker` (`get_doc` plus `has_permission`). A fetched but unchecked row doesn't count against the budget and never becomes the position.
- Chunk size is `min(scan_budget − scanned, max_page_size)`. Each chunk starts strictly after the last checked position, using 2.2's `keyset_criterion`.
- Outcome, in order of precedence:
  1. **Exhausted.** A chunk returned fewer rows than requested and all of them were checked: `hasNextPage: false`, `endCursor: null`, `scanLimitReached: false`.
  2. **Page full.** `hasNextPage: true`, `scanLimitReached: false`, and `endCursor` is the last checked row.
  3. **Budget spent.** `scanLimitReached: true`, `hasNextPage: true`, and `endCursor` is the last checked candidate. `endCursor` differs from `after`, and it is issued even when `edges` is empty.
- `hasNextPage` comes only from checked candidates, never from peeking at a fetched but unchecked row.
- Within one walk, each candidate is checked once. Keyset positions are strict, and 1.5's per-request cache dedupes within a request.
- Select-only users still get an empty connection with no scan (2.1).
- The README's DocWeave section documents the AD-15 accepted residual: `scanLimitReached` can reveal that many hook-rejected documents match a filter range.

**Never:**
- No `max_total_candidates` across connections (v2). No client-settable budget.
- No batch preloading for AD-4. No change to the cursor format or payload.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 7 of 5,000 | budget 100, `first: 20`; a `has_permission` hook allows 7 | walking `after: endCursor` until `hasNextPage` is false returns the 7 exactly once; the walk terminates; each of the 5,000 is checked exactly once | N/A |
| Budget spent | budget 100; none of the next 100 is readable | `edges: []`, `scanLimitReached` and `hasNextPage` true, `endCursor` = 100th checked ≠ `after` | N/A |
| Default 200 | defaults; user reads none of 5,000 | exactly 200 checks; short page with `scanLimitReached: true` | N/A |
| Aliases | `a:` over an unreadable range, `b:` over readable rows | `a` spends its own budget; `b` fills its page; check counts are counted per alias | N/A |
| Exhausted | last candidates checked | `hasNextPage: false`, `endCursor: null` | N/A |
| Fills on the last check | the page fills on check number `scan_budget` | `scanLimitReached: false`, `hasNextPage: true` | N/A |
| Ends at the budget | exactly 100 candidates, budget 100 | `scanLimitReached: true` (exhaustion unknown); the next request gives `[]`, `false`, `null` | N/A |
| Over-fetch | the page fills at the 20th row of a 100-row chunk | `endCursor` = 20th row; the next page starts at the 21st | N/A |
| Mixed | 30% readable, `first: 20`, budget 200 | full pages until near the end, then a short tail; union = parity set | N/A |

</frozen-after-approval>

## Code Map

- `docweave/adapter/frappe_v16.py` (1.5, 2.1, 2.2) -- `ROOT_CONNECTION` loading: replace the single chunk with the loop. Reuse `_authorized_query(after=...)`.
- `docweave/adapter/cursor.py` (2.2) -- `encode`, `decode` and `keyset_criterion`. Don't change the payload.
- `docweave/adapter/permission.py` (1.5) -- `readable(doctype, names)` with a per-request cache. Call it per candidate (`(name,)`) so the loop can stop exactly at the budget.
- `docweave/core/types.py` (1.2) -- `SettingsView.scan_budget`, `max_page_size`.
- `docweave/tests/test_pagination.py` (2.2), `test_query_count.py` (2.2), `tests/utils.py` (1.2, 1.5) -- reuse the helpers.
- `~/frappe-bench/apps/frappe/frappe/database/database.py:1496` -- `bulk_insert(doctype, fields, values)` for the 5,000-row fixture (tests are outside AD-1 scope). `frappe.tests.IntegrationTestCase.patch_hooks` for the `has_permission` hook.
- `spikes/spike-0-2-ad-4-remeasure.md` -- the source of the 200 default: one request costs about one REST page; the budget bounds a request, not a walk.

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/adapter/frappe_v16.py` -- the fill loop, the precedence rules and the per-node scan counter.
- [ ] `docweave/tests/test_scan_budget.py` -- the matrix. Insert the 5,000 minimal Sales Orders once per class with `frappe.db.bulk_insert` and remove them in `tearDownClass`. Count checks per name by spying `PermissionChecker` (or `frappe.get_doc` in `adapter/permission.py`).
- [ ] `docweave/tests/test_scan_budget.py` -- negative tests:
  - a request never makes more than `scan_budget` checks per connection;
  - `endCursor` never equals `after` when `hasNextPage` is true;
  - `hasNextPage` is never `false` while a fetched row is unchecked (patch `readable` to record the order of checks);
  - a variable or argument can't change the budget (the schema has no such argument).
- [ ] `docweave/tests/test_query_count.py` -- extend: with every row readable, candidate queries stay constant. With none readable, each connection makes at most `ceil(scan_budget / max_page_size)` candidate queries.
- [ ] `README.md` -- one line on the `scanLimitReached` residual in the DocWeave section from 1.1.

**Acceptance Criteria:**
- Given the full 7-of-5,000 walk, when it finishes, then the number of requests is at most `ceil(5000 / 100) + 1`, and every response with `hasNextPage: true` has a non-null `endCursor`.
- Given the 2.2 pagination suite, when it reruns under the loop, then it passes unchanged.

## Design Notes

A chunk of up to `max_page_size` rows keeps candidate queries to about 2 per request at the defaults, even for `first: 1`. Over-fetched rows cost only the SQL read. They are never checked and never move the position. The 5,000-row walk does 5,000 `get_doc` calls in total, roughly 20–40 s on the dev box according to the Spike 0.2 per-candidate p50. That is acceptable in CI and doesn't need a "slow test" marker.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.
- `bench --site dev.localhost run-tests --app docweave --module docweave.tests.test_scan_budget` -- expected: passes in under 2 minutes.

## Implementation Notes

## Spec Change Log

## Review Triage Log
