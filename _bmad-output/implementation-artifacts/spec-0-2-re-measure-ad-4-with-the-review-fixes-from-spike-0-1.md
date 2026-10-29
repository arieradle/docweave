---
title: 'Re-measure AD-4 with the review fixes from Spike 0.1'
type: 'chore'
created: '2026-10-29'
status: 'done'
baseline_commit: '63f22e4b1cc14676a5a12edf01dafa38f6cfe124'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-0-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Spike 0.1 amended AD-4 with a lower scan budget of 200, but that value is extrapolated from p50 per candidate, while the target is p95. Its review also found that the REST baseline's data parity and cold state were never verified.

**Approach:** Run the harness with the review fixes already in `spikes/` on the Spike 0.1 site and fixtures. Measure the time to fill one 100-document page at several scan budgets against REST's page p95, then confirm or replace Spike 0.1's decision.

## Boundaries & Constraints

**Always:**
- Same versions, hardware, site (`spike.localhost`) and fixtures as Spike 0.1. Record the environment with every number.
- The target stays Spike 0.1's: a 100-document page at p95 with a warm cache, on par with or faster than REST for the same user and item-count set.
- State the sample size next to every p95.
- Nothing else runs on the bench during the measurement: stop `bench start`, and don't open port 8001.

**Decision (target reading):** the target compares time for an equal number of readable documents. REST's cost per readable document is its 100-row page p95 divided by the readable documents on that page; DocWeave's is the fill p95 divided by the documents it returned.

**Decision (rerun scope):** full rerun of the harness, about 45 minutes, so every table in the report comes from one harness version, including REST cold with fresh workers.

**Never:**
- Edit the architecture, PRD or epics. Applying the decision stays the deferred item in `deferred-work.md`.
- Ship spike code, or change Frappe or ERPNext source.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Page fills before budget | unrestricted, customer, owner, shared | Scanned = 100 at every budget; same time at every budget | N/A |
| Short page | warehouse user (~50% pass) at budget 100 or 150 | Returned < 100, reported as a short page | N/A |
| Fill needs ~2× candidates | warehouse user at budget ≥ 200 | Scanned ≈ 200–220; p95 compared with REST | N/A |
| REST parity | every user and set, 100-row page | Name-set and allow/deny disagreements reported (expected 0) | Non-zero disagreements are listed in the report, not hidden |
| Server stalls | gunicorn stops answering | Run fails within 60 s; checkpoint keeps finished users | `--resume` continues |

</frozen-after-approval>

## Code Map

- `spikes/time_permission_check.py` -- harness. Already contains the review fixes:
  - `fill_pass` (checks candidates until `PAGE` pass or the budget runs out)
  - `FILL_BUDGETS = (200, 2000)` and `FILL_TRIALS = (3, 10)`
  - `restart_rest_workers` (HUP via `GUNICORN_PID`)
  - REST `names`/`allowed` in `Rest.page`, with `rest_name_mismatch` and `rest_allow_disagreements` in `comparison`
  - `dw_p95` using ping p95, and the fill table in `tables()`

  None of this has been run yet. Expect first-run bugs.
- `spikes/serve_rest.sh` -- gunicorn gthread with `--pid /home/vscode/frappe-bench/spike-gunicorn.pid`. The harness needs that file for the HUP.
- `spikes/fixtures.py` -- deterministic row names. Already loaded on `spike.localhost` with the same restriction mix as Spike 0.1: 196 / 229 / 203 shares. Do not reload.
- `spikes/results/` -- Spike 0.1's results, committed. Write Story 0.2's results under new names (`*-0-2.*`) so Spike 0.1's evidence stays intact.
- `_bmad-output/implementation-artifacts/spikes/spike-0-1-permission-check.md` -- Spike 0.1 report. Its decision says "provisional until Story 0.2"; update that line to point at the new report.
- `_bmad-output/implementation-artifacts/spec-0-1-spike-time-the-per-candidate-permission-check-ad-4.md` -- the Review Triage Log rows routed to Story 0.2 (1, 3, 4, 6).

## Tasks & Acceptance

**Execution:**
- [x] `spikes/time_permission_check.py` -- set `FILL_BUDGETS = (100, 150, 200, 300, 500, 2000)`; add an `--out-suffix` option for the result file names; smoke-run with `--quick` and fix what breaks -- measure enough budgets to pick one, not just test 200
- [x] `spikes/results/permission-check-0-2.{json,md}` -- the measured run -- evidence
- [x] `_bmad-output/implementation-artifacts/spikes/spike-0-2-ad-4-remeasure.md` -- report: environment, method changes from Spike 0.1, the fill table, the REST parity results, REST cold with fresh workers, a request-count table for walking a result set at each budget for the warehouse user, and the decision -- the deliverable
- [x] `_bmad-output/implementation-artifacts/spikes/spike-0-1-permission-check.md` -- replace "provisional until Story 0.2" with the final decision and a link to the new report -- one source of truth

**Acceptance Criteria:**
- Given the run, when the report is read, then each user and item-count set has a measured p95 fill time per budget, with candidates scanned and whether the page came back short, against that set's REST page p95.
- Given those measurements, then the report ends with exactly one decision for AD-4: a named scan budget that meets the target in every case, or, if no budget does for 100-item orders, one named alternative (preloading or the hybrid check) with the evidence for it.
- Given REST parity, then the report states the name-set and allow/deny disagreements per user and set.

## Implementation Notes

- Implemented directly in this session (no implementation subagent).
- Smoke run (two to three users, 5-item set, `--quick`) found two bugs before the full run:
  - `--out-suffix -0-2` is parsed as a flag; it must be passed as `--out-suffix=-0-2`. Verification command updated.
  - The fill table header printed `FILL_TRIALS` instead of the trial counts actually used.
- Full run 2026-10-29 21:05–21:47 UTC, exit 0. Results committed in `60ff2f0` before review, so they never need a rerun.
- The stall row of the matrix was tested separately against a port that accepts connections and never answers: the harness exited 1 after 61 s with `ReadTimeout`, and wrote no result files.
- The "target reading" decision was asked and recorded **after** the run's numbers were shown to the human. The report says so.
- Spike 0.1's Review Triage Log rows routed here:
  - 1 (budget extrapolated): closed by the fill passes.
  - 3 (REST parity): closed, 0 disagreements.
  - 4 (REST cold): closed, 75 HUPs in the run.
  - 6 (ping percentile): closed, ping p95 used.
- Review fixes (no rerun): equal-readable tables moved into the harness, with `--tables-from` to regenerate the Markdown from the JSON; `permission-check-0-2.md` was regenerated that way (additions only, every existing row unchanged).

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | Target reading chosen after seeing the numbers, not recorded as such | medium | The decision was asked after the run; the spec gave no timing | patch (spec notes, report section "Target reading") |
| 2 | The argument against 150 ignores that 200 is also short for warehouse/100 (94) | medium | Fill row warehouse/100/200 returned 94 | patch (report) |
| 3 | "Going higher only lengthens the worst request" ignores that 300+ fills the page | low | 300/500/2000 return 100 for warehouse/100 | patch (report) |
| 4 | 2,000-candidate cost cited from Spike 0.1, not this run | medium | This run measured 4.9–21.3 s warm, 5.6–20.8 s cold | patch (report) |
| 5 | Equal-readable tables hand-computed, not reproducible | medium | Not in `tables()` | patch (`equal_readable_tables`, `--tables-from`) |
| 6 | Sample sizes missing; small-n p95 not discussed | low | Spec requires n next to every p95 | patch (report) |
| 7 | Literal-comparison section title misleading | low | That table is the 100-candidate page check | patch (retitled, with a pointer to the Literal column) |
| 8 | REST cold numbers and HUP evidence missing from the report | medium | Spec task lists "REST cold with fresh workers" | patch (table plus 75 HUPs from the gunicorn log) |
| 9 | Default tables name changed from `permission-check-tables.md` | medium | Spike 0.1's rerun step names the old file | patch (no suffix keeps the Spike 0.1 names) |
| 10 | `res["fill_trials"]` overwritten on `--resume` | low | Line set unconditionally | patch (`setdefault`) |
| 11 | `tables()` KeyError on Spike 0.1's JSON | low | Verified: also `rest_name_mismatch` | patch (`.get` with defaults; Spike 0.1 JSON renders) |
| 12 | Spec working sections empty | low | Implementation Notes blank | patch |
| 13 | Spike 0.1 decision line lacks the target-reading caveat | low | Single source of truth | patch |
| 14 | Request-count table not for the warehouse user's measured pass rates | low | Generic pass rates only | patch (warehouse rows from measured fills) |
| 15 | `sprint-status.yaml` `last_updated` earlier than the run | low | 09:00 vs a 21:05 run | patch |
| 16 | `--resume` with different budgets or `--out-suffix` silently mixes or restarts | low | Manual flags; guards add branches | rejected |
| 17 | `--out-suffix` not validated for `/` or `..` | low | Manual flag on a throwaway script | rejected |
| 18 | Default run overwrites committed Spike 0.1 evidence | low | Recoverable from git; guard adds a branch | rejected |

## Design Notes

A budget below 100 cannot fill a 100-document page, so 100 is the floor. The request count for walking every readable warehouse order is `ceil(readable / 100)` pages when no page is short, and about `candidates / budget` when the budget binds. Compute it from the measured pass rate. No extra run is needed.

## Verification

**Commands:**
- `bash spikes/serve_rest.sh` (second terminal), then from `~/frappe-bench/sites`: `../env/bin/python /workspaces/docweave/spikes/time_permission_check.py --site spike.localhost --out-suffix=-0-2` -- expected: completes and writes `spikes/results/permission-check-0-2.{json,md}`

**Manual checks (if no CLI):**
- The fill table has every user, set and budget. REST parity columns are populated. The report has one decision.
