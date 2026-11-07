---
title: 'Links and child tables in one request, without N+1'
type: 'feature'
created: '2026-11-01'
status: 'draft'
baseline_commit: 'cd5c12665210c90e70229a728c76326a8c6e0bfe'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `customerDoc` and `items` still resolve to `null`, so a client needs several round trips to load one Sales Order screen. A naive per-row loader would cause N+1 queries and could inherit access from the parent (FR-4, FR-5, AD-3, AD-6, AD-7).

**Approach:** Extend the planner with `LINK` and `CHILDREN` nodes at any depth. The adapter loads each node in one batched `_authorized_query` call over all sibling source rows. Link targets get their own AD-4 check. Children load only under parents that passed the check. The assembler joins Links on `Row.matched_key`, and derived fields inherit their source field's sentinel.

## Boundaries & Constraints

**Always:**
- Plan node identity is `(doctype, parent_doctype, parentfield or link fieldname, argument fingerprint, path)`. Batching happens only across sibling rows of one node, never across nodes. Each alias is its own node.
- **Links.** Keys are the distinct non-empty source values from rows whose source field is a plain value. A source holding `MASKED` or `FORBIDDEN` gives `xDoc` the same sentinel, and that row contributes no key. An empty or NULL source gives `xDoc: null` with no error. The target goes through `_authorized_query(keys=...)` and then the AD-4 check for its own DocType; an unreadable target is `null` + `NOT_FOUND`. Each returned `Row` carries `matched_key`, the requested key the SQL matched, and the assembler joins only on it. The raw `x: String` follows only its own readability.
- **Children.** They load only for parent rows that passed AD-4, and only if the Table field's permlevel is in `meta.get_permlevel_access("read", user=...)`; otherwise the field is `FORBIDDEN` and nothing is loaded. The query passes `parent_doctype`, `parentfield` and `parent_names`, and selects `parent`, `parentfield` and `idx`. Rows are ordered by `idx ASC` within each parent, and masking uses the parent DocType (1.6's path with `parenttype`).
- If total child rows in a request exceed `max_child_rows`, the child field fails with `COST_LIMIT` on every parent and the parents still return. Nothing is ever truncated.
- Resolvers do no I/O. Queries for links and children are constant per plan node, whatever the number of source rows.

**Never:**
- No per-row loads. No string comparison in the assembler for Link joins. No load from a hidden source. Child DocTypes never become roots.
- No lists or connections (Epic 2). No Dynamic Link resolution.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Slice | `salesOrder{customerDoc{customerName} items{itemCode qty}}` | customer and items; items in `idx` order | N/A |
| Customer unreadable | can read the SO but not its Customer | `customerDoc: null` + `NOT_FOUND`; `customer` is the raw name | N/A |
| Masked source | `customer` masked | `customerDoc` `MASKED`; no Customer query | N/A |
| Forbidden source | `customer` above the user's permlevel (test Property Setter) | `customerDoc` `FORBIDDEN`; no query | N/A |
| Empty Link | `customer` empty | `customerDoc: null`, no error, no key sent | N/A |
| Case variant | `customer` stored as a case variant of the Customer name | still joined through `matched_key` | N/A |
| Unreadable Table field | `items` permlevel raised for the test | `items` `FORBIDDEN`; no child query | N/A |
| Masked child field | `rate` masked on Sales Order Item | `rate` `MASKED` per row | N/A |
| Child cap | `max_child_rows` = 2, order with 3 items | `items: null` + `COST_LIMIT`; other fields intact | N/A |
| Aliases | `c1: customerDoc{customerName}` and `c2: customerDoc{name}`; roots `a:` and `b:` on two orders | each alias resolves its own result | N/A |
| Link in child rows | `items{itemCodeDoc{itemName}}` with Item exposed | one batched Item load for all rows | N/A |

</frozen-after-approval>

## Open Questions

- **Query-count AC (1 to 50 orders).** v1's only root is `salesOrder(name:)`, and AD-3 forbids batching across nodes, so 50 orders means 50 aliased root nodes with 50 Link and 50 child queries. The constant count can't be shown across orders until `salesOrderList` (Story 2.2). Options: in 1.7, assert constancy over one order's rows, 1 to 50 items with `itemCodeDoc` (Item exposed in the test), plus a per-node bound (queries per node = 1 query + AD-4 checks), and move the 1-to-50-orders assertion into Story 2.2 (the epics change; the AD-3 property is proven now on child rows) / batch identical aliased roots into one node (the AC as written, but it breaks AD-3's node identity rule, so the spine changes).
- **How the adapter reports a failed node such as `COST_LIMIT`.** AD-16's port returns `Sequence[Page | list[Row]]`, with no way to fail one request while the others succeed. Options: allow a `Sentinel` in place of a result, `Sequence[Page | list[Row] | Sentinel]` (small and explicit; amends AD-16) / the adapter returns rows and the executor enforces `max_child_rows` after the load (no port change, but rows over the cap are fetched and masked before being discarded, and the limit moves out of the adapter).

## Code Map

- `docweave/execution/planner.py` (created in 1.5) -- `PlanNode` and `plan()`, with only `ROOT_ONE` so far. Add `LINK` and `CHILDREN` children here, from the builder tags `kind: "link_doc"` (with `fieldname` as the source Link fieldname and `target`) and `kind: "children"` (with `fieldname` as the parentfield and `target` as the child DocType). Those tags are created in 1.3.
- `docweave/execution/graph.py` (1.5) -- `assemble`: add joins and sentinel inheritance. `docweave/core/types.py` (1.5) -- add a `COST_LIMIT` sentinel; `Row.matched_key` already exists.
- `docweave/adapter/frappe_v16.py` (1.5, 1.6) -- `_authorized_query` already takes `keys`, `parent_doctype`, `parentfield` and `parent_names`. `readable_fields` and `masked_fields(doctype, parenttype)` come from 1.6. `docweave/adapter/permission.py` (1.5) -- `readable(doctype, names)` for Link targets.
- `~/frappe-bench/apps/frappe/frappe/query_builder/utils.py:136-160` -- masking matches by dict key after `run`, so an extra select term for `matched_key` (for example a `Case` per key on `name`) passes through untouched.
- `frappe.tests` `IntegrationTestCase.assertQueryCount` (`tests/classes/integration_test_case.py:122`).

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/execution/planner.py` -- `LINK` and `CHILDREN` nodes at any depth. Source fields are added to the parent node's fields.
- [ ] `docweave/adapter/frappe_v16.py` -- `LINK` (keys, `matched_key`, Stage 2 check) and `CHILDREN` (Table readability, `parent_names` limited to authorized parents, `idx` order, a per-request child-row counter against `max_child_rows`). `_authorized_query` applies `parent, idx ASC` itself whenever `parent_names` is given; its `order` parameter stays `None` until Epic 2.
- [ ] `docweave/execution/executor.py` -- load nodes breadth-first by depth: one `adapter.load` call per depth level, with all nodes of that level.
- [ ] `docweave/execution/graph.py` -- the joins, inheritance and `COST_LIMIT` placement described above.
- [ ] `docweave/tests/test_links_children.py` -- the matrix. Negative tests: assert no target or child query (spy on `_authorized_query`) for a masked or forbidden source and for an unreadable Table field.
- [ ] `docweave/tests/test_query_count.py` -- the query-count assertions per the Open Question. Spy on `_authorized_query` calls (constant) separately from AD-4 checks (linear in candidates).

**Acceptance Criteria:**
- Given the slice query, when it executes, then no resolver calls the adapter or Frappe (resolvers are spied).
- Given two different users, when they run the same nested query, then each sees only their own authorized Customer and items.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.
- Manual HTTP POST of the slice query as a Sales User -- expected: one round trip with customer and items.

## Implementation Notes

## Spec Change Log

## Review Triage Log
