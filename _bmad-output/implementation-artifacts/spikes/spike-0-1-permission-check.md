# Spike 0.1: Cost of the per-candidate permission check (AD-4)

**Story:** 0.1 · **Date:** 2026-10-26 · **Decision:** **Amend AD-4: lower the default scan budget to 200 candidates.** Confirmed by measurement in [Spike 0.2](spike-0-2-ad-4-remeasure.md), reading the target as equal readable documents. Read literally (one REST 100-row page), 200 fails for the warehouse user with 100-item orders and 150 would be the budget.

## Summary

- **The check passes the target.** For a 100-document page at p95 with a warm cache, AD-4's check plus one HTTP round trip takes 0.31× to 0.84× the time of Frappe's REST equivalent, for every user and document size. The closest case is the warehouse-restricted user with 100-item orders: 1,893 ms against 2,246 ms.
- **The scan budget is the problem.** When a user's restrictions only show up in the document check, a short page can scan the full budget. At 2,000 candidates that costs 5.8–7.4 s for 5-item orders, 8–11 s for 20-item orders and 19–26 s for 100-item orders, warm. REST serves a whole 100-document page in 0.9–3.0 s.
- **Cost grows with document size, not query count.** About 8 queries per candidate in every case (1 parent plus 7 child tables; 10 for the shared user). For 100-item orders, building the child documents and running the User Permission check over every child row dominates.
- **The shortcut is wrong exactly where expected.** Checking a document built from the query row disagrees with the full check on about half the candidates for the user restricted by Warehouse on item rows (986–1,017 of 2,000), and allows all of them. It agreed for every other user. For the DocShare-only user that is close to automatic, because the candidate query already keeps only shared documents.
- **Preloading keeps full parity and helps small documents.** Reusing the `*` query row as the parent and loading the child tables in batches of 100 gave 0 disagreements. It cuts a 2,000-candidate scan by 2.6–5× for 5-item orders and 1.7–2.4× for 20-item orders, but by only about 7% for 100-item orders.

## Environment

| | |
|---|---|
| Frappe | v16.53.0 |
| ERPNext | v16.52.1 |
| MariaDB | 11.8.9 (Compose service, same host) |
| Redis | 7.4.12 |
| Python | 3.14.10 |
| Hardware | GitHub Codespace, Intel Xeon Platinum 8370C @ 2.80 GHz, 2 cores, 7.8 GB RAM |
| REST server | gunicorn 23.0.0, gthread, 2 workers × 4 threads, `--preload` |
| HTTP round trip | `/api/method/ping`: p50 3.0 ms, p95 7.1 ms |
| Run | 2026-10-26, 21:31–21:58 UTC, nothing else running on the bench |

All numbers are valid only for these versions and this hardware. A 2-core Codespace is slower than typical production, but every comparison here is relative and ran on the same machine.

## Method

**Fixtures** (`spikes/fixtures.py`, fixed seed, bulk-inserted):
- Three sets of 2,000 submitted Sales Orders with 5, 20 and 100 item rows each (10,000 / 40,000 / 200,000 item rows).
- 20 Customers, 4 Warehouses, 50 Items.
- Half the orders use Warehouse W1 on every item row; the other half mix in other Warehouses.
- 10% of orders are owned by the owner-only user, and about 10% are shared with the shared user.

**Users** (one per row of the spec's matrix):

| User | Access | Candidates the query returns (per set) |
|---|---|---|
| unrestricted | System Manager + Sales Manager | 2,000 |
| customer | Sales User, User Permission on one Customer | 100 |
| warehouse | Sales User, User Permission on Warehouse W1 | 2,000 (the query cannot see item rows) |
| owner | custom role with `read` + `if_owner` on Sales Order | 171–210 |
| shared | no Sales Order role, access only through DocShare | 196–229 |

**Measurements** (`spikes/time_permission_check.py`), per user and set:
- **AD-4 full check.** Candidates come from `frappe.qb.get_query(..., ignore_permissions=False, user=)`, ordered by name. Each candidate is timed through `frappe.get_doc` plus `frappe.has_permission(..., doc=doc, user=user)`. This is done over 100 and over 2,000 candidates.
- **Cold vs warm.** Cold clears the site's Redis cache and the in-process client cache before the pass. For the REST rows only Redis and the harness process are cleared: the gunicorn workers keep their in-process caches, so REST cold numbers are partly warm. Warm follows an unmeasured warm-up pass. Every pass starts a fresh Frappe request context. MariaDB's buffer pool is warm in both cases.
- **Trials.** For 100 candidates: 5 cold, 20 warm. For 2,000 candidates: 2 cold, 3 warm. Per-candidate p50/p95 pool every candidate across trials. Page p95 is taken across trials, so with 2–5 trials it is close to the maximum.
- **Query counts** per candidate come from wrapping `frappe.db.sql`, the pattern `IntegrationTestCase.assertQueryCount` uses.
- **REST target.** `GET /api/resource/Sales Order` for the same 100 names, then one `GET /api/resource/Sales Order/<name>` per document, as the same user over a keep-alive session. A 403 counts as denied.
- **DocWeave estimate.** The full-check page p95 plus one HTTP round trip at ping p50 (3.0 ms; p95 is 7.1 ms, a negligible difference), because DocWeave serves the page in one request. GraphQL parsing and serialization are not included, while REST pays for serializing 100 full documents.
- **Also measured** for comparison:
  - in-process `frappe.get_list` for the same page
  - the shortcut: `has_permission` on a document built from the `*` query row, with no load
  - the preload option: the `*` query row as the parent, all 7 child tables loaded per batch of 100 candidates, complete documents built in memory, then `has_permission`

## Results

All times in milliseconds. "Page p95" includes the candidate query.

### AD-4 full check (get_doc + has_permission) per candidate

| User | Items | Limit | Candidates | Allowed | Cache | p50 ms | p95 ms | Queries/candidate | Candidate query p95 ms | Page p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| unrestricted | 5 | 100 | 100 | 100 | cold | 3.13 | 42.64 | 8.8 | 491.1 | 3408 |
| unrestricted | 5 | 100 | 100 | 100 | warm | 2.36 | 3.76 | 8.0 | 7.5 | 307 |
| unrestricted | 5 | 2000 | 2000 | 2000 | cold | 2.88 | 12.04 | 8.0 | 324.4 | 12428 |
| unrestricted | 5 | 2000 | 2000 | 2000 | warm | 2.51 | 4.65 | 8.0 | 9.4 | 5834 |
| unrestricted | 20 | 100 | 100 | 100 | cold | 3.45 | 7.54 | 8.8 | 197.6 | 813 |
| unrestricted | 20 | 100 | 100 | 100 | warm | 3.02 | 5.27 | 8.0 | 6.5 | 413 |
| unrestricted | 20 | 2000 | 2000 | 2000 | cold | 3.54 | 6.81 | 8.0 | 212.3 | 8578 |
| unrestricted | 20 | 2000 | 2000 | 2000 | warm | 3.51 | 6.75 | 8.0 | 9.8 | 8312 |
| unrestricted | 100 | 100 | 100 | 100 | cold | 8.19 | 17.46 | 8.8 | 184.7 | 1404 |
| unrestricted | 100 | 100 | 100 | 100 | warm | 7.58 | 14.21 | 8.0 | 4.9 | 983 |
| unrestricted | 100 | 2000 | 2000 | 2000 | cold | 8.06 | 14.42 | 8.0 | 211.0 | 18795 |
| unrestricted | 100 | 2000 | 2000 | 2000 | warm | 8.12 | 14.51 | 8.0 | 9.1 | 18697 |
| customer | 5 | 100 | 100 | 100 | cold | 2.96 | 6.59 | 8.8 | 367.8 | 882 |
| customer | 5 | 100 | 100 | 100 | warm | 2.76 | 4.63 | 8.0 | 14.0 | 409 |
| customer | 5 | 2000 | 100 | 100 | cold | 3.55 | 7.98 | 8.8 | 223.8 | 728 |
| customer | 5 | 2000 | 100 | 100 | warm | 2.75 | 3.86 | 8.0 | 5.9 | 324 |
| customer | 20 | 100 | 100 | 100 | cold | 4.60 | 11.13 | 8.8 | 227.2 | 989 |
| customer | 20 | 100 | 100 | 100 | warm | 4.15 | 7.45 | 8.0 | 9.7 | 534 |
| customer | 20 | 2000 | 100 | 100 | cold | 4.13 | 6.46 | 8.8 | 228.9 | 745 |
| customer | 20 | 2000 | 100 | 100 | warm | 4.14 | 7.12 | 8.0 | 8.4 | 522 |
| customer | 100 | 100 | 100 | 100 | cold | 13.17 | 26.56 | 8.8 | 245.7 | 2038 |
| customer | 100 | 100 | 100 | 100 | warm | 12.70 | 23.68 | 8.0 | 9.6 | 1595 |
| customer | 100 | 2000 | 100 | 100 | cold | 12.74 | 23.54 | 8.8 | 253.0 | 1796 |
| customer | 100 | 2000 | 100 | 100 | warm | 12.83 | 24.01 | 8.0 | 10.8 | 1509 |
| warehouse | 5 | 100 | 100 | 49 | cold | 3.56 | 7.29 | 9.3 | 422.8 | 1131 |
| warehouse | 5 | 100 | 100 | 49 | warm | 3.32 | 5.36 | 8.5 | 10.8 | 443 |
| warehouse | 5 | 2000 | 2000 | 992 | cold | 3.49 | 6.09 | 8.5 | 207.5 | 7895 |
| warehouse | 5 | 2000 | 2000 | 992 | warm | 3.43 | 5.54 | 8.5 | 11.4 | 7384 |
| warehouse | 20 | 100 | 100 | 50 | cold | 4.23 | 8.08 | 9.3 | 383.1 | 1113 |
| warehouse | 20 | 100 | 100 | 50 | warm | 4.13 | 7.43 | 8.5 | 7.6 | 667 |
| warehouse | 20 | 2000 | 2000 | 983 | cold | 4.62 | 8.84 | 8.5 | 254.6 | 11281 |
| warehouse | 20 | 2000 | 2000 | 983 | warm | 4.62 | 8.48 | 8.5 | 11.2 | 10783 |
| warehouse | 100 | 100 | 100 | 45 | cold | 12.57 | 26.28 | 9.3 | 228.9 | 1827 |
| warehouse | 100 | 100 | 100 | 45 | warm | 12.27 | 24.94 | 8.6 | 7.2 | 1890 |
| warehouse | 100 | 2000 | 2000 | 1014 | cold | 12.83 | 21.57 | 8.5 | 252.8 | 26528 |
| warehouse | 100 | 2000 | 2000 | 1014 | warm | 12.94 | 21.12 | 8.5 | 9.0 | 26070 |
| owner | 5 | 100 | 100 | 100 | cold | 3.06 | 5.12 | 8.9 | 239.0 | 755 |
| owner | 5 | 100 | 100 | 100 | warm | 2.39 | 3.40 | 8.0 | 9.3 | 311 |
| owner | 5 | 2000 | 210 | 210 | cold | 2.53 | 3.61 | 8.4 | 161.9 | 809 |
| owner | 5 | 2000 | 210 | 210 | warm | 2.41 | 3.68 | 8.0 | 5.4 | 600 |
| owner | 20 | 100 | 100 | 100 | cold | 3.48 | 7.18 | 8.9 | 257.9 | 741 |
| owner | 20 | 100 | 100 | 100 | warm | 3.03 | 4.57 | 8.0 | 7.4 | 378 |
| owner | 20 | 2000 | 171 | 171 | cold | 3.17 | 5.62 | 8.5 | 197.9 | 925 |
| owner | 20 | 2000 | 171 | 171 | warm | 3.06 | 4.86 | 8.0 | 5.4 | 635 |
| owner | 100 | 100 | 100 | 100 | cold | 7.83 | 14.56 | 8.9 | 207.7 | 1339 |
| owner | 100 | 100 | 100 | 100 | warm | 7.77 | 17.88 | 8.0 | 11.7 | 1359 |
| owner | 100 | 2000 | 199 | 199 | cold | 8.25 | 18.62 | 8.5 | 214.6 | 2309 |
| owner | 100 | 2000 | 199 | 199 | warm | 7.85 | 14.55 | 8.0 | 11.9 | 1866 |
| shared | 5 | 100 | 100 | 100 | cold | 4.15 | 11.17 | 10.9 | 289.5 | 1010 |
| shared | 5 | 100 | 100 | 100 | warm | 3.88 | 6.12 | 10.0 | 32.4 | 519 |
| shared | 5 | 2000 | 196 | 196 | cold | 5.11 | 11.05 | 10.5 | 167.9 | 1496 |
| shared | 5 | 2000 | 196 | 196 | warm | 3.84 | 5.52 | 10.0 | 18.6 | 850 |
| shared | 20 | 100 | 100 | 100 | cold | 5.17 | 10.12 | 10.9 | 213.9 | 963 |
| shared | 20 | 100 | 100 | 100 | warm | 4.54 | 7.41 | 10.0 | 20.8 | 626 |
| shared | 20 | 2000 | 229 | 229 | cold | 5.32 | 10.44 | 10.4 | 193.9 | 1738 |
| shared | 20 | 2000 | 229 | 229 | warm | 4.54 | 6.78 | 10.0 | 31.0 | 1209 |
| shared | 100 | 100 | 100 | 100 | cold | 9.57 | 25.22 | 10.9 | 184.9 | 1772 |
| shared | 100 | 100 | 100 | 100 | warm | 9.05 | 16.51 | 10.0 | 23.7 | 1171 |
| shared | 100 | 2000 | 203 | 203 | cold | 9.98 | 22.53 | 10.5 | 185.3 | 2895 |
| shared | 100 | 2000 | 203 | 203 | warm | 9.34 | 17.10 | 10.0 | 31.3 | 2255 |

### Target: 100-document page, p95 warm (ms)

| User | Items | REST list + GETs | DocWeave check + 1 round trip | Ratio | get_list only | Shortcut page | Preload page |
|---|---|---|---|---|---|---|---|
| unrestricted | 5 | 987 | 310 | 0.31 | 5.4 | 26 | 89 |
| unrestricted | 20 | 1183 | 416 | 0.35 | 3.0 | 22 | 189 |
| unrestricted | 100 | 2253 | 986 | 0.44 | 2.6 | 17 | 747 |
| customer | 5 | 1055 | 412 | 0.39 | 10.3 | 82 | 129 |
| customer | 20 | 1259 | 537 | 0.43 | 8.2 | 63 | 342 |
| customer | 100 | 2967 | 1598 | 0.54 | 5.5 | 66 | 1414 |
| warehouse | 5 | 1065 | 446 | 0.42 | 6.3 | 41 | 168 |
| warehouse | 20 | 1289 | 670 | 0.52 | 5.1 | 34 | 337 |
| warehouse | 100 | 2246 | 1893 | 0.84 | 4.5 | 36 | 1059 |
| owner | 5 | 870 | 314 | 0.36 | 6.7 | 63 | 65 |
| owner | 20 | 1073 | 381 | 0.35 | 5.3 | 27 | 161 |
| owner | 100 | 2629 | 1362 | 0.52 | 5.7 | 44 | 1089 |
| shared | 5 | 1355 | 522 | 0.39 | 19.9 | 247 | 329 |
| shared | 20 | 1467 | 629 | 0.43 | 26.0 | 236 | 348 |
| shared | 100 | 2617 | 1174 | 0.45 | 18.5 | 244 | 928 |

### REST per-document GET (ms)

| User | Items | Cache | p50 | p95 | Page p95 |
|---|---|---|---|---|---|
| unrestricted | 5 | cold | 7.63 | 13.83 | 1424 |
| unrestricted | 5 | warm | 7.54 | 13.60 | 987 |
| unrestricted | 20 | cold | 9.38 | 19.45 | 1612 |
| unrestricted | 20 | warm | 9.02 | 16.58 | 1183 |
| unrestricted | 100 | cold | 19.05 | 36.29 | 2692 |
| unrestricted | 100 | warm | 18.67 | 34.20 | 2253 |
| customer | 5 | cold | 8.01 | 15.00 | 1211 |
| customer | 5 | warm | 7.90 | 14.00 | 1055 |
| customer | 20 | cold | 10.36 | 19.77 | 1534 |
| customer | 20 | warm | 10.28 | 18.93 | 1259 |
| customer | 100 | cold | 24.00 | 45.52 | 3094 |
| customer | 100 | warm | 23.89 | 44.85 | 2967 |
| warehouse | 5 | cold | 8.52 | 18.74 | 1383 |
| warehouse | 5 | warm | 8.44 | 15.87 | 1065 |
| warehouse | 20 | cold | 10.15 | 19.45 | 1424 |
| warehouse | 20 | warm | 10.15 | 18.32 | 1289 |
| warehouse | 100 | cold | 21.80 | 34.96 | 2522 |
| warehouse | 100 | warm | 21.53 | 32.86 | 2246 |
| owner | 5 | cold | 7.44 | 11.92 | 1081 |
| owner | 5 | warm | 7.42 | 12.05 | 870 |
| owner | 20 | cold | 9.14 | 14.41 | 1287 |
| owner | 20 | warm | 8.99 | 14.49 | 1073 |
| owner | 100 | cold | 21.03 | 38.02 | 2715 |
| owner | 100 | warm | 19.95 | 41.30 | 2629 |
| shared | 5 | cold | 10.03 | 21.04 | 1554 |
| shared | 5 | warm | 10.09 | 18.54 | 1355 |
| shared | 20 | cold | 11.75 | 22.81 | 1696 |
| shared | 20 | warm | 11.64 | 20.48 | 1467 |
| shared | 100 | cold | 21.28 | 43.89 | 2825 |
| shared | 100 | warm | 21.25 | 38.18 | 2617 |

### Parity with the full check over the scan budget (2,000 candidates, warm)

| User | Items | Candidates | Full allowed | Shortcut allowed | Shortcut disagreements | Preload allowed | Preload disagreements | Full p50/p95 ms | Shortcut p50/p95 ms | Preload p50/p95 ms | Full scan ms | Preload scan ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| unrestricted | 5 | 2000 | 2000 | 2000 | 0 | 2000 | 0 | 2.51 / 4.65 | 0.06 / 0.11 | 0.52 / 0.74 | 5771 | 1145 |
| unrestricted | 20 | 2000 | 2000 | 2000 | 0 | 2000 | 0 | 3.51 / 6.75 | 0.06 / 0.13 | 1.56 / 2.44 | 8156 | 3343 |
| unrestricted | 100 | 2000 | 2000 | 2000 | 0 | 2000 | 0 | 8.12 / 14.51 | 0.06 / 0.12 | 8.38 / 10.23 | 18653 | 17411 |
| customer | 5 | 100 | 100 | 100 | 0 | 100 | 0 | 2.75 / 3.86 | 0.15 / 0.32 | 0.74 / 1.24 | 311 | 102 |
| customer | 20 | 100 | 100 | 100 | 0 | 100 | 0 | 4.14 / 7.12 | 0.15 / 0.18 | 2.26 / 4.60 | 495 | 309 |
| customer | 100 | 100 | 100 | 100 | 0 | 100 | 0 | 12.83 / 24.01 | 0.34 / 0.40 | 10.99 / 17.30 | 1491 | 1274 |
| warehouse | 5 | 2000 | 992 | 2000 | 1008 | 992 | 0 | 3.43 / 5.54 | 0.14 / 0.30 | 1.40 / 2.16 | 7326 | 2810 |
| warehouse | 20 | 2000 | 983 | 2000 | 1017 | 983 | 0 | 4.62 / 8.48 | 0.14 / 0.29 | 2.72 / 4.44 | 10707 | 6150 |
| warehouse | 100 | 2000 | 1014 | 2000 | 986 | 1014 | 0 | 12.94 / 21.12 | 0.14 / 0.28 | 12.77 / 18.81 | 25980 | 24155 |
| owner | 5 | 210 | 210 | 210 | 0 | 210 | 0 | 2.41 / 3.68 | 0.06 / 0.09 | 0.39 / 0.81 | 576 | 124 |
| owner | 20 | 171 | 171 | 171 | 0 | 171 | 0 | 3.06 / 4.86 | 0.06 / 0.08 | 1.17 / 1.33 | 609 | 228 |
| owner | 100 | 199 | 199 | 199 | 0 | 199 | 0 | 7.85 / 14.55 | 0.06 / 0.08 | 8.64 / 10.27 | 1833 | 1674 |
| shared | 5 | 196 | 196 | 196 | 0 | 196 | 0 | 3.84 / 5.52 | 1.49 / 2.05 | 1.88 / 2.47 | 847 | 411 |
| shared | 20 | 229 | 229 | 229 | 0 | 229 | 0 | 4.54 / 6.78 | 1.49 / 2.09 | 2.78 / 3.70 | 1190 | 718 |
| shared | 100 | 203 | 203 | 203 | 0 | 203 | 0 | 9.34 / 17.10 | 1.51 / 2.58 | 8.92 / 12.23 | 2248 | 1954 |

## Findings

1. **Against REST, the full check is not the bottleneck.** REST pays one HTTP request per document, about 7–24 ms each at p50. AD-4 pays 2.4–13 ms per candidate in process. For a full 100-candidate page, AD-4 wins in every case.
2. **The comparison flatters AD-4 for heavily restricted users.** With the warehouse restriction, only 45–50 of 100 candidates pass. REST should return the same 45–50 documents for its 100-row list, since it uses the same filters and order, so the comparison should be fair for equal data. That is not verified per name in this run. But a DocWeave page that must *fill* 100 rows keeps scanning, about 220 candidates here, which costs about 4 s for 100-item orders against REST's 2.2 s.
3. **Worst case is the full scan budget.** A user who can read almost nothing that the query lets through (child-row User Permissions, `has_permission` hooks) makes every short page scan the whole budget. At 2,000 candidates that is 5.8–26 s warm on this machine, and 8–27 s cold. That fails the "on par with REST" bar by 6–12×.
4. **Cold cost is mostly in the first query.** Cold candidate queries take 160–490 ms (metadata and permission caches being rebuilt). Per-candidate cold cost is up to about 33% over warm at p50 for small documents. The first configuration measured (unrestricted, 5 items, 100 candidates: cold page 3.4 s) also pays one-off process start-up.
5. **Shortcut parity.** The architecture rejected the shortcut for three reasons: child-row User Permissions, DocShare and permlevel-hidden fields. Only the first shows up as wrong allow/deny answers on these fixtures. For DocShare the shortcut agreed on every candidate, but this test can hardly fail: the candidate query already keeps only shared documents, and `has_permission` looks shares up by document name. Permlevel-hidden fields affect which values are returned, not allow/deny, so this test can't show them. The child-row case alone is enough to keep the rejection.
6. **Preload is exact, but its speed-up depends on document size.** It cut queries from 8–10 per candidate to 0.07–2.1, and gave 0 disagreements in all 15 cases. The speed-up shrinks as documents grow: the remaining cost is Python building child documents and `has_permission` looping over every child row's link fields (about 4 ms of the 13 ms for 100-item orders with a User Permission; under 0.1 ms without one; from a separate cProfile run over 200 candidates, not from the harness). Preload's queries per candidate (0.07–2.1) are in `permission-check.json`, not in the tables.

## Decision for AD-4

**Amend: lower the default scan budget to 200 candidates (2 × the maximum page of 100).** Story 0.2 measured it and confirmed it; see [Spike 0.2](spike-0-2-ad-4-remeasure.md). The extrapolation below is kept as originally written.

- The per-candidate check itself meets the target, so AD-4's two-stage design and full-parity check stay as they are.
- What fails is the default budget, which the architecture already marks `[ASSUMPTION]`, to be tuned in the first slice.
- The value 200 is **extrapolated, not measured.** At p50 per candidate, a worst-case 200-candidate page costs about 0.7 s for 5-item orders and about 2.6 s for 100-item orders. At p95, which is what the target uses, the warehouse user with 100-item orders comes to about 4.2 s against that user's REST page of 2.2 s, so 200 may still miss the target for large documents. Story 0.2 measures a fill-one-page pass at budgets 200 and 2,000 at p95. It either confirms 200 or names the budget, or the other amendment, that meets the target.
- A lower budget bounds the cost of **one request**, not of walking the whole result set. A user who can read few of the candidates still pays for every candidate, spread over more requests. With a pass rate under 50%, a 200-candidate budget always returns short pages of 100.
- Correctness does not change. Hitting the budget already returns a short page with `scanLimitReached` and a continuation cursor (FR-8, Story 2.3). Heavily restricted users get more, smaller pages.

**Changes to make:** architecture "Default limit values" (scan budget 200); Story 2.3's defaults and tests; the `DocWeave Settings` default in Story 1.2.

**Not chosen, for Epic 1 to revisit:**
- **Preloading** keeps exact parity and would let a larger budget hold for small documents. It doesn't fix the 100-item worst case, and it adds a batch loader to `adapter/permission.py`. It's worth considering as an optimization once the budget is in place.
- **The hybrid check** would only speed up users who already pass the target. It also puts a security-sensitive classification ("does this DocType have hooks or child-row User Permission links for this user?") on the critical path.

## Rerun

On the Story 0.0 bench (Frappe v16.53.0, ERPNext v16.52.1), from the repository root:

1. `bash spikes/setup_site.sh` creates `spike.localhost` with ERPNext and completes the setup wizard. Safe to rerun.
2. `cd ~/frappe-bench/sites && ../env/bin/python /workspaces/docweave/spikes/fixtures.py --site spike.localhost` loads the fixtures in about 3 minutes and skips anything already present.
3. Stop `bench start` if it is running, and don't open port 8001 in a browser during the run.
4. In a second terminal: `bash spikes/serve_rest.sh` (gunicorn on 127.0.0.1:8001).
5. `cd ~/frappe-bench/sites && ../env/bin/python /workspaces/docweave/spikes/time_permission_check.py --site spike.localhost` takes about 27 minutes. It writes `spikes/results/permission-check.json` and `permission-check-tables.md`. Add `--resume` to continue after a failure, or `--quick` for a short smoke run.

The numbers in this report come from the harness as committed in `d3f4520`. The harness in `spikes/` now also carries the review fixes for Story 0.2: a fill-one-page pass, the REST name and allow/deny comparison, gunicorn workers restarted before cold REST trials, ping p95, and deterministic fixture row names. Those fixes have not been run yet.

## Limitations

- The fixtures fill only the `items` child table. Taxes, payment schedule, sales team and packed items are empty, so `get_doc` and the child-row permission loop are cheaper than on real orders.
- No fixture user has a `has_permission` hook, two User Permissions at once, or a permlevel-restricted role. Hooks are named above as a worst-case driver, but they were not measured.
- REST does not return the same 100 names checked against the full check's allow/deny per name. The two use the same filters and order, but this run did not verify it (Story 0.2 does).
- DocWeave-side serialization is not measured.

Spike code is throwaway: it lives in `spikes/`, outside any app package, and is never shipped.
