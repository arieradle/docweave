---
title: 'Schema generation from Exposed DocTypes'
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

**Problem:** The gate from 1.2 passes requests through to an empty `_run`. There is no schema, so clients can't discover the exposed DocTypes, their fields or their descriptions (FR-1, FR-13).

**Approach:** Build a `GraphQLSchema` per request from `SettingsView.exposed_doctypes` and `frappe.get_meta`. The rules are the spine's naming, fieldtype map, standard fields, Link variants, child types and scalars. Each type and field is tagged with `extensions["docweave"]` metadata for the planner. `_run` parses, validates and executes the request with graphql-core, so introspection works. Data fields resolve to `null` until 1.5.

## Boundaries & Constraints

**Always:**
- `schema/naming.py` is the only producer of GraphQL names. Types are PascalCase, fields camelCase; split on `[^A-Za-z0-9]+` and `_`; prefix `_N` when a name starts with a digit; Link `x` gives `xDoc`; the single root field is camelCase (`salesOrder(name: String!)`).
- Standard fields: `name: String!`, `owner`, `creation`, `modified`, `modifiedBy`, `docstatus`, plus `idx` on child types. Never expose `_*`, `parent`, `parenttype` or `parentfield`. Every output field except `name` is nullable, root fields included. A Table or Table MultiSelect field is a nullable `[ChildType!]`.
- `xDoc` exists only when the Link target is exposed. Dynamic Link is a plain `String`. Child DocTypes appear only under a Table field. The builder raises `SchemaBuildError` if the exposed list holds a child DocType, a Single DocType or DocWeave Settings (AD-14).
- Descriptions come from untranslated labels and help text, never `frappe._`. The schema doesn't depend on the user or their language (AD-11).
- Unknown fieldtypes are excluded and logged once per build through `frappe.logger("docweave")`. Password and layout types are excluded.
- A failed build returns 200 with a GraphQL error coded `INTERNAL`, and the failure is logged.
- Settings validation (the 1.2 controller) also rejects two exposed DocTypes that give the same type name or root field name, naming both.

**Never:**
- No `salesOrderList`, filter, order or connection types (Epic 2). No cache (1.4), no data loading (1.5), no depth rules (2.4).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Slice | Sales Order and Customer exposed | `SalesOrder`, `Customer` and `SalesOrderItem` types; `grandTotal: Decimal`; `customer: String`; `customerDoc: Customer`; `items: [SalesOrderItem!]` | N/A |
| Link to a non-exposed DocType | `company` Link to Company | `company: String`, no `companyDoc`, no `Company` type | N/A |
| Excluded types | Password, Section/Column/Tab Break, HTML, Button | absent | N/A |
| Unknown fieldtype | a DocField with `fieldtype="Weird"` | excluded; one log line per build | N/A |
| Digit-led name | fieldname `3d_model` | `_N3dModel` | N/A |
| Untranslated | user language `de` | descriptions are the English label plus help text | N/A |
| Two users | build as Administrator and as a Sales User | identical `print_schema` output | N/A |
| Child as root | `SettingsView` that lists Sales Order Item | build fails | `SchemaBuildError` → `INTERNAL` |
| Exposed name clash | Settings exposes DocTypes `Foo Bar` and `Foo-Bar` | save rejected, naming both | `ValidationError` |
| Invalid GraphQL | syntax error or unknown field | 200 with errors coded `VALIDATION` | N/A |

</frozen-after-approval>

## Open Questions

- **Field-name collision.** The epics say the build fails, naming both fields, with nothing suffixed silently. The spine (Names convention) says a field collision drops the custom field with a logged warning. Options: fail the build (the epics' rule: a customization can take the whole API down until it's fixed; the spine is amended through correct-course) / drop the custom field and warn (the API stays up; the epics' AC is amended, and a client silently loses a field).
- **Decimal format.** The spine says `str(value.normalize())`, which renders 100 as `"1E+2"`. Options: follow the spine literally (exponent strings reach clients) / use `format(value.normalize(), "f")`, giving `"100"` and `"0.5"` (a spine text change).
- **Enabled with nothing exposed.** graphql-core rejects a `Query` type with no fields. Options: 403 `NOT_EXPOSED` while `exposed_doctypes` is empty (consistent with the gate; also blocks introspection) / a fixed `_docweave: String` placeholder field (introspection still works, but every schema carries a field clients don't need).

## Code Map

- `docweave/core/types.py` (created in 1.2) -- `SettingsView`, `ErrorCode`, `GraphQLRequest`.
- `docweave/api.py` (created in 1.2) -- `_run(request, settings)` is the seam. Here it becomes `build_schema(settings)` followed by `execute(schema, request)`. Gate, rollback and `Response` stay as they are.
- `docweave/docweave/doctype/docweave_settings/docweave_settings.py` (created in 1.2) -- add the collision check using `schema.naming`.
- `~/frappe-bench/apps/frappe/frappe/model/meta.py` -- `meta.fields` (DocFields: `fieldname`, `fieldtype`, `label`, `description`, `options`, `is_virtual`), `istable`, `issingle`, `description`. `get_table_fields()` is at l.244.
- graphql-core 3.3 (`graphql/type/definition.py`) -- `extensions` on types and fields; scalars use `coerce_output_value` (`serialize` is the legacy name).
- `~/frappe-bench/apps/erpnext/erpnext/selling/doctype/sales_order/sales_order.json` -- `customer` (Link Customer), `company` (Link), `items` (Table Sales Order Item), `grand_total` (Currency).

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/schema/naming.py` -- `type_name`, `field_name`, `doc_field_name`, `root_one_name`, plus a reverse map from GraphQL name to fieldname per type.
- [ ] `docweave/schema/fieldtypes.py` -- `FIELDTYPE_MAP` (the spine's table), `EXCLUDED_FIELDTYPES`, `STANDARD_FIELDS`.
- [ ] `docweave/schema/scalars.py` -- `Decimal` (accepts `Decimal`, `int` and `float` via `Decimal(repr(v))`; format per the Open Question), `Long` (string), `Date`, `Datetime` (ISO 8601 with the offset from `frappe.utils.get_system_timezone`), `Time`, `JSON`. Output coercion only; input coercion comes in 2.1.
- [ ] `docweave/schema/builder.py` -- `build_schema(settings) -> GraphQLSchema`, `SchemaBuildError`. Tags: object types `{"doctype", "is_child"}`; fields `{"fieldname", "kind": "scalar" | "link_doc" | "children", "target"}`; the root field `{"kind": "root_one", "doctype"}`. Virtual fields are excluded.
- [ ] `docweave/execution/executor.py` -- `execute(schema, request, root_value=None) -> dict`: parse, run graphql-core's standard validation, `execute_sync`, and format. Syntax and validation errors get `extensions.code = "VALIDATION"`.
- [ ] `docweave/api.py`, `docweave_settings.py` -- the wiring and collision validation described above.
- [ ] `docweave/tests/test_schema.py` -- the matrix, `print_schema` snapshots of the slice types' fields, a nullability walk, and descriptions.

**Acceptance Criteria:**
- Given Sales Order and Customer exposed and an allowed user, when they POST the standard introspection query, then they get 200 with `SalesOrder` and `Customer`, descriptions on types and fields, and no non-exposed DocType.
- Given the slice schema, when every field is walked, then only `name` is non-null.

## Design Notes

A type's description is `meta.description` or else the DocType name. A field's description is its label, followed by a blank line and the help text when there is one. The `extensions` tags are the contract 1.5 and 1.7 plan from, so keep their keys exactly as above.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.

## Implementation Notes

## Spec Change Log

## Review Triage Log
