# Spike 0.2: Re-measuring AD-4 with the review fixes

**Story:** 0.2 · **Date:** 2026-10-29 · **Decision:** **Confirm Spike 0.1's amendment: lower AD-4's default scan budget from 2,000 to 200 candidates.** This rests on the "equal readable documents" reading of the target, which the human chose after seeing this run's numbers (see "Target reading" below).

## Summary

- **Per readable document, the target holds at every budget.** DocWeave's warm p95 costs 0.52–0.60× REST's in the worst case of each budget, across all five users and three order sizes. When a page fills, the scan stops. And REST pays for denied documents too: its 100-row list includes them, and each of their GETs returns 403.
- **So the budget doesn't decide the target; it caps one request.** It bounds how long a single request can run for users who can read little of what the candidate query returns. This run's 2,000-candidate scans took 4.9–21.3 s warm (n=3) and 5.6–20.8 s cold (n=2). At 200 the slowest measured request was 1.9 s warm p95 (n=10) for 100-item orders, close to one REST page for that set (1.8 s, n=20).
- **REST matches the full check exactly.** For every user and set, the REST list returned the same 100 names as `get_query`, with the same allow/deny answer per name (0 and 0 in all 15 cases).
- **The literal reading fails in one case.** Comparing DocWeave's fill time with one REST 100-row page, the warehouse user with 100-item orders fails at budget 200 and above (1.06–1.26×), and passes at 150 or below (0.84× and less). DocWeave returns about twice as many readable documents as that REST page.

## Target reading

Spike 0.1's target says DocWeave must be "on par with or faster than Frappe's REST API returning the same data", for a 100-document page at p95 warm. It doesn't say whether "the same data" means the same 100-row REST page or the same number of readable documents. The two readings differ only when many candidates are denied. In this run that is only the warehouse user (45–50% pass).

**The human chose the equal-readable reading after this run's numbers were shown** (spec decision, recorded 2026-10-29, after the run). Under the literal reading, the decision would have been a budget of 150. The report gives both readings so the choice can be revisited.

## What changed from Spike 0.1

| | Spike 0.1 | Spike 0.2 |
|---|---|---|
| Budget value | 200 extrapolated from p50 per candidate | Fill-one-page passes measured at budgets 100, 150, 200, 300, 500 and 2,000 (3 cold and 10 warm trials each) |
| REST parity | assumed | REST list names and per-name allow/deny compared with the full check |
| REST cold | Redis cleared only; gunicorn workers kept warm caches | gunicorn HUPed before each cold trial. The log shows 75 HUPs in the run (5 cold trials × 15 sets), each booting 2 fresh workers. |
| DocWeave estimate | page p95 + ping p50 | page p95 + ping p95 (6.7 ms) |
| Fixture row names | random hashes | deterministic (`SPK-SO-100-0001-001`); same seed and the same restriction mix (196 / 229 / 203 shares) |

Everything else is as in [Spike 0.1](spike-0-1-permission-check.md): the same site, fixtures, users, method and target.

**Sample sizes.** A p95 over 10 warm fill trials is in practice the second-highest value. A cold p95 over 3 trials is close to the maximum. A REST page p95 is over 20 warm or 5 cold trials. Every figure below names its n.

## Environment

| | |
|---|---|
| Frappe / ERPNext | v16.53.0 / v16.52.1 |
| MariaDB / Redis / Python | 11.8.9 / 7.4.12 / 3.14.10 |
| Hardware | GitHub Codespace, Intel Xeon Platinum 8370C @ 2.80 GHz, 2 cores, 7.8 GB RAM |
| REST server | gunicorn 23.0.0, gthread, 2 workers × 4 threads, `--preload` (`spikes/serve_rest.sh`) |
| HTTP round trip | p50 3.2 ms, p95 6.7 ms |
| Run | 2026-10-29, 21:05–21:47 UTC, nothing else running on the bench |
| Evidence | `spikes/results/permission-check-0-2.json`. Every table below is in `permission-check-0-2.md`, regenerated with `--tables-from spikes/results/permission-check-0-2.json` (no measuring). |

## The deciding numbers

### Equal readable documents: worst case per budget

| Budget | Worst equal-readable ratio | Where |
|---|---|---|
| 100 | 0.56 | customer, 100 items |
| 150 | 0.54 | warehouse, 100 items |
| 200 | 0.52 | customer, 100 items |
| 300 | 0.53 | warehouse, 100 items |
| 500 | 0.57 | warehouse, 100 items |
| 2000 | 0.60 | customer, 100 items |

### Equal readable documents: warehouse user (fill: 10 warm trials; REST: 20)

| User | Items | Budget | REST readable per page | REST ms per readable doc | Returned | DocWeave ms per returned doc | Equal-readable ratio | Literal ratio (fill ÷ REST page) |
| warehouse | 5 | 100 | 49 | 18.1 | 49 | 7.5 | 0.41 | 0.41 |
| warehouse | 5 | 150 | 49 | 18.1 | 74 | 7.6 | 0.42 | 0.63 |
| warehouse | 5 | 200 | 49 | 18.1 | 100 | 6.9 | 0.38 | 0.78 |
| warehouse | 5 | 300 | 49 | 18.1 | 100 | 6.7 | 0.37 | 0.75 |
| warehouse | 5 | 500 | 49 | 18.1 | 100 | 7.5 | 0.42 | 0.85 |
| warehouse | 5 | 2000 | 49 | 18.1 | 100 | 7.1 | 0.39 | 0.80 |
| warehouse | 20 | 100 | 50 | 21.5 | 50 | 9.7 | 0.45 | 0.45 |
| warehouse | 20 | 150 | 50 | 21.5 | 77 | 8.9 | 0.42 | 0.64 |
| warehouse | 20 | 200 | 50 | 21.5 | 100 | 9.1 | 0.42 | 0.85 |
| warehouse | 20 | 300 | 50 | 21.5 | 100 | 8.7 | 0.40 | 0.81 |
| warehouse | 20 | 500 | 50 | 21.5 | 100 | 9.0 | 0.42 | 0.84 |
| warehouse | 20 | 2000 | 50 | 21.5 | 100 | 9.3 | 0.43 | 0.87 |
| warehouse | 100 | 100 | 45 | 40.1 | 45 | 21.6 | 0.54 | 0.54 |
| warehouse | 100 | 150 | 45 | 40.1 | 70 | 21.5 | 0.54 | 0.84 |
| warehouse | 100 | 200 | 45 | 40.1 | 94 | 20.4 | 0.51 | 1.06 |
| warehouse | 100 | 300 | 45 | 40.1 | 100 | 21.2 | 0.53 | 1.18 |
| warehouse | 100 | 500 | 45 | 40.1 | 100 | 22.8 | 0.57 | 1.26 |
| warehouse | 100 | 2000 | 45 | 40.1 | 100 | 21.6 | 0.54 | 1.20 |

The same table for every user, and the full fill table with cold p95, are in `spikes/results/permission-check-0-2.md`.

### REST parity, and a 100-candidate page against one REST 100-row page (warm p95, 20 trials)

This is the per-page check without filling, the same comparison as Spike 0.1's target table. The literal-reading failures in the Summary come from the warehouse table above ("Literal ratio" column).

| User | Items | REST list + GETs | DocWeave check + 1 round trip | Ratio | get_list only | Shortcut page | Preload page | REST vs full: different names | REST vs full: allow/deny disagreements |
|---|---|---|---|---|---|---|---|---|---|
| unrestricted | 5 | 783 | 304 | 0.39 | 5.9 | 35 | 51 | 0 | 0 |
| unrestricted | 20 | 1015 | 352 | 0.35 | 6.4 | 16 | 137 | 0 | 0 |
| unrestricted | 100 | 1747 | 695 | 0.40 | 1.9 | 12 | 526 | 0 | 0 |
| customer | 5 | 852 | 322 | 0.38 | 5.2 | 84 | 122 | 0 | 0 |
| customer | 20 | 1157 | 470 | 0.41 | 6.4 | 41 | 261 | 0 | 0 |
| customer | 100 | 2404 | 1276 | 0.53 | 4.0 | 26 | 1079 | 0 | 0 |
| warehouse | 5 | 889 | 460 | 0.52 | 4.9 | 50 | 170 | 0 | 0 |
| warehouse | 20 | 1074 | 480 | 0.45 | 8.8 | 26 | 262 | 0 | 0 |
| warehouse | 100 | 1803 | 1128 | 0.63 | 3.0 | 32 | 792 | 0 | 0 |
| owner | 5 | 869 | 278 | 0.32 | 4.6 | 36 | 63 | 0 | 0 |
| owner | 20 | 1406 | 345 | 0.25 | 12.3 | 27 | 193 | 0 | 0 |
| owner | 100 | 1906 | 781 | 0.41 | 3.0 | 15 | 542 | 0 | 0 |
| shared | 5 | 1081 | 484 | 0.45 | 13.9 | 224 | 256 | 0 | 0 |
| shared | 20 | 1302 | 543 | 0.42 | 12.0 | 200 | 320 | 0 | 0 |
| shared | 100 | 2073 | 970 | 0.47 | 13.5 | 222 | 826 | 0 | 0 |

### REST cold with fresh workers (page p95 ms; cold n=5, warm n=20)

| User | Items | Cold | Warm | Cold ÷ warm | Spike 0.1 cold ÷ warm (Redis only) |
|---|---|---|---|---|---|
| unrestricted | 5 | 1057 | 783 | 1.35 | 1.44 |
| unrestricted | 20 | 1191 | 1015 | 1.17 | 1.36 |
| unrestricted | 100 | 2110 | 1747 | 1.21 | 1.19 |
| customer | 5 | 1044 | 852 | 1.23 | 1.15 |
| customer | 20 | 1315 | 1157 | 1.14 | 1.22 |
| customer | 100 | 2633 | 2404 | 1.10 | 1.04 |
| warehouse | 5 | 1110 | 889 | 1.25 | 1.30 |
| warehouse | 20 | 1241 | 1074 | 1.16 | 1.11 |
| warehouse | 100 | 2006 | 1803 | 1.11 | 1.12 |
| owner | 5 | 1142 | 869 | 1.31 | 1.24 |
| owner | 20 | 2326 | 1406 | 1.65 | 1.20 |
| owner | 100 | 2194 | 1906 | 1.15 | 1.03 |
| shared | 5 | 1305 | 1081 | 1.21 | 1.15 |
| shared | 20 | 1515 | 1302 | 1.16 | 1.16 |
| shared | 100 | 2252 | 2073 | 1.09 | 1.08 |

Restarting the workers barely changed REST's cold cost. Its cold-over-warm ratio stays in the same range as Spike 0.1's, so the gunicorn workers' in-process caches were not hiding much.

### Requests to walk the warehouse user's 2,000 candidates

Measured pass rates are 49%, 50% and 45% for 5, 20 and 100 items. Each request scans `min(budget, candidates needed to fill 100)`. These counts are computed from the measured fill rows, not run.

| Items | Budget 100 | 150 | 200 | 300 | 500 | 2,000 |
|---|---|---|---|---|---|---|
| 5 (49%) | 20 × 49 | 14 × 74 | 11 × 100 | 11 × 100 | 11 × 100 | 11 × 100 |
| 20 (50%) | 20 × 50 | 14 × 77 | 11 × 100 | 11 × 100 | 11 × 100 | 11 × 100 |
| 100 (45%) | 20 × 45 | 14 × 70 | 10 × 94 | 10 × 100 | 10 × 100 | 10 × 100 |

Entries read *requests × documents per request*. For lower pass rates (computed, no fixture user has one), the number of requests at budget 200 grows as `2,000 / 200 = 10`, while each request returns fewer documents: about 40 at 20%, about 10 at 5%. At budget 2,000 the same user gets one request that scans everything, which took 4.9–21.3 s warm in this run.

## Decision for AD-4

**Confirm the amendment: lower the default scan budget from 2,000 to 200 candidates (2 × the maximum page of 100).**

- **The target, read as equal readable documents, is met at every budget.** At 200, the worst case over all users and sets is 0.52× REST.
- **200 caps a single request** at the 200-candidate cost: for 100-item orders, 1.9 s warm p95 (n=10) and 2.2 s cold p95 (n=3) on this machine, about one REST page. At 2,000 a request can scan all 2,000 candidates: 4.9–21.3 s warm in this run.
- **The trade-off is short pages.** At 200, the warehouse user with 100-item orders (45% pass) already gets a short page of 94. 150 returns 70 and 100 returns 45 for that user, with requests of 1.5 s and 1.0 s. Budgets of 300 and up fill that page to 100 for about 10% more time (2.1 s against 1.9 s). They only cost more when a user's pass rate is low enough for the budget to bind, and no fixture user had one.
- **Correctness doesn't change.** A short page carries `scanLimitReached` and a continuation cursor (FR-8, Story 2.3).

**Applying it** (still the item in `deferred-work.md`, for the human): the architecture's "Default limit values", Story 2.3's defaults and tests, and Story 1.2's `DocWeave Settings` default.

## Limitations

- No fixture user has a pass rate far below 50%, so the cost of a high budget binding was not measured in fill mode. The 2,000-candidate scans (limit 2,000, unrestricted and warehouse users) show what a fully bound budget costs, because one scanned candidate costs one `get_doc` plus one `has_permission` whatever the outcome.
- The REST side of the equal-readable comparison is the measured 100-row page divided by its readable documents. Fetching exactly 100 readable documents through REST (about 220 GETs) was not timed directly.
- The p95 figures rest on small samples: 10 warm and 3 cold fill trials, 20 warm and 5 cold REST pages.
- Unchanged from Spike 0.1:
  - only the `items` child table is filled
  - no `has_permission` hook, no user with two User Permissions at once, no permlevel-restricted role
  - DocWeave-side serialization is not measured

## Rerun

As in Spike 0.1, but the last step becomes `../env/bin/python /workspaces/docweave/spikes/time_permission_check.py --site spike.localhost --out-suffix=-0-2` (from `~/frappe-bench/sites`, with `bash spikes/serve_rest.sh` running), about 45 minutes. It writes `spikes/results/permission-check-0-2.{json,md}`. Without a suffix the harness writes Spike 0.1's file names (`permission-check.json`, `permission-check-tables.md`).
