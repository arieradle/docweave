---
title: 'All-or-nothing mutation requests'
type: 'feature'
created: '2026-11-01'
status: 'draft'
baseline_commit: 'cd5c12665210c90e70229a728c76326a8c6e0bfe'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

v2 backlog: not implemented in v1.

**Problem:** api.py's `finally` always rolls back (AD-12), so mutations from 3.1–3.3 never persist over HTTP. Simply removing the rollback would allow partial writes: a request whose second mutation fails would keep the first (FR-11, AD-9).

**Approach:** The transport owns the transaction. Mutations run in document order and stop at the first failure. The request's writes persist only when it is a mutation operation and every write succeeded; otherwise api.py rolls back as in v1. Write code never commits.

## Boundaries & Constraints

**Always:**
- Mutation root fields run in document order (after fragments and `@skip`/`@include`), one write at a time. Depth and cost checks for all payloads run before the first write.
- On the first failed write, no further write runs. Every mutation field in the request then resolves to `null` with an error: the failed one with its own code, the others per the Open Question. No payload is loaded.
- Commit only if the operation is a `mutation` and every write succeeded. A payload read that returns `NOT_FOUND` doesn't prevent the commit. An exception escaping `_run` (`INTERNAL`) rolls back.
- Query operations keep v1's guarantee: rollback in `finally`, always.
- One commit per request, after the response is built. Deferred `INTERNAL` log entries are still written after the rollback or commit decision, through `frappe.log_error(..., defer_insert=True)`.
- `frappe.db.commit` stays banned everywhere outside the transport rule chosen below; the boundary test proves it.

**Never:**
- No savepoints or per-mutation commits. No `frappe.db.commit` in `adapter/`, `execution/`, `schema/` or `core/`.
- Hooks that commit explicitly are out of scope (as in AD-12) and break all-or-nothing; this is documented, not prevented.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Second fails | `a: createCustomer(...)` ok, `b: createSalesOrder(...)` missing `customer` | `a: null` + rollback error, `b: null` + `VALIDATION`; neither row exists afterwards (checked from a fresh connection) | rollback |
| First fails | `a` fails `FORBIDDEN`, `b` valid | `b` never runs; both `null`; nothing persisted | rollback |
| All succeed | `a: createCustomer`, then `b: createSalesOrder` using `a`'s name | both persisted; `b`'s link validation sees `a` (document order) | commit once |
| Unreadable payload | `a` succeeds, `doc` unreadable | `a.name` set, `doc: null` + `NOT_FOUND`; committed | N/A |
| Query operation | a `query` whose `has_permission` hook writes a row | row not persisted | rollback |
| Cost breach | a payload selection over the cost limit | `COST_LIMIT`; no write runs | rollback |
| Unexpected error | write module raises `KeyError` | `INTERNAL`; nothing persisted; one deferred Error Log entry | rollback |

</frozen-after-approval>

## Open Questions

- **Who issues the commit.** The epics say "Frappe commits once"; AD-9 says "the transport owns the transaction". Options: api.py skips its rollback on success and Frappe's request end commits (`frappe/app.py:162`, `sync_database` commits every POST; no AD-1 change, but persistence depends on Frappe's request lifecycle and no commit happens when `_run` is called in-process) / api.py calls `frappe.db.commit()` itself before returning (explicit and testable in-process; adds `frappe.db.commit` to api.py's AD-1 allowlist; Frappe's later commit is then a no-op). Either way AD-12's read-only text needs a v2 amendment.
- **Errors for mutations that didn't fail themselves.** The AC wants every result `null` "with their errors", but no code fits a write that succeeded and was rolled back, or one never run. Options: a new `ABORTED` code for both (precise; amends `core`'s code list and Story 4.2's contract) / reuse `VALIDATION` with a message naming the failed field's path (no new code, but clients can't tell their own invalid input from someone else's) / `null` with no error for these (simplest; contradicts the AC).
- **`writes.py`.** The epics' "`writes.py` never commits" names a module the spine lacks. depends on 3.1 question: "Where write code lives". This story only adds the boundary assertion against whichever module is chosen.

## Code Map

- `docweave/api.py` (1.2) -- `graphql()`: gate, `_run(request, settings)`, `finally` with `frappe.db.rollback()`, deferred logs via `adapter.errors.take_deferred()`. `_run` must now also report the operation type and whether every write succeeded.
- `docweave/execution/executor.py`, `planner.py` (1.5, 3.1–3.3) -- `execute(schema, request, adapter)`, the ordered write plans. Add stop-on-first-failure and the per-field errors.
- write module (3.1, spec draft) -- `DataAdapter.write`; must stay commit-free.
- `docweave/tests/test_boundaries.py` (1.1, 3.1) -- `frappe.db.commit` banned everywhere since 3.1; adjust only per the first Open Question.
- `docweave/tests/utils.py` (1.2) -- HTTP helpers. `frappe/tests/test_api.py:41-90` `FrappeAPITestCase` runs each request on its own connection, so transaction tests must go over HTTP and clean up committed rows in `tearDown`.
- `~/frappe-bench/apps/frappe/frappe/app.py:150-162,438-448` -- on success `sync_database()` commits for POST; on an exception it rolls back.

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/execution/executor.py` -- serial writes, stop on first failure, error assignment per the second Open Question, return an outcome with `is_mutation` and `all_writes_ok`.
- [ ] `docweave/api.py` -- in `finally`: roll back unless `is_mutation and all_writes_ok`; commit per the first Open Question; then flush deferred logs.
- [ ] `docweave/tests/test_boundaries.py` -- assert no `frappe.db.commit` outside the chosen location.
- [ ] `docweave/tests/test_mutation_transactions.py` -- the matrix over HTTP; verify persistence by querying as Administrator after the response.

**Acceptance Criteria:**
- Given a successful two-mutation request, when `frappe.db.commit` and `insert` calls are spied in order, then no commit happens before or between the writes, and DocWeave issues at most one commit.
- Given the package, when `test_boundaries.py` runs, then `frappe.db.commit` in the write module fails.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.

## Implementation Notes

## Spec Change Log

## Review Triage Log
