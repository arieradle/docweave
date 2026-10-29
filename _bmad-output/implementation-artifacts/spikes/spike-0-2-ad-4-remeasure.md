# Spike 0.2: Re-measuring AD-4 with the review fixes

**Story:** 0.2 · **Date:** 2026-10-29 · **Decision:** **Confirm Spike 0.1's amendment: lower AD-4's default scan budget from 2,000 to 200 candidates.**

## Summary

- **The target holds at every budget.** Compared over an equal number of readable documents, DocWeave's warm p95 costs 0.52–0.60× REST's in the worst case of each budget, across all five users and all three order sizes (table below). When a page fills, the scan stops. And REST pays for denied documents too: its 100-row list includes them, and each of their GETs returns 403.
- **So the budget does not decide the target; it caps one request.** It bounds how long a single request can run for users who can read little of what the candidate query returns. A 2,000-candidate scan costs 6–26 s (Spike 0.1). At 200 the measured worst request is 1.9 s p95 for 100-item orders (200 candidates scanned, a short page of 94 returned). That is on par with one REST page for the same set, 1.8 s.
- **REST matches the full check exactly.** For every user and set, the REST list returned the same 100 names as `get_query`, with the same allow/deny answer per name (0 and 0 in all 15 cases).
- **The literal 100-row comparison** (one REST list plus its GETs, against DocWeave filling 100 readable documents) fails only for the warehouse user with 100-item orders, at budget 200 and above (1.06–1.26×). It fails because DocWeave returns about twice as many readable documents as that REST page does. The human chose the equal-readable reading for the target (spec decision).

## What changed from Spike 0.1

| | Spike 0.1 | Spike 0.2 |
|---|---|---|
| Budget value | 200 extrapolated from p50 per candidate | Fill-one-page passes measured at budgets 100, 150, 200, 300, 500 and 2,000 (3 cold, 10 warm trials each) |
| REST parity | assumed | REST list names and per-name allow/deny compared with the full check |
| REST cold | Redis cleared only; gunicorn workers kept warm caches | gunicorn HUPed before each cold trial, so its workers start fresh |
| DocWeave estimate | page p95 + ping p50 | page p95 + ping p95 (6.7 ms) |
| Fixture row names | random hashes | deterministic (`SPK-SO-100-0001-001`); same seed and the same restriction mix (196 / 229 / 203 shares) |

Everything else is as in [Spike 0.1](spike-0-1-permission-check.md): the same site, fixtures, users, method and target.

## Environment

| | |
|---|---|
| Frappe / ERPNext | v16.53.0 / v16.52.1 |
| MariaDB / Redis / Python | 11.8.9 / 7.4.12 / 3.14.10 |
| Hardware | GitHub Codespace, Intel Xeon Platinum 8370C @ 2.80 GHz, 2 cores, 7.8 GB RAM |
| REST server | gunicorn 23.0.0, gthread, 2 workers × 4 threads, `--preload` (`spikes/serve_rest.sh`) |
| HTTP round trip | p50 3.2 ms, p95 6.7 ms |
| Run | 2026-10-29, 21:05–21:47 UTC, nothing else running on the bench |
| Harness | `spikes/time_permission_check.py` at this story's commit; results in `spikes/results/permission-check-0-2.{json,md}` |

## The deciding numbers

### Equal readable documents: worst case per budget (all users and sets, warm p95)

| Budget | Worst ratio (DocWeave per returned doc ÷ REST per readable doc) | Where |
|---|---|---|
| 100 | 0.56 | customer, 100 items |
| 150 | 0.54 | warehouse, 100 items |
| 200 | 0.52 | customer, 100 items |
| 300 | 0.53 | warehouse, 100 items |
| 500 | 0.57 | warehouse, 100 items |
| 2000 | 0.60 | customer, 100 items |

### Equal readable documents: warehouse user (about 45–50% of candidates pass)

| Items | Budget | REST readable per page | REST ms per readable doc | DocWeave returned | DocWeave ms per returned doc | Ratio | Request p95 ms |
|---|---|---|---|---|---|---|---|
| 5 | 100 | 49 | 18.1 | 49 | 7.5 | 0.41 | 368 |
| 5 | 150 | 49 | 18.1 | 74 | 7.6 | 0.42 | 562 |
| 5 | 200 | 49 | 18.1 | 100 | 6.9 | 0.38 | 691 |
| 5 | 300 | 49 | 18.1 | 100 | 6.7 | 0.37 | 671 |
| 5 | 500 | 49 | 18.1 | 100 | 7.5 | 0.42 | 755 |
| 5 | 2000 | 49 | 18.1 | 100 | 7.1 | 0.39 | 709 |
| 20 | 100 | 50 | 21.5 | 50 | 9.7 | 0.45 | 486 |
| 20 | 150 | 50 | 21.5 | 77 | 8.9 | 0.42 | 689 |
| 20 | 200 | 50 | 21.5 | 100 | 9.1 | 0.42 | 908 |
| 20 | 300 | 50 | 21.5 | 100 | 8.7 | 0.40 | 870 |
| 20 | 500 | 50 | 21.5 | 100 | 9.0 | 0.42 | 898 |
| 20 | 2000 | 50 | 21.5 | 100 | 9.3 | 0.43 | 930 |
| 100 | 100 | 45 | 40.1 | 45 | 21.6 | 0.54 | 973 |
| 100 | 150 | 45 | 40.1 | 70 | 21.5 | 0.54 | 1508 |
| 100 | 200 | 45 | 40.1 | 94 | 20.4 | 0.51 | 1917 |
| 100 | 300 | 45 | 40.1 | 100 | 21.2 | 0.53 | 2121 |
| 100 | 500 | 45 | 40.1 | 100 | 22.8 | 0.57 | 2279 |
| 100 | 2000 | 45 | 40.1 | 100 | 21.6 | 0.54 | 2161 |

### Requests to walk 2,000 candidates (computed from pass rate, not run)

| Pass rate | Readable | Budget 100 | 150 | 200 | 300 | 500 | 2,000 |
|---|---|---|---|---|---|---|---|
| 100% | 2000 | 20 | 20 | 20 | 20 | 20 | 20 |
| 50% | 1000 | 20 | 14 | 10 | 10 | 10 | 10 |
| 20% | 400 | 20 | 14 | 10 | 7 | 4 | 4 |
| 5% | 100 | 20 | 14 | 10 | 7 | 4 | 1 |

### REST parity and the literal 100-row page (warm p95, 20 trials)


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

The full fill table (every user, set and budget, with cold p95) is in `spikes/results/permission-check-0-2.md`.

At pass rates under 50%, every page at budget 200 comes back short, so a client walking the result set makes more requests. Each request stays bounded at about 200 candidates.

## Decision for AD-4

**Confirm the amendment: lower the default scan budget from 2,000 to 200 candidates (2 × the maximum page of 100).**

- **The target is met at every budget.** At 200, the worst case over all users and sets is 0.52× REST per readable document.
- **200 bounds a single request** at about 1.9 s warm p95 (2.2 s cold) for 100-item orders on this machine, about one REST page. At 2,000 the worst request is 6–26 s. Going lower (100 or 150) makes requests faster but returns short pages even to users with a 50% pass rate. Going higher only lengthens the worst request: at 50% the page fills at about 220 candidates anyway.
- **Correctness does not change.** A short page carries `scanLimitReached` and a continuation cursor (FR-8, Story 2.3).

**Applying it** (still the item in `deferred-work.md`, for the human): the architecture's "Default limit values", Story 2.3's defaults and tests, and Story 1.2's `DocWeave Settings` default.

## Limitations

- These fixtures have no user with a pass rate far below 50%. The request-count table is computed, not measured, but the cost of one request at a budget does not depend on the pass rate: every scanned candidate costs one `get_doc` plus one `has_permission`.
- The REST side of the equal-readable comparison is the measured 100-row page divided by its readable documents. Fetching exactly 100 readable documents through REST (about 220 GETs) was not timed directly.
- Unchanged from Spike 0.1:
  - only the `items` child table is filled
  - no `has_permission` hook, no user with two User Permissions at once, no permlevel-restricted role
  - DocWeave-side serialization is not measured

## Rerun

As in Spike 0.1. The last step becomes `../env/bin/python /workspaces/docweave/spikes/time_permission_check.py --site spike.localhost --out-suffix=-0-2` (from `~/frappe-bench/sites`, with `bash spikes/serve_rest.sh` running), about 45 minutes.
