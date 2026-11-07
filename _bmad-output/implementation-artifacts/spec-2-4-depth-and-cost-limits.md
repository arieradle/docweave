---
title: 'Depth and cost limits'
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

**Problem:** Nothing bounds how deep or how expensive a request is. A client or AI agent can nest links and child tables, or ask for many large connections, and DocWeave only finds out while loading (FR-12, FR-14, AD-10).

**Approach:** Add a depth validation rule, built per request from `max_depth`, alongside graphql-core's `MaxIntrospectionDepthRule`. Add `execution.rules.estimate_cost(plan)`, which runs after planning and before any adapter call, checked against a new `max_cost` setting. Publish the formula in the `Query` type's description.

## Boundaries & Constraints

**Always:**
- **Depth** counts object-typed field levels. `edges` and `node` inside a connection don't count; every other object-typed field does, `pageInfo` included. The count follows fragment spreads and inline fragments (each fragment visited once per path) and ignores `@skip`/`@include`, which makes it conservative. `__schema` and `__type` subtrees are skipped.
  - A breach gives `DEPTH_LIMIT` with the message `Query depth {d} exceeds the limit of {max_depth}`, during validation, before variables are bound or a plan is built.
  - Validation runs graphql-core's `specified_rules` plus `MaxIntrospectionDepthRule` plus the depth rule. Errors from those two limit rules carry `DEPTH_LIMIT`. Every other validation error keeps `VALIDATION`.
- **Cost** is `estimate_cost(plan) -> int` in `execution/rules.py`, computed once after variables are bound:
  - `rows(node) = rows(parent) × local(node)`;
  - `local(node)` is the bound `first` for a connection (`max_page_size` if omitted), `child_fanout_estimate` for children, and 1 for a Link or a single get;
  - `cost = Σ rows(node) × the scalar leaf fields the client selected on node`.
  - `__typename`, `cursor`, `pageInfo` fields and source fields the planner adds cost 0. A connection already failed with `VALIDATION` adds 0.
- A cost breach gives `{"data": null, "errors": [COST_LIMIT]}` with the message `Estimated cost {c} exceeds the limit of {max_cost}`, and `DataAdapter.load` is never called.
- `max_cost` is a new DocWeave Settings Int with its default, validated `>= 1` like the other limits. It is carried as `SettingsView.max_cost`. A patch sets the default on sites whose saved Settings lack it.
- The `Query` description publishes the formula and the current `max_depth`, `max_cost`, `max_page_size` and `child_fanout_estimate`. The schema stays user-independent, and Settings `modified` already rebuilds it (1.4).
- `execution/` reads limits only from `SettingsView` and never imports `adapter/`.

**Never:**
- No per-user limits, no runtime (post-load) cost accounting and no persisted operations.
- No change to `max_child_rows` handling (1.7).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Introspection | `graphql.get_introspection_query()` at `max_depth` 8, and at 2 | succeeds | N/A |
| Deep introspection | `__schema{types{fields{type{fields{type{fields{name}}}}}}}` | none | `DEPTH_LIMIT` (`MaxIntrospectionDepthRule`) |
| Too deep | 9 object levels through `customerDoc` and `items`, Item exposed | none; planner not called | `DEPTH_LIMIT`, message names 8 |
| Hidden in a fragment | the same depth through named and inline fragments | none | `DEPTH_LIMIT` |
| Wrappers | `salesOrderList{edges{node{...}}}` at exactly 8 counted levels | passes | N/A |
| Cost math | `salesOrderList(first:10){edges{node{name grandTotal items{itemCode qty} customerDoc{customerName}}}}`, fanout 50 | 10×2 + 500×2 + 10×1 = 1030 | N/A |
| Variable `first` | `$n` bound to 100 | uses 100 | N/A |
| Omitted `first` | no `first` | uses `max_page_size` | N/A |
| Zero-cost fields | add `__typename`, `cursor`, `pageInfo{...}` | estimate unchanged | N/A |
| Aliases | two aliased connections | both summed | N/A |
| Over limit | estimate > `max_cost` | `data: null`; `load` not called | `COST_LIMIT`, message names the limit and the estimate |
| Bad setting | save `max_cost` 0 | rejected | `ValidationError` |

</frozen-after-approval>

## Open Questions

- **Default `max_cost`.** Neither the spine's "Default limit values" nor Story 1.2 has a cost limit. For scale, a 100-row page with 10 scalars and a 10-scalar child table costs 51,000. Options: 10,000 (strict; many default-`first` list queries with children fail until clients pass a smaller `first`) / 50,000 (allows one moderate page with children; a full-fan-out nested query still fails) / 100,000 (permissive; a single request can plan up to 100k leaf values). Whatever is chosen should be added to the spine's defaults and, ideally, to 1.2's Settings.
## Code Map

- `docweave/execution/executor.py` (1.3, 1.5, 2.1) -- runs graphql-core's standard validation and stamps `VALIDATION` on every validation error. Change it so a code already set by a rule is kept. The run order is parse → validate (+ depth) → bind variables → plan → **cost** → load.
- `docweave/execution/planner.py` (1.5, 1.7, 2.1, 2.2) -- `PlanNode` with the selected fields (response key to fieldname), the kind and `first`. Planner-added source fields (1.7) must be distinguishable from client-selected ones. Add a flag if 1.7 didn't.
- `docweave/schema/builder.py` (1.3) -- add the `Query` description.
- `docweave/docweave/doctype/docweave_settings/` (1.2), `docweave/adapter/settings.py` (1.2), `docweave/core/types.py` (1.2) -- add `max_cost`.
- `docweave/patches.txt` (1.1) -- empty so far.
- graphql-core 3.3.1 -- `graphql.validation.MaxIntrospectionDepthRule` is only in `recommended_rules`, not in `specified_rules`, so it must be added explicitly. `validate(schema, doc, rules, max_errors=...)`. A rule is an `ASTValidationRule` class, so build it per request with a closure over the limit.

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/docweave/doctype/docweave_settings/docweave_settings.json` and `.py`, `docweave/core/types.py`, `docweave/adapter/settings.py` -- the `max_cost` field (default per the Open Question), its validation, and `SettingsView.max_cost`.
- [ ] `docweave/patches/v0_1/set_max_cost_default.py`, `docweave/patches.txt` -- set `max_cost` where it is unset, under `[post_model_sync]`.
- [ ] `docweave/execution/rules.py` -- `depth_rule(max_depth)` and `estimate_cost(plan, settings)`.
- [ ] `docweave/execution/executor.py` -- wire both rules and the cost check, and keep rule-set codes.
- [ ] `docweave/schema/builder.py` -- the `Query` description.
- [ ] `docweave/tests/test_limits.py` -- the matrix. Spy on `plan` and `DataAdapter.load` to assert they aren't called on a breach.
- [ ] `docweave/tests/test_boundaries.py` -- a negative case: an inline source that has `execution/rules.py` import `docweave.adapter.settings` fails the import-direction check from 2.1.

**Acceptance Criteria:**
- Given an allowed user, when they POST the standard introspection query over HTTP at default settings, then it returns 200 with no errors.
- Given the printed schema, when `Query`'s description is read, then it states the formula, `max_depth` and `max_cost`.
- Given a breach of either limit, when the response is read, then `errors[0].extensions.code` is `DEPTH_LIMIT` or `COST_LIMIT` and `message` contains the limit's number.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.
- `bench --site dev.localhost migrate` -- expected: the patch runs once, and DocWeave Settings shows `max_cost`.

## Implementation Notes

## Spec Change Log

## Review Triage Log
