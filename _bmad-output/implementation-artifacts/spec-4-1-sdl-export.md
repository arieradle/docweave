---
title: 'SDL export'
type: 'feature'
created: '2026-11-01'
status: 'draft'
baseline_commit: 'cd5c12665210c90e70229a728c76326a8c6e0bfe'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Tool builders (for example MCP server authors) can discover the schema only by running the introspection query and converting the result themselves. There is no plain SDL export (FR-15).

**Approach:** Add `docweave.api.sdl`, a POST-only endpoint that prints the same cached schema `graphql` serves, using graphql-core's `print_schema`. It goes through the same access check, rollback and response path as `graphql`. Give every custom scalar a description of its wire format.

## Boundaries & Constraints

**Always:**
- `@frappe.whitelist(methods=["POST"])`, no guests. A GET is refused.
- The SDL comes from `schema.cache.get_schema(settings)`, the object `graphql` executes against. It is per site, never per user or language, and never built separately.
- The output has the type and field descriptions (untranslated labels and help text), the custom scalars `Decimal`, `Long`, `Date`, `Datetime`, `Time` and `JSON` each with a description of its format, and the `Query` description with the AD-10 cost formula.
- The body is only the payload: no `_server_messages`, `exc` or `message` keys. Refusals and failures use the same coded JSON errors and statuses as `graphql` (403 `NOT_EXPOSED`, 200 `INTERNAL` on a failed build).
- The endpoint shares the `graphql` endpoint's `try/finally` (rollback, then the deferred error flush). It is not copied.

**Never:**
- No per-user filtering of the SDL, no introspection-to-SDL round trip, no SDL file written to disk, no MCP server.
- Don't change the schema builder's types or names. Only scalar and `Query` descriptions are added.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Allowed caller | POST, Sales Order and Customer exposed | 200, SDL containing `type SalesOrder`, `scalar Decimal` with its description, field descriptions | N/A |
| Same as served | the same site, any two allowed users | byte-identical SDL, equal to `print_schema(get_schema(settings))` | N/A |
| After a change | Customer added to the exposed DocTypes, then commit | the next export contains `type Customer` | N/A |
| GET | allowed caller | refused by Frappe's method check | Frappe's 403 |
| Not allowed | caller fails the access check (see Open Questions) | 403 `NOT_EXPOSED`, no SDL | N/A |
| Build fails | `build_schema` raises | 200 with `INTERNAL`, no traceback | deferred Error Log |

</frozen-after-approval>

## Open Questions

- **Who may export.** The epics allow System Manager only. AD-12 gives `sdl` the same gate as `graphql` (enabled, a role in `allowed_roles`, Administrator only if `allow_administrator`). Options: the `graphql` gate (any API user can fetch the SDL, which they can already get through introspection; the epics' AC is amended) / System Manager only, ignoring `enabled` and `allowed_roles` (admins can export before turning the API on; AD-12 is amended through correct-course) / both the gate and System Manager (strictest; a tool builder who isn't a System Manager must ask an admin).
- **Success body format.** Options: the raw SDL as `text/plain; charset=utf-8` (`curl ... > schema.graphql` just works; errors are JSON, so the content type differs between success and failure) / JSON `{"data": {"sdl": "..."}}` (one content type for every response; clients must unwrap it).
- Depends on 1.3 question "Decimal format": the `Decimal` description states whichever format is chosen.
- Depends on 1.3 question "Enabled with nothing exposed": the export returns the same thing `graphql` does in that state.
- Depends on 1.2 question "Guest and GET refusals": a GET or guest gets Frappe's 403 envelope, not coded JSON, unless that question is answered otherwise.

## Code Map

- `docweave/api.py` (created in 1.2) -- `graphql()`, `_gate(settings)`, the `finally` with `frappe.db.rollback()`, deferred error flush (1.5) and the `Response` writer. Factor the shared request path into one helper used by both endpoints.
- `docweave/schema/cache.py` (created in 1.4) -- `get_schema(settings)`. Reuse; don't change.
- `docweave/schema/scalars.py` (created in 1.3) -- the six scalars, output coercion only. Add descriptions here.
- `docweave/schema/builder.py` (created in 1.3) -- the `Query` description carrying the cost formula is promised to Story 2.4 by AD-10 (2.4 spec not yet written). Check it is present; don't duplicate it.
- `docweave/adapter/errors.py` (created in 1.5) -- `map_exception`, `take_deferred`. A failed build goes through it.
- `docweave/tests/utils.py` (created in 1.2) -- `make_user`, `auth_headers`, `set_settings`.
- graphql-core 3.3 `graphql.utilities.print_schema(schema) -> str` (verified in 3.3.1) -- prints descriptions and `scalar` definitions, skips built-in types.

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/schema/scalars.py` -- add a `description` to each custom scalar stating its wire format: `Decimal` (string, per the 1.3 decision), `Long` (string), `Date` (ISO 8601 date), `Datetime` (ISO 8601 with the site offset), `Time` (`HH:MM:SS[.ffffff]`), `JSON`.
- [ ] `docweave/api.py` -- `sdl()`: the access check from the first Open Question, `get_schema`, `print_schema`, and the body format from the second, all through the shared `try/finally` and `Response` helper.
- [ ] `docweave/tests/test_sdl.py` -- the matrix over HTTP (committed fixtures, cleanup in `tearDown`), including at least one refused caller for each rule the chosen access check has, and a check that the SDL parses back with `graphql.build_schema`.

**Acceptance Criteria:**
- Given an allowed caller, when they POST to `docweave.api.sdl`, then the SDL has a description on every exposed type, on `Query` (with the cost formula) and on each custom scalar.
- Given any SDL response, when its body is inspected, then it has no `_server_messages`, `exc` or `message` keys and no traceback.
- Given the package, when `test_boundaries.py` runs, then it passes with no new allowlist entries.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave --module docweave.tests.test_sdl` -- expected: all pass.
- `bench --site dev.localhost run-tests --app docweave` -- expected: all pass.

## Implementation Notes

## Spec Change Log

## Review Triage Log
