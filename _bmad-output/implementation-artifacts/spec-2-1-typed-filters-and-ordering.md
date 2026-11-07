---
title: 'Typed filters and ordering'
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

**Problem:** Clients can fetch a Sales Order by name, but they can't list documents or select them by criteria. Filters and sorts must never act on values the user can't see, because Frappe masks only returned values (FR-4, AD-6, AD-16).

**Approach:** Add a `<type>List(filter, orderBy)` root field returning a minimal connection, plus typed `<Type>Filter` and `<Type>Order` inputs. The planner builds a `FilterIR` and an `OrderKey`. `core.filter_hash` hashes the IR canonically. The adapter checks AD-6, translates the IR into criteria inside `_authorized_query`, and returns one page of candidates that passed AD-4. `first`, `after`, cursors and the scan budget come in 2.2 and 2.3.

## Boundaries & Constraints

**Always:**
- Schema, one per exposed DocType: `salesOrderList(filter: SalesOrderFilter, orderBy: SalesOrderOrder): SalesOrderConnection`, where `SalesOrderConnection { edges: [SalesOrderEdge!]!, pageInfo: PageInfo! }`, `SalesOrderEdge { node: SalesOrder! }` and `PageInfo { hasNextPage: Boolean! }`. The root field itself is nullable. All names come from `schema/naming.py`.
- `<Type>Filter { and: [<Type>Filter!], or: [<Type>Filter!], <field>: <Scalar>Ops }` covers every filterable field, standard fields included. The ops types are `StringOps`, `IntOps`, `LongOps`, `FloatOps`, `DecimalOps`, `BooleanOps`, `DateOps`, `DatetimeOps` and `TimeOps`. Each has `eq ne in nin lt lte gt gte isNull`, and only `StringOps` also has `like`. JSON, Text Editor, Markdown Editor, Code, Long Text, Table and `xDoc` fields are neither filterable nor orderable.
- `<Type>Order { field: <Type>OrderField!, direction: SortDirection! }`. The enum values are camelCase field names (`transactionDate`) whose internal value is the Frappe fieldname. The planner turns a missing `orderBy` into `OrderKey("creation", DESC)`. Only the adapter appends `name` in the same direction, and never twice.
- IR semantics: sibling keys and multiple operators are ANDed. `and: []` matches all, `or: []` matches none, `in: []` matches none and `nin: []` matches all. `isNull: true|false` means IS NULL or IS NOT NULL. An explicit `null` operand is `VALIDATION`. Scalars gain input coercion: Decimal from a string or number, Long from a string, Datetime with an offset converted to naive site time (without an offset it is taken as site time).
- `core/filter_hash.py`: `filter_hash(ir | None) -> str`, the sha256 of canonical JSON with type-tagged values. It normalizes Decimals, renders dates and datetimes as ISO, sorts and dedupes `IN`/`NIN` values, sorts children by their canonical form and flattens nested nodes of the same kind. Like all of `core/`, it imports nothing from Frappe or other DocWeave packages.
- AD-6: before any query in a `load` call, the adapter checks every connection's IR and order fields against 1.6's `readable_fields` and `masked_fields`. A connection that uses an unreadable or masked field gets `null` + `FORBIDDEN` and issues no query. Standard fields always pass.
- Only `_authorized_query` turns the IR into a pypika `Criterion` and passes it as `filters=`, so `get_query` ANDs it with the permission conditions. No Frappe-format filters cross the port or reach `get_query`: `_authorized_query` raises `TypeError` when `filter` isn't a `FilterIR` or `None`, or `order` isn't an `OrderKey` or `None`. Empty `or` and `in` become explicit false terms, never pypika's `EmptyCriterion` or `IN ()`.
- Users with `select` but not `read` get `edges: []` and `hasNextPage: false`, with no candidate query.
- A page is one `_authorized_query(filter, order, limit=max_page_size)`, then the AD-4 check for each candidate in order. Values come from the Stage 1 rows. `hasNextPage` is true iff the query returned `limit` rows. Selections under `node` plan as they do under `salesOrder` (1.7).

**Never:**
- No `first`, `after`, cursors, keyset, `endCursor`, `scanLimitReached` or scan budget (2.2, 2.3). No depth or cost rules (2.4).
- No filters on child-table fields or through Links. No multi-field `orderBy`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Slice | `filter:{status:{in:["Draft","To Deliver"]}, or:[{customer:{eq:"A"}},{grandTotal:{gt:"1000"}}]}`, `orderBy:{field:transactionDate, direction:DESC}` | `And(Cmp(status, IN, tuple), Or(...))`; matching rows ordered by `transaction_date DESC, name DESC` | N/A |
| Default order | no `orderBy` | `creation DESC, name DESC` | N/A |
| Empty sets | `or: []`; `in: []` / `and: []`; `nin: []`; `filter: {}` | no edges / all readable rows | N/A |
| LIKE escape | `name:{like:"SO\\_1%"}` | `\` escapes `_` | N/A |
| Wrong op or field | `like` on `docstatus`; filter on a Text Editor field; `eq: null` | none | `VALIDATION` |
| Masked filter or sort | masked user filters or sorts on the masked field | `salesOrderList: null` + `FORBIDDEN`; no query | N/A |
| Above permlevel | Sales User filters on `ignorePricingRule` | `FORBIDDEN`; no query | N/A |
| Aliases | `a:` with a forbidden filter, `b:` valid | `b` returns data | N/A |
| OR against permissions | User Permission on Customer; `or` matching orders of other customers | only permitted orders | N/A |
| Select-only | `select` without `read` | empty connection; `_authorized_query` not called | N/A |
| Datetime | `creation:{gte:"2026-10-01T00:00:00+02:00"}`, site in UTC | compared as naive `2026-09-30 22:00:00` | N/A |

</frozen-after-approval>

## Open Questions

- **Rejecting the request or the connection.** The epics say a forbidden filter rejects "the request". AD-5 says two aliased connections are independent. Options: per connection, as written above (siblings still return; this is what AD-5's alias test asserts) / the whole request gets `data: null` + `FORBIDDEN` (matches the epics' words; the epics or AD-5 change).
- **Geolocation.** It maps to the `JSON` scalar but isn't on the spine's non-filterable list. Options: not filterable, like JSON (no meaningless ops on JSON; this extends the spine's list) / filterable with `eq` on the JSON value (literal spine; equality on serialized JSON is fragile).
- Depends on the 1.7 question about failed nodes: a per-connection `FORBIDDEN` needs the port to return a `Sentinel` in place of a `Page`.
- Depends on the 1.6 question about the Currency fixture: the masked filter case uses whichever masked field 1.6 picks.

## Code Map

- `docweave/core/types.py` (1.2, 1.5) -- `LoadRequest` already has `filter`, `order`, `first` and `after`; `LoadKind.ROOT_CONNECTION` exists. `docweave/core/port.py` (1.5) -- `load` returns `Sequence[list[Row]]`; widen it here.
- `docweave/schema/builder.py`, `naming.py`, `fieldtypes.py`, `scalars.py` (1.3) -- the tag contract is `extensions["docweave"]`. Scalars do output coercion only; 1.3 defers input coercion to this story.
- `docweave/execution/planner.py`, `graph.py`, `executor.py` (1.5, 1.7) -- `plan(schema, document, operation_name, variables)` and `execute(schema, request, adapter)`. Neither takes `SettingsView` yet. Add it, because the planner needs `max_page_size`.
- `docweave/adapter/frappe_v16.py` (1.5–1.7) -- `_authorized_query(...)` currently requires `filter`, `order` and `after` to be `None`. `readable_fields` and `masked_fields(doctype, parenttype)` come from 1.6. `docweave/adapter/permission.py` (1.5) -- `can_read_doctype`, `readable`.
- `~/frappe-bench/apps/frappe/frappe/database/query.py:432` -- `apply_filters` passes a `Criterion` straight to `.where()`. `:333` -- `order_by=None` applies no ORDER BY. `query_builder/utils.py` `execute_query` parameterizes values, so MariaDB's default `\` LIKE escape applies.

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/core/types.py`, `core/port.py` -- `FilterOp`, `And`, `Or`, `Cmp` (`IN`/`NIN` values are tuples), `Direction`, `OrderKey`, and `Page(rows, edge_cursors, end_cursor, has_next_page, scan_limit_reached)`. `load` returns `Sequence[Page | list[Row]]` (plus a failure form, per the Open Question).
- [ ] `docweave/core/filter_hash.py` -- `filter_hash`.
- [ ] `docweave/schema/naming.py`, `fieldtypes.py`, `scalars.py`, `builder.py` -- list, filter, order and connection names; `NON_FILTERABLE`; input coercion; the types and root field. Tags: the root field `{"kind": "root_connection", "doctype"}`, filter and order inputs `{"fieldname"}`.
- [ ] `docweave/execution/planner.py`, `graph.py`, `executor.py`, `docweave/api.py` -- a `ROOT_CONNECTION` node whose identity fingerprints filter and order; IR building with the default order; connection assembly keyed by response key (`edges` and `node` may be aliased); `SettingsView` passed through.
- [ ] `docweave/adapter/frappe_v16.py` -- the AD-6 pre-check, `_to_criterion(table, ir)` (pypika only, called inside `_authorized_query` with the table it built), the resolved order, and `ROOT_CONNECTION` loading.
- [ ] `docweave/tests/test_filters.py` -- the matrix, with spies on `_authorized_query` and `get_query` asserting no query on `FORBIDDEN` or select-only.
- [ ] `docweave/tests/test_filter_hash.py` -- equivalence and difference cases.
- [ ] `docweave/tests/test_parity.py` -- list parity: for each fixture user, list membership equals `frappe.get_list` filtered by `has_permission`, over the first `max_page_size` rows.
- [ ] `docweave/tests/test_boundaries.py` -- a negative test for the import direction: `core/` imports no `frappe` and no `docweave` modules outside `core`, and `schema/` and `execution/` never import `docweave.adapter`.

**Acceptance Criteria:**
- Given two equivalent filters with different key or child order, duplicate `in` values, nested same-kind nodes, or `1.0` against `1`, when hashed, then the hashes are identical. Changing one op, value or value type changes the hash.
- Given the slice query, when it executes, then `_authorized_query` receives a `FilterIR` and an `OrderKey`, and `get_query` receives a `Criterion`, never a dict or list.
- Given a fixture user and `_authorized_query(..., filter={"status": "Draft"})`, when it is called, then it raises `TypeError`.

## Design Notes

`_to_criterion` gets `frappe.qb.DocType(doctype)` from `_authorized_query`, so `frappe.qb` stays inside the chokepoint (1.5's boundary rule). Because `get_query` gets a `Criterion` rather than Frappe filters, Frappe's own check on filter fields (the `PermissionError` for above-permlevel fields) doesn't run. The AD-6 pre-check is the only guard.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.

## Implementation Notes

## Spec Change Log

## Review Triage Log
