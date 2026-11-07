# Epic 2 Context: Listing, filtering and safe pagination

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Extend DocWeave's read path from single documents to lists. Clients query `<type>List` connections with typed filters and ordering, and page through large result sets with opaque, encrypted cursors. The hard case is a user who can read only a few of thousands of candidates: pages must come back short with a continuation cursor instead of stalling or erroring, every readable row must appear exactly once, nothing hidden may leak through filters, sorting or cursors, and every request stays within depth and cost limits. This serves integrators (predictable typed queries) and AI-agent or tool builders (bounded, introspectable queries).

## Stories

- Story 2.1: Typed filters and ordering
- Story 2.2: Keyset connections with encrypted cursors
- Story 2.3: Scan budget and short pages
- Story 2.4: Depth and cost limits

## Requirements & Constraints

- List queries support typed filters, field selection, links and child tables, all through the same authorized read path and document check as Epic 1.
- Cursor pagination. Hitting the scan budget returns a short page with `scanLimitReached: true` and a continuation cursor, never an error.
- The cursor marks the last scanned (permission-checked) candidate, is bound to user, filter and order, and is issued even when a page has no edges but candidates remain.
- `hasNextPage` is conservative: `false` only when candidates are known to be exhausted.
- Introspection works, bounded by depth and cost limits. Errors carry actionable messages and machine-readable codes (`FORBIDDEN`, `BAD_CURSOR`, `VALIDATION`, `DEPTH_LIMIT`, `COST_LIMIT`).
- Success: pagination over a long run of unauthorized records terminates and checks each candidate once. Testing priority is permissions, masking, then cursor correctness; every rule needs a negative test.

## Technical Decisions

- **Root field.** `salesOrderList(filter: SalesOrderFilter, orderBy: SalesOrderOrder, first: Int, after: String): SalesOrderConnection`. Connections are `edges { cursor node }` and `pageInfo { hasNextPage endCursor scanLimitReached }`; `edges`, `node`, `pageInfo` and its booleans are non-null. Two aliased connections must be independent: one failing must not null the other.
- **Filter input.** `<Type>Filter { and, or, <field>: <ScalarOps> }`. Sibling keys and multiple operators are ANDed. Empty `and` matches all, empty `or` matches none, `in: []` matches none, `nin: []` matches all. `like` is String-only with `\` as escape. JSON, Text Editor, Markdown Editor, Code and Long Text are neither filterable nor orderable. Standard fields (`name`, `owner`, `creation`, `modified`, `modifiedBy`, `docstatus`) are filterable and orderable.
- **FilterIR (in `core/types.py`).** `And(children) | Or(children) | Cmp(fieldname, op, value)`, ops `EQ NE IN NIN LT LTE GT GTE LIKE IS_NULL`. Values are typed Python values (`Decimal`, `date`, naive site-time `datetime`, `str`, `int`, `bool`, tuples for `IN`/`NIN`). The planner builds the IR; only the adapter translates it into qb criteria. No Frappe-format filters cross the port.
- **filter_hash.** `core.filter_hash` is the only hash function: canonical JSON that normalizes Decimals and Datetimes, sorts and dedupes `IN` values, sorts children and flattens nested same-kind nodes, so equivalent filters hash identically.
- **No filtering or sorting on hidden data.** Before any query runs, a filter or `orderBy` field that is masked or unreadable for the user is rejected with `FORBIDDEN`. This is required: Frappe masks only returned values, so filters and sorts would otherwise act on real hidden values.
- **Ordering.** `orderBy` takes one field and a direction (`OrderSpec`, as given by the client). The adapter alone appends `name` in the same direction as tie-break. No `orderBy` resolves to `creation DESC, name DESC`. The resolved order is always encoded in the cursor.
- **Keyset predicate.** Explicit OR expansion with `IS NULL` branches, not a row-tuple comparison. NULLs sort first in ASC and last in DESC.
- **Cursor.** Fernet authenticated encryption; key HKDF-derived from `frappe.utils.password.get_encryption_key()` with info `docweave-cursor-v1`; TTL 24 h via `Fernet.decrypt(token, ttl=86400)`. Payload `{v, doctype, filter_hash, order, user, position}`. Decrypt failure, expiry, or a user, filter or order mismatch returns `BAD_CURSOR`. Cursors cross the port only as opaque strings; `KeysetPosition` is private to `adapter/cursor.py`. A site-key change invalidates all cursors (accepted). Uses `cryptography ~=50.0.0` as pinned by Frappe.
- **Scan budget.** "Scanned" means checked through the per-candidate document check (`get_doc` plus `has_permission`). The adapter fetches candidates in chunks; `position` is the last checked candidate. The budget applies per connection occurrence, is never client-set, and defaults to 200 (measured in Spikes 0.1/0.2; it bounds one request, not the whole walk). Select-only users get an empty connection without scanning.
- **Page info.** Each edge cursor encodes that row's position. `endCursor` encodes the last checked position and may lie beyond the last edge; clients continue from `endCursor`. On budget exhaustion: `scanLimitReached: true`, `hasNextPage: true`, and `endCursor` differs from `after`. `hasNextPage` is decided only from checked candidates, never by peeking. On known exhaustion: `hasNextPage: false`, `endCursor: null`. `first` above the maximum page size (default 100) is `VALIDATION`.
- **Port.** `LoadRequest` kind `ROOT_CONNECTION` carries filter, order, first and after; the adapter returns a `Page(rows, edge_cursors, end_cursor, has_next_page, scan_limit_reached)`.
- **Depth limit.** A graphql-core validation rule counting object-typed field levels only (`edges` and `node` don't count). `__schema` and `__type` are exempt and bounded by graphql-core's `MaxIntrospectionDepthRule`. Default 8; breach is `DEPTH_LIMIT` naming the limit.
- **Cost limit.** Computed once by `execution.rules.estimate_cost(plan)`, after variables are bound and before any adapter call. `rows(node) = rows(parent) × local(node)`; `local` is `first` (or max page size) for a connection, `child_fanout_estimate` (default 50) for a child table, 1 for a link or single get. `cost = Σ rows(node) × scalar leaf fields selected`; `__typename` and connection wrappers cost 0. The formula is published in the `Query` type's SDL description. Breach is `COST_LIMIT` naming the limit and the estimate.
- All limits come from DocWeave Settings via `SettingsView`; `execution/` never imports `adapter/`.

## Cross-Story Dependencies

- Builds on Epic 1: `_authorized_query`, the document check, masking sentinels, the planner and result-graph assembly, `SettingsView` limits, and the error codes in `core`.
- 2.1 supplies `FilterIR`, `OrderSpec`, the resolved order and `filter_hash`, which 2.2's cursor binds to.
- 2.3 depends on 2.2's cursor and keyset predicate, plus Epic 1's per-candidate check.
- 2.4 needs the planner from Epic 1 and the connection shape from 2.2 to estimate cost.
- Accepted residual: `scanLimitReached` can reveal that many hook-rejected documents match a filter range.
