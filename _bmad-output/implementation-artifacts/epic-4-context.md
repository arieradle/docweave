# Epic 4 Context: Integration readiness and operations

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Make DocWeave ready for integrators, tool builders and administrators. Tool builders (including third-party MCP authors) can export the schema as SDL and rely on a stable error contract. Administrators can diagnose problems from one log line per request without leaking data, and can upgrade and uninstall DocWeave cleanly with no stale state left behind. DocWeave ships no MCP server; these are low-cost constraints that keep MCP tooling easy without driving schema decisions.

## Stories

- Story 4.1: SDL export
- Story 4.2: Error contract and request logging
- Story 4.3: Upgrade and uninstall lifecycle

## Requirements & Constraints

- The schema can be exported as SDL, including descriptions (from untranslated Frappe labels and help text) and custom scalars.
- Errors carry actionable messages and machine-readable codes: `MASKED`, `FORBIDDEN`, `NOT_FOUND`, `NOT_EXPOSED`, `VALIDATION`, `BAD_CURSOR`, `DEPTH_LIMIT`, `COST_LIMIT`, `INTERNAL`, defined only in `core`.
- No traceback, field value or cursor ever reaches the client or the log line.
- Each release states the exact Frappe v16 and ERPNext tags it was tested on (currently v16.53.0 and v16.52.1).

## Technical Decisions

- **SDL endpoint.** `docweave.api.sdl` is `@frappe.whitelist(methods=["POST"])`, no guests, so GET is refused. It returns a werkzeug `Response` with only the payload (no Frappe `_server_messages`, `exc` or `message` keys). The schema is per site, never per user or language, and comes from the same revision/fingerprint cache as `graphql`. The `Query` type's description publishes the cost formula. Scalars: `Decimal` as `str(value.normalize())`, ISO 8601 `Date`/`Datetime` (site offset), `Time` as `HH:MM:SS[.ffffff]`, `Long` as string, `JSON`.
- **Access.** The epic restricts SDL to System Manager; the architecture says `sdl` uses the same gate as `graphql` (enabled, a role in `allowed_roles`, Administrator only if `allow_administrator`). See the conflict note below.
- **Exception map.** `adapter/errors.py` is the only mapper. `DoesNotExistError` and `PermissionError` become `NOT_FOUND`. `ValidationError` becomes `VALIDATION` with the exception class and a sanitized message. Anything else becomes `INTERNAL`, deferred-logged with `with_context=False` (no locals). A test per mapped class.
- **Deferred error logging.** `adapter/errors.py` collects `INTERNAL` entries; the transport's `finally` calls `frappe.db.rollback()` and then writes them with `frappe.log_error(..., defer_insert=True)`. Never inline. A failed schema build is logged and returns `INTERNAL`.
- **Request log line.** `frappe.logger("docweave")`, one line per request: duration, query count, candidates scanned, cost and the codes returned. Never field values or cursors.
- **HTTP status.** 200 for GraphQL results including errors, 400 for malformed requests, 403 for gate failures.
- **Upgrade.** Settings changes ship as patches in `patches.txt`; `after_migrate` bumps `docweave:schema_revision` (Redis `INCR`), so the next request rebuilds the schema.
- **Uninstall.** `after_uninstall` in `hooks.py` deletes every `docweave:*` Redis key. Allowed Frappe calls outside the adapter are limited by the boundary allowlist (`frappe.cache` is allowed everywhere).
- **Release.** Semantic versioning; the README records the tested Frappe and ERPNext tags.

## Cross-Story Dependencies

- 4.1 depends on the schema builder and cache (Epic 1) and the cost formula description (Epic 2, depth and cost limits).
- 4.2 hardens the error map and transport `finally` introduced in Epic 1 and adds the candidates-scanned and cost numbers produced in Epic 2.
- 4.3 depends on the schema revision mechanism and hooks from Epic 1's cache story.
- Conflict to resolve when specifying 4.1: the epic limits SDL to System Manager, while the architecture applies the `graphql` gate to `sdl`.
