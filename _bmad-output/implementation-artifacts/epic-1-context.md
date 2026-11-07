# Epic 1 Context: Secure document reads, starting with the Sales Order slice

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Deliver the first vertical slice of DocWeave, a pure-Python Frappe v16 app that adds a permission-correct, read-only GraphQL API. An administrator installs the app, enables the endpoint and exposes Sales Order and Customer. A client can then fetch one Sales Order with its customer and item rows in a single request, getting only the fields it selected. Frappe permissions and masking must apply exactly as they do in Frappe's own REST API, and there must be no N+1 queries. This slice proves the hexagonal boundary, the authorized read chokepoint and two-phase execution, which Epic 2 (lists and pagination) builds on.

## Stories

- Story 1.1: Installable app with CI and boundary guard
- Story 1.2: DocWeave Settings and the access gate
- Story 1.3: Schema generation from Exposed DocTypes
- Story 1.4: Schema cache and invalidation
- Story 1.5: Authorized single-document read
- Story 1.6: Masking and field-level readability
- Story 1.7: Links and child tables in one request, without N+1

## Requirements & Constraints

- The schema contains only Exposed DocTypes. Nothing is reachable until an admin enables the endpoint and adds DocTypes in the DocWeave Settings Single DocType. Settings are restricted to System Manager, have change tracking on and are never exposed themselves.
- Every read runs as the session user through the single authorized query function. No unrestricted data path exists. A build-time AST test enforces this, backed by integration tests.
- Masked values return `null` plus a field-level `MASKED` error. Masking is detected from metadata and permissions, never by comparing values.
- Descriptions on types and fields come from Frappe labels and help text, untranslated.
- Errors carry actionable messages and machine-readable codes.
- Frappe v16 only, tested on v16.53.0 with ERPNext v16.52.1. Pure Python on `graphql-core ~=3.3.0`. v1 is read-only: no `Mutation` root type.
- Testing priority: permissions, masking, then cursor correctness. Every architecture rule needs at least one negative test. Tests use v16 `IntegrationTestCase` on ERPNext fixtures.
- Success: a Sales Order with customer and items loads in one request with a constant, small number of database queries, and no test shows a permission leak.

## Technical Decisions

- **Layers and imports.** `core/` is a dependency-free shared kernel (types, sentinels, `ErrorCode`, `SettingsView`, `DataAdapter` port, generic resolver, `filter_hash`). `api.py` is transport. `schema/` and `execution/` never import `adapter/`; the transport injects the adapter and `SettingsView`. `adapter/` is the only code that touches Frappe data.
- **Boundary allowlist (`test_boundaries.py`).** It resolves aliased imports to dotted names. Outside `adapter/`, only `frappe.get_meta`, `frappe.cache`, `frappe.logger`, `frappe._`, `frappe.session.user`, `frappe.get_roles` and `frappe.utils.get_system_timezone` are allowed. `api.py` may also use `frappe.whitelist`, `frappe.local.request`, `frappe.local.message_log`, `frappe.db.rollback` and `frappe.log_error`. `hooks.py` and `schema/cache.py` may also use `frappe.db.after_commit` and `frappe.clear_cache`. Banned everywhere: `frappe.db.sql`, `frappe.db.exists`, `frappe.db.get_value`, `frappe.get_all`, `frappe.get_list`, `frappe.get_cached_doc`. `adapter/permission.py` alone may use `get_doc` and `has_permission`. `adapter/settings.py` alone may use `get_single("DocWeave Settings")`.
- **Authorized query.** `_authorized_query` has a closed parameter set: no kwargs, no raw SQL, no Frappe-format filters. It calls `frappe.qb.get_query` with `ignore_permissions=False` and `ignore_user_permissions=False`, and asserts the user is `frappe.session.user`. Never switch the session user. Child reads must pass `parent_doctype`, or Frappe raises `PermissionError`.
- **Document check.** Stage 1 takes candidates from `_authorized_query`. Stage 2 runs `frappe.get_doc` plus `frappe.has_permission(..., "read", doc=...)` per candidate, cached per request. Returned values always come from the masked Stage 1 row, never from the loaded document. Select-only users get `NOT_FOUND` without a scan. A parity test checks the results against Frappe's `get_list` plus `has_permission`, covering a child-row Warehouse permission, a shared document, `if_owner` and a hook-denied document.
- **Masking and readability.** The masked set is the union of `meta.get_masked_fields(parenttype=...)` and a fresh per-request computation from the user's current roles, because Frappe's per-user mask cache never expires. Administrator gets no masked fields. Readable fields are computed before the query, because Frappe silently drops fields above the user's permlevel. In `Row`, masked values become `MASKED` and unreadable selected fields become `FORBIDDEN`.
- **Nullability.** Every output field except `name` is nullable, and so are root fields. A child list is `[ChildType!]` and the list itself is nullable.
- **Two-phase execution.** A request runs as parse, depth rules, bind variables, plan, preload through `DataAdapter.load`, assemble the result graph, then execute in graphql-core. Resolvers do no I/O and read the graph by response key (`info.path.key`). A plan node's identity is (DocType, parent_doctype, parentfield or link fieldname, argument fingerprint, path). Batching happens only across sibling rows of one node.
- **Links and children.** A Link target is authorized for its own DocType; an unreadable target is `null` plus `NOT_FOUND`. Empty Link values give `xDoc: null` with no error and are never sent as keys. The assembler joins only on `Row.matched_key`. A Link or child load starts only from a readable, unmasked source field. Otherwise the derived field inherits the source's sentinel. Children load only for parents that passed the document check, filtered on `parenttype`, `parentfield` and `parent IN (...)`, ordered by `idx ASC`. Total child rows over `max_child_rows` fail the child field with `COST_LIMIT` and are never truncated. Child DocTypes are never roots.
- **Port types (frozen dataclasses in `core/types.py`).** `LoadRequest` has kind (ROOT_ONE, ROOT_CONNECTION, LINK, CHILDREN), doctype, fields, filter, order, first, after, keys, parent_doctype and parentfield. `Row` is keyed by Frappe fieldname, never GraphQL names. It always has `name`; child rows add `parent`, `parentfield` and `idx`; link rows add `matched_key`. `DataAdapter.load(requests) -> results` returns results aligned with the requests.
- **Errors.** Error codes are defined only in `core`. `adapter/errors.py` is the only exception mapper: `DoesNotExistError` and `PermissionError` become `NOT_FOUND`, `ValidationError` becomes `VALIDATION` with a sanitized message, and anything else becomes `INTERNAL`, deferred-logged without locals. An unreadable document is `NOT_FOUND` whether or not it exists. `FORBIDDEN` is only for fields and filters.
- **Endpoint and gate.** `docweave.api.graphql` and `docweave.api.sdl` accept POST only and refuse guests. The gate checks, in order: enabled (else 403 `NOT_EXPOSED`), a role in `allowed_roles` (Website Users never allowed), and Administrator only if `allow_administrator` is on. Execution sits in `try/finally`: rollback, then flush deferred error logs. The endpoint returns a werkzeug `Response` with GraphQL JSON only. Status is 200 for GraphQL results, 400 for malformed requests and 403 for gate failures.
- **Schema.** `schema/naming.py` is the only producer of GraphQL names. It splits on non-alphanumerics and `_`, then builds PascalCase types and camelCase fields, prefixing `_N` when a name starts with a digit. Root fields are `salesOrder(name: String!)` and `salesOrderList(...)`. Standard fields are `name: String!`, `owner`, `creation`, `modified`, `modifiedBy` and `docstatus`, plus `idx` on child types. Never expose `_*`, `parent`, `parenttype` or `parentfield`. Link `x` becomes `x: String` plus `xDoc` only if the target is exposed. Dynamic Link is a string only. Table fields become `[ChildType!]`. The fieldtype map, the excluded types (Password and layout fields) and the scalar formats are set in the spine; Decimal is serialized as `str(value.normalize())`. Unknown fieldtypes are excluded and logged once per build. The epic requires a GraphQL name collision to fail the build and name both fields.
- **Schema cache.** The schema is per site, never per user. The `docweave:schema_revision` Redis integer is created with `SET NX` as a random 63-bit value and bumped with `INCR` in `after_commit`. The bump is triggered by DocWeave Settings, DocType, Custom Field, Property Setter, DocPerm and Custom DocPerm changes, and by `after_migrate`. The cache key is (revision, fingerprint). The fingerprint hashes the Settings `modified`, each exposed and child DocType's meta `modified`, and Frappe's internal `metadata_version`, which needs its own test. Storage is a per-process LRU that never serves the previous schema after a revision change. A failed build logs the error and returns `INTERNAL`.
- **Settings defaults.** Maximum page 100, scan budget 200, depth 8, `child_fanout_estimate` 50, `max_child_rows` 10,000. Endpoint disabled and `allow_administrator` off by default.
- **Stack and CI.** Python 3.14, ruff 0.14.10 in pre-commit, MariaDB 11.8. CI reuses the dev image whose reference is read from `.devcontainer/docker-compose.yml`, with no separate CI image and no `bench init` or `get-app`. MariaDB and Redis run as service containers. Tests run via `docker run --user vscode` on a throwaway site. A PR that changes `.devcontainer/` tests against the image built in that PR.
- **Logging.** Use `frappe.logger("docweave")`. Never log field values or cursors.

## Cross-Story Dependencies

- 1.1 comes first. Its boundary test guards every later story, and its CI depends on the Epic 0 dev image and prebuild.
- 1.2 provides `SettingsView` and the gate that 1.3 to 1.7 rely on. 1.3 needs the exposed-DocType list from 1.2. 1.4 caches the output of 1.3.
- 1.5 establishes `core/types.py` (sentinels, `ErrorCode`, `Row`, `LoadRequest`), `_authorized_query`, the document check and `adapter/errors.py`. 1.6 and 1.7 build on these.
- 1.7 depends on the masking sentinels from 1.6 for derived Link and child loads.
- Epic 2 reuses `_authorized_query`, the document check, `FilterIR` and the planner for connections, cursors and the scan budget.
- Epic 0 spikes confirmed the scan budget of 200 and the runtime masking behaviour these rules are based on.
- Story 1.4 requires a Redis lock for concurrent schema builds, but the architecture lists the build lock as a v2 item. Resolve this when 1.4 is specified.
