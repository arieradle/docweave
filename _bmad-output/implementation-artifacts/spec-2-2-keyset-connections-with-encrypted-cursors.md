---
title: 'Keyset connections with encrypted cursors'
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

**Problem:** After 2.1, a list returns only its first page and can't be continued. Offsets or readable cursors would skip or repeat rows under concurrent writes, and could leak names, sort values or users (FR-8, FR-9, AD-8).

**Approach:** Add `first` and `after`, edge `cursor`, and `pageInfo.endCursor` and `scanLimitReached`. A new `adapter/cursor.py` owns Fernet encoding bound to user, DocType, filter hash and resolved order, plus the keyset predicate. The adapter scans one chunk of `first` candidates after the cursor position. Story 2.3 replaces that one-chunk limit with the scan budget.

## Boundaries & Constraints

**Always:**
- Schema: `salesOrderList(filter, orderBy, first: Int, after: String)`, `SalesOrderEdge { cursor: String!, node: SalesOrder! }` (Relay's connection spec makes the edge cursor non-null), and `PageInfo { hasNextPage: Boolean!, endCursor: String, scanLimitReached: Boolean! }`.
- If `first` is omitted it is `max_page_size`. A `first` below 1 or above `max_page_size` is `VALIDATION` for that connection. The planner raises it before any adapter call.
- Cursor payload: `{v: 1, doctype, filter_hash, order, user, position}`. `order` is the resolved order, tie-break included. `position` is the last checked row's sort value and `name`, type-tagged (`Decimal`, `date`, `datetime`, `timedelta`, `str`, `int`, `float`, `None`). The key is `urlsafe_b64encode(HKDF(SHA256, length=32, salt=None, info=b"docweave-cursor-v1").derive(get_encryption_key().encode()))`. Decoding uses `Fernet.decrypt(token, ttl=86400)`.
- Any decode failure returns `BAD_CURSOR` for that connection before its query, with one message that doesn't say which check failed. Failures include an invalid or expired token, bad JSON or shape, `v != 1`, and a mismatch in DocType, user (`frappe.session.user`), `filter_hash` or order.
- `KeysetPosition` is private to `adapter/cursor.py`. Cursors cross the port only as strings. `keyset_criterion(table, order, position)` builds an explicit OR expansion with `IS NULL` branches. In ASC, NULLs come first: after NULL it is `(f IS NULL AND name > n) OR f IS NOT NULL`. In DESC, NULLs come last. There is no row-tuple comparison and no Python-side comparison of values.
- One chunk: `_authorized_query(filter, order, after=position, limit=first)`, then the AD-4 check for every fetched candidate in order.
  - Each edge cursor encodes its own row's position. `endCursor` is the last checked candidate.
  - `hasNextPage` is true iff the chunk returned `first` rows. Otherwise candidates are exhausted: `hasNextPage: false`, `endCursor: null`.
  - `scanLimitReached` = `hasNextPage` and fewer than `first` edges.
- A `BAD_CURSOR` or `VALIDATION` connection is `null` plus the code. Aliased siblings still return.
- `cryptography~=50.0.0`, Frappe's pin, is declared in `pyproject.toml`.

**Never:**
- No multi-chunk fill and no `scan_budget` (2.3). No `MultiFernet` or key epochs (v2). No offsets. No multi-field `orderBy`.
- Never log or echo cursor contents.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Shape | `first: 20` | `edges { cursor node }`, `pageInfo { hasNextPage endCursor scanLimitReached }` | N/A |
| Opaque | base64url-decode `endCursor` | no SO name, sort value or user email in the bytes | N/A |
| Replay | user B uses user A's cursor | none | `BAD_CURSOR` |
| Changed binding | same cursor with another filter, order or DocType | none | `BAD_CURSOR` |
| Expired | token made with `encrypt_at_time` 24 h + 1 s ago | none | `BAD_CURSOR` |
| Tampered | one byte flipped; garbage; site key patched | none | `BAD_CURSOR` |
| Ties | 30 orders with equal `transaction_date`; `first: 7`, ASC and DESC | each exactly once, `name` in the same direction | N/A |
| NULLs | some `delivery_date` NULL; ASC and DESC | each exactly once; NULLs first in ASC, last in DESC | N/A |
| Resume mid-page | `after: edges[3].cursor` | starts at the fifth row | N/A |
| `first` out of range | `max_page_size + 1`; `0` | that connection only; adapter gets no request for it | `VALIDATION` |
| Aliases | `a:` with a tampered cursor, `b:` valid | `b` returns data | N/A |
| Short page | 20 candidates, 5 readable (hook) | 5 edges, `scanLimitReached` and `hasNextPage` true, `endCursor` = 20th candidate | N/A |
| Exhausted | last chunk returns fewer than `first` | `hasNextPage: false`, `endCursor: null` | N/A |

</frozen-after-approval>

## Open Questions

- Depends on the 1.7 question about failed nodes: per-connection `BAD_CURSOR` needs the port to return a `Sentinel` in place of a `Page`.
- Depends on the 1.7 question about the query-count AC: if 1.7 moves "constant query count over 1–50 orders" here, the query-count task below stays. If 1.7 batches aliased roots instead, delete that task.

## Code Map

- `docweave/core/types.py`, `core/port.py`, `core/filter_hash.py` (2.1) -- `Page`, `OrderKey`, `filter_hash`. `LoadRequest.after: str | None` (1.5).
- `docweave/adapter/frappe_v16.py` (1.5, 2.1) -- `_authorized_query` already takes `after`, which must be `None` until this story. The resolved order and `_to_criterion` come from 2.1. `docweave/adapter/permission.py` (1.5) -- `readable(doctype, names)`.
- `docweave/execution/planner.py`, `graph.py` (2.1) -- the `ROOT_CONNECTION` node and connection assembly.
- `~/frappe-bench/apps/frappe/frappe/utils/password.py:223` -- `get_encryption_key()` returns a Fernet key string from site config.
- `cryptography` 50.0.2 in the bench env -- `cryptography.hazmat.primitives.kdf.hkdf.HKDF`; `Fernet.decrypt(token, ttl)`, `encrypt_at_time` (for tests).
- MariaDB orders NULLs first in ASC and last in DESC natively, so `ORDER BY` needs no NULLS clause. Time fields come back as `timedelta`.

## Tasks & Acceptance

**Execution:**
- [ ] `pyproject.toml` -- add `cryptography~=50.0.0`.
- [ ] `docweave/adapter/cursor.py` -- `encode(doctype, filter_hash, order, user, position) -> str`, `decode(token, *, doctype, filter_hash, order, user) -> KeysetPosition` (raises `DocWeaveError(BAD_CURSOR)`), `keyset_criterion(table, order, position)`.
- [ ] `docweave/adapter/frappe_v16.py` -- decode `after` before any query in the `load` call; apply `keyset_criterion` inside `_authorized_query`; build the `Page` as above.
- [ ] `docweave/schema/builder.py` -- the new arguments and fields.
- [ ] `docweave/execution/planner.py`, `graph.py` -- the `first` default and range check; `first` and `after` in the node fingerprint; edge cursors and `pageInfo` placed by response key.
- [ ] `docweave/tests/test_pagination.py` -- the matrix, plus full walks in both directions over every orderable standard field, with randomized ties and NULLs. The union of the walk must equal `get_list` filtered by `has_permission`, with no duplicates.
- [ ] `docweave/tests/test_query_count.py` -- `salesOrderList(first: N){edges{node{customerDoc{customerName} items{itemCode}}}}` for N = 1, 10 and 50: `_authorized_query` calls stay constant (3), and AD-4 checks grow linearly.
- [ ] `docweave/tests/test_boundaries.py` -- `frappe.utils.password.get_encryption_key` passes in `adapter/cursor.py` and fails in `execution/`.

**Acceptance Criteria:**
- Given a cursor decoded by a test, when its plaintext is inspected, then `position` is the last AD-4-checked candidate, never a fetched-but-unchecked row.
- Given `BAD_CURSOR` or `VALIDATION` on one connection, when the request runs, then `_authorized_query` is never called for that connection (spied).

## Design Notes

In this story the scan limit is `first`, so one request checks at most `max_page_size` candidates, under the default budget of 200. 2.3 swaps in the budget-bounded fill loop without changing the cursor format.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.

## Implementation Notes

## Spec Change Log

## Review Triage Log
