---
status: draft
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-docweave-2026-10-24/prd.md
  - _bmad-output/planning-artifacts/architecture/architecture-docweave-2026-10-24/ARCHITECTURE-SPINE.md
---

# DocWeave: Epic Breakdown

## Overview

This document breaks the DocWeave PRD and Architecture Spine into implementable epics and stories. There is no UX document; DocWeave is API-only. AD-n references point to the Architecture Spine.

## Requirements Inventory

### Functional Requirements

- FR-1: The GraphQL schema contains only Exposed DocTypes. Nothing is exposed until configured.
- FR-2: An administrator configures exposure, limits and enablement in the DocWeave Settings Single DocType. The settings are admin-only and never exposed, and changes invalidate the schema revision after commit.
- FR-3: The endpoint is reachable only when enabled.
- FR-4: A client queries documents with typed filters, field selection, links and child tables in one request.
- FR-5: Batched loading keeps request cost independent of the parent row count (no N+1).
- FR-6: Every read goes through the single authorized query function as the session user.
- FR-7: Masked values return `null` plus a `MASKED` error, detected from metadata.
- FR-8: Cursor pagination. Hitting the scan budget returns a short page with `scanLimitReached` and a continuation cursor.
- FR-9: The cursor marks the last scanned candidate, is bound to user and filter, and is issued even for empty pages.
- FR-10: `hasNextPage` is a conservative signal: `false` only when candidates are known to be exhausted.
- FR-11: Create, sparse update and delete mutations, with Frappe permissions and validation, all or nothing per request.
- FR-12: Introspection works, with depth and cost limits.
- FR-13: Descriptions come from Frappe labels and help text.
- FR-14: Actionable messages and machine-readable error codes.
- FR-15: SDL export.

### NonFunctional Requirements

- NFR-1: No GraphQL read bypasses `_authorized_query`. Enforced by the AST boundary test, integration tests and review rules. `has_permission` hooks are tested.
- NFR-2: Frappe v16 only, tested on the exact release (v16.53.0, ERPNext v16.52.1).
- NFR-3: Pure Python on `graphql-core ~=3.3.0`.
- NFR-4: Testing priority: permissions, masking, cursor correctness.

### Additional Requirements

From the Architecture Spine:
- Hexagonal layout with a dependency-free `core` shared kernel (AD-1).
- Two-phase execution with response-key resolvers (AD-3).
- A permission projection, so `has_permission` runs without per-candidate loads (AD-4).
- Derived loads only from readable, unmasked fields (AD-6).
- Child rows bound to `parentfield` (AD-7).
- Fernet-encrypted keyset cursor (AD-8).
- Transport owns the transaction (AD-9).
- Mutation input contract (AD-13).
- Child DocTypes are never roots (AD-14).
- `NOT_FOUND` for unreadable documents (AD-15).
- POST-only endpoint, access gate and envelope stripping (AD-12).
- Schema cache keyed by revision and fingerprint (AD-11).
- Operations: patches, uninstall cleanup, per-request log line.

### UX Design Requirements

None. DocWeave is API-only.

### FR Coverage Map

| FR | Stories |
| --- | --- |
| FR-1 | 1.3, 1.4 |
| FR-2 | 1.2, 1.4 |
| FR-3 | 1.2 |
| FR-4 | 1.5, 1.7, 2.1 |
| FR-5 | 1.7 |
| FR-6 | 1.5 |
| FR-7 | 1.6 |
| FR-8 | 2.2, 2.3 |
| FR-9 | 2.2, 2.3 |
| FR-10 | 2.3 |
| FR-11 | 3.1, 3.2, 3.3, 3.4 |
| FR-12 | 2.4 |
| FR-13 | 1.3 |
| FR-14 | 1.5, 2.4, 4.2 |
| FR-15 | 4.1 |

## Epic List

### Epic 1: Secure document reads, starting with the Sales Order slice
An administrator installs DocWeave and exposes Sales Order and Customer. A client then reads one Sales Order, with its customer and item rows, in a single request. Permissions and masking are exactly right, and there is no N+1.
**FRs covered:** FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-13, FR-14 (partial)

### Epic 2: Listing, filtering and safe pagination
Clients list documents with typed filters and ordering. They page through large, mostly unauthorized sets without stalling, skipping or leaking, and every request stays within limits.
**FRs covered:** FR-4, FR-8, FR-9, FR-10, FR-12, FR-14

### Epic 3: Writing data
Clients create, update and delete documents through mutations that respect Frappe permissions, validation and hidden values, all or nothing per request.
**FRs covered:** FR-11

### Epic 4: Integration readiness and operations
Integrators and tool builders (including MCP authors) can export the schema and rely on stable errors. Administrators can observe, upgrade and uninstall DocWeave cleanly.
**FRs covered:** FR-14, FR-15

## Epic 1: Secure document reads, starting with the Sales Order slice

An administrator installs DocWeave and exposes Sales Order and Customer. A client then reads one Sales Order, with its customer and item rows, in a single request. Permissions and masking are exactly right, and there is no N+1.

### Story 1.1: Installable app with CI and boundary guard

As the DocWeave developer,
I want an installable Frappe app skeleton with CI and the AD-1 boundary test,
So that every later story builds on a green, permission-safe baseline.

**Acceptance Criteria:**

**Given** a bench on Frappe v16.53.0 with ERPNext v16.52.1
**When** I run `bench get-app` and `bench --site test install-app docweave`
**Then** the app installs with the package layout from the spine (`core/`, `schema/`, `execution/`, `adapter/`, `api.py`)
**And** `pyproject.toml` pins `graphql-core~=3.3.0` and ruff 0.14.10 runs in pre-commit

**Given** a module outside `adapter/` that calls `frappe.get_all` (or an aliased import of a banned name)
**When** `test_boundaries.py` runs
**Then** it fails and names the file and call. Allowlisted calls such as `frappe.get_meta` pass.

**Given** a push to the repository
**When** GitHub Actions runs
**Then** it provisions MariaDB 11.8 and Redis, installs Frappe v16.53.0 and ERPNext v16.52.1, and runs `bench run-tests --app docweave` green

### Story 1.2: DocWeave Settings and the access gate

As a Frappe administrator,
I want to enable the endpoint and choose who may use it in DocWeave Settings,
So that nothing is reachable until I configure it.

**Acceptance Criteria:**

**Given** a fresh install
**When** any user POSTs to `/api/method/docweave.api.graphql`
**Then** they get HTTP 403 with code `NOT_EXPOSED` (disabled by default)

**Given** DocWeave Settings with a child table of exposed DocTypes
**When** an admin adds a child DocType (`istable=1`), a Single DocType, or DocWeave Settings itself
**Then** validation rejects the row with a clear message

**Given** the endpoint is enabled
**When** the request is a GET, comes from a Website User, a user without an `allowed_roles` role, or Administrator while `allow_administrator` is off
**Then** the request is refused: GET is not allowed (CSRF-safe), and the others get 403 `NOT_EXPOSED`

**Given** any DocWeave response
**When** Frappe has queued messages
**Then** the body contains only GraphQL JSON, with no `_server_messages`, `exc` or `message` keys

**And** DocWeave Settings is editable only by System Manager and has change tracking enabled

### Story 1.3: Schema generation from Exposed DocTypes

As an API client,
I want a typed schema generated from the exposed DocTypes,
So that I can discover documents, fields and descriptions by introspection.

**Acceptance Criteria:**

**Given** Sales Order and Customer are exposed
**When** I introspect the schema
**Then** `SalesOrder` and `Customer` types exist with camelCase fields mapped per the spine's fieldtype table, and Password and layout fields are absent
**And** types and fields carry descriptions from Frappe labels and help text
**And** non-exposed DocTypes do not appear

**Given** Sales Order's `customer` Link field
**When** the schema is built
**Then** it has `customer: String` and, because Customer is exposed, `customerDoc: Customer`. A Link to a non-exposed DocType gets no `xDoc` field.

**Given** two fields that map to the same GraphQL name
**When** the schema is built
**Then** the build fails, naming both fields. Nothing is suffixed silently.

**And** every output field except `name` is nullable

### Story 1.4: Schema cache and invalidation

As a Frappe administrator,
I want schema changes to take effect immediately after I save settings or customize a DocType,
So that the API never serves a stale schema.

**Acceptance Criteria:**

**Given** a cached schema
**When** DocWeave Settings, a DocType, Custom Field, Property Setter, DocPerm or Custom DocPerm changes and the transaction commits
**Then** `docweave:schema_revision` is incremented and the next request rebuilds the schema

**Given** a Property Setter deleted through Customize Form, which fires no `doc_events`
**When** the next request arrives
**Then** the fingerprint (meta `modified` plus Frappe's metadata version) differs and the schema is rebuilt

**Given** a change that is rolled back
**When** the next request arrives
**Then** the revision is unchanged

**Given** several workers missing the cache at once
**When** they build
**Then** a Redis lock ensures only one builds while the others wait or reuse the result

### Story 1.5: Authorized single-document read

As an API client,
I want to fetch one Sales Order by name,
So that I get exactly the fields I select, with Frappe permissions enforced.

**Acceptance Criteria:**

**Given** a user allowed to read Sales Order SO-1
**When** they query `salesOrder(name: "SO-1") { name grandTotal }`
**Then** they get those fields, read through `_authorized_query` with `ignore_permissions=False`

**Given** a user restricted by User Permissions, by a `permission_query_conditions` hook, or by a document-level `has_permission` hook denying SO-1
**When** they query SO-1
**Then** `salesOrder` is `null` with code `NOT_FOUND`, the same response as for a name that does not exist

**Given** a `has_permission` hook that reads a non-selected field
**When** the check runs
**Then** the hook sees that field from the permission projection, and the query count stays constant (no per-document load)

**And** `core/types.py` defines the sentinels, `ErrorCode`, `Row` and `LoadRequest`, and `adapter/errors.py` maps Frappe exceptions per AD-15

### Story 1.6: Masking and field-level readability

As an API client,
I want masked and unreadable fields to come back as `null` with a clear code,
So that I can tell a hidden value from an empty one without breaking type coercion.

**Acceptance Criteria:**

**Given** Customer `credit_limit` (Currency) is masked for the user
**When** they select `creditLimit`
**Then** it returns `null` with a field error `{path: [..., "creditLimit"], extensions.code: "MASKED"}` and no Decimal coercion error

**Given** a field at permlevel 1 that the user lacks
**When** they select it
**Then** it returns `null` with code `FORBIDDEN`, and the parent object is not nulled

**And** masking is detected from `get_masked_fields(parenttype=...)` and permissions, never by comparing values

### Story 1.7: Links and child tables in one request, without N+1

As a mobile developer,
I want a Sales Order with its customer and item rows in one round trip,
So that my screen loads fast without leaking data I can't see.

**Acceptance Criteria:**

**Given** `salesOrder { customerDoc { customerName } items { itemCode qty } }`
**When** it executes
**Then** the customer and items load through batched plan nodes, and resolvers do no I/O

**Given** a user who can read the Sales Order but not its Customer
**When** they select `customerDoc`
**Then** `customerDoc` is `null` with `NOT_FOUND`, and `customer` (raw name) follows the field's own readability

**Given** a masked or unreadable `customer` field
**When** `customerDoc` is selected
**Then** it gets the same sentinel and no Customer load happens

**Given** child rows
**When** they load
**Then** the query filters on `parenttype`, `parentfield` and authorized parent names, uses `parent_doctype` for masking, orders by `idx`, and skips the Table field if it is unreadable at its permlevel

**Given** aliased selections of the same field with different arguments
**When** the query executes
**Then** each alias resolves its own result (response-key resolution)

**And** `test_query_count.py` asserts a constant query count when fetching 1 versus 50 orders with customer and items

## Epic 2: Listing, filtering and safe pagination

Clients list documents with typed filters and ordering. They page through large, mostly unauthorized sets without stalling, skipping or leaking, and every request stays within limits.

### Story 2.1: Typed filters and ordering

As an integrator,
I want typed filters and ordering on list queries,
So that I can fetch exactly the documents I need.

**Acceptance Criteria:**

**Given** `salesOrders(filter: { status: { in: ["Draft","To Deliver"] }, or: [...] }, orderBy: [{ field: transactionDate, direction: DESC }])`
**When** it executes
**Then** the planner produces a `FilterIR` and only the adapter translates it into qb criteria

**Given** two equivalent filters with different key or child order
**When** `filter_hash` is computed
**Then** both hashes are identical (canonical JSON)

**Given** no `orderBy`
**When** the query is planned
**Then** the order resolves to `creation DESC, name DESC` before any query runs

**Given** a field that is masked or unreadable for the user
**When** it is used in a filter or `orderBy`
**Then** the request is rejected with `FORBIDDEN` before any query runs

### Story 2.2: Keyset connections with encrypted cursors

As an API client,
I want Relay-style connections with opaque cursors,
So that I can page reliably without seeing anything I'm not allowed to.

**Acceptance Criteria:**

**Given** `salesOrders(first: 20)`
**When** it returns
**Then** I get `edges { cursor node }` and `pageInfo { hasNextPage endCursor scanLimitReached }`

**Given** an `endCursor`
**When** I base64-decode it
**Then** no document name, sort value or user email is readable (Fernet, HKDF purpose `docweave-cursor-v1`)

**Given** a cursor that is replayed by another user, used with a different filter or order, older than 24 hours, or tampered with
**When** it is used
**Then** the response is `BAD_CURSOR`

**Given** rows with equal sort values or NULLs
**When** I page through all of them
**Then** every row appears exactly once (name tie-break in the same direction, explicit `IS NULL` branch)

**Given** `first` above the maximum page size
**When** the query runs
**Then** it is rejected with `VALIDATION`

### Story 2.3: Scan budget and short pages

As an API client,
I want short pages with continuation when most candidates are unauthorized,
So that paging always makes progress and never errors on the scan limit.

**Acceptance Criteria:**

**Given** 5,000 Sales Orders of which the user can read 7, scan budget 100, `first: 20`
**When** I page with `after: endCursor` until `hasNextPage` is false
**Then** every readable order is returned exactly once, the loop terminates, and every candidate is permission-checked once

**Given** a page where the budget runs out after checking 100 candidates
**When** it returns
**Then** `scanLimitReached: true` and `hasNextPage: true`, the cursor points at the last permission-checked candidate (not merely fetched), and a cursor is issued even when `edges` is empty

**Given** two connections in one request
**When** the per-request `max_total_candidates` is reached
**Then** every unfinished connection reports `scanLimitReached: true` with a valid cursor

**Given** the candidates are exhausted
**When** the last page returns
**Then** `hasNextPage` is `false`

### Story 2.4: Depth and cost limits

As a Frappe administrator,
I want depth and cost limits on every request,
So that clients and AI agents can't run unbounded queries.

**Acceptance Criteria:**

**Given** the standard introspection query
**When** it runs at depth limit 8
**Then** it succeeds (`__schema` and `__type` are exempt)

**Given** a query deeper than the limit
**When** it is validated
**Then** it fails with `DEPTH_LIMIT`, and the message states the limit

**Given** a query whose `estimate_cost(plan)` exceeds the limit (connections at `first` or the maximum page size, children at `child_fanout_estimate`, links at 1)
**When** it is planned
**Then** it fails with `COST_LIMIT` before any adapter call, and the message states the limit and the estimated cost

## Epic 3: Writing data

Clients create, update and delete documents through mutations that respect Frappe permissions, validation and hidden values, all or nothing per request.

### Story 3.1: Create mutations with the input contract

As an integrator,
I want to create documents through `createX(input)`,
So that I can write data with Frappe validation and permissions applied.

**Acceptance Criteria:**

**Given** the generated `SalesOrderCreateInput`
**When** I inspect it
**Then** it excludes the system, read-only, `fetch_from` (unless `fetch_if_empty`), virtual, Password and display fields per AD-13, plus `name` unless autoname is Prompt

**Given** a user with create permission
**When** they call `createSalesOrder(input: {...})`
**Then** the document is inserted through `frappe.get_doc(...).insert()` without ignore flags, and the payload `{ name, doc }` is re-read through the read planner

**Given** input that sets a field above the user's write permlevel, or one masked for them
**When** the mutation runs
**Then** it is rejected with `FORBIDDEN`

**Given** a user who can create but not read the result
**When** the mutation succeeds
**Then** `name` is returned and `doc` is `null` with `NOT_FOUND`

### Story 3.2: Sparse update, including child rows

As an API client,
I want updates to change only the fields I send,
So that values hidden from me are never overwritten.

**Acceptance Criteria:**

**Given** a Sales Order with a masked field
**When** I call `updateSalesOrder(name, input: { deliveryDate })`
**Then** only `delivery_date` changes, and the masked value is preserved

**Given** an `items` input list
**When** the update runs
**Then** rows with `name` are patched (hidden columns kept), rows without `name` are inserted, and existing rows left out are deleted

**Given** an item row `name` that belongs to another document or another table field
**When** the update runs
**Then** it is rejected with `FORBIDDEN`

**And** `set_only_once` fields are absent from the update input

### Story 3.3: Delete and submitted documents

As an API client,
I want to delete drafts and get a clear error on locked documents,
So that I can't corrupt submitted records.

**Acceptance Criteria:**

**Given** a draft the user may delete
**When** `deleteSalesOrder(name)` runs
**Then** it is deleted through `frappe.delete_doc`

**Given** a submitted or cancelled Sales Order
**When** the user updates a field that is not `allow_on_submit`, or deletes the document
**Then** it is rejected with `VALIDATION`, and only `allow_on_submit` fields may change

**Given** a document the user cannot read
**When** they update or delete it
**Then** they get `NOT_FOUND`

### Story 3.4: All-or-nothing mutation requests

As an integrator,
I want a request's mutations to succeed or fail together,
So that I never end up with partial writes.

**Acceptance Criteria:**

**Given** a request with two mutations where the second fails validation
**When** it executes
**Then** the transport rolls back both, both results are `null` with their errors, and nothing is committed

**Given** all mutations succeed
**When** the request ends
**Then** Frappe commits once, mutations run in document order, and `writes.py` never commits

## Epic 4: Integration readiness and operations

Integrators and tool builders (including MCP authors) can export the schema and rely on stable errors. Administrators can observe, upgrade and uninstall DocWeave cleanly.

### Story 4.1: SDL export

As a tool builder,
I want to export the schema as SDL,
So that external tooling (such as an MCP server) can consume it without custom code.

**Acceptance Criteria:**

**Given** a System Manager
**When** they POST to `docweave.api.sdl`
**Then** they receive the current SDL, with descriptions and custom scalars

**Given** a non-System Manager, or a GET request
**When** they call the endpoint
**Then** it is refused

### Story 4.2: Error contract and request logging

As an administrator,
I want every request logged with its key numbers, and errors mapped consistently,
So that I can diagnose problems without leaking data.

**Acceptance Criteria:**

**Given** any request
**When** it completes
**Then** `frappe.logger("docweave")` writes one line with duration, query count, candidates scanned, cost and the codes returned, and no field values or cursors

**Given** an unexpected exception
**When** it occurs
**Then** the client gets `INTERNAL` with no traceback, and `frappe.log_error` records it without local variables

**Given** each Frappe exception class listed in AD-15
**When** it is raised in the adapter
**Then** it maps to the documented code (test per class)

### Story 4.3: Upgrade and uninstall lifecycle

As an administrator,
I want clean upgrades and uninstalls,
So that DocWeave never leaves stale state behind.

**Acceptance Criteria:**

**Given** a new release with a Settings change
**When** I run `bench migrate`
**Then** the patches in `patches.txt` apply and `schema_revision` is bumped

**Given** DocWeave is uninstalled
**When** `after_uninstall` runs
**Then** every `docweave:*` Redis key is deleted

**And** the README states the release's tested Frappe v16 and ERPNext versions (NFR-2)
