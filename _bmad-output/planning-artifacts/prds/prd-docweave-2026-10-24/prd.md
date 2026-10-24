---
title: DocWeave
status: draft
created: 2026-10-24
updated: 2026-10-24
---

# PRD: DocWeave
*Working title — confirm.*

## 1. Vision
DocWeave is a pure-Python Frappe app that adds a permission-correct GraphQL API to Frappe v16. A client asks for a Sales Order, its Customer and its child rows in one request and gets back exactly the fields it asked for, with none of the per-document round trips Frappe's REST API forces today.

The existing option, `leam-tech/frappe_graphql`, appears stale and lacks Frappe 15+ support, so v16 has no GraphQL layer. DocWeave fills that gap as a hobby project. It is GraphQL only. The reason for it is better access to Frappe data for applications and integrations: no N+1 round trips, precise field selection, and richer querying and updating. MCP is a secondary benefit, not a driver: no MCP server is planned, but because GraphQL is a strong base for MCP tooling, design choices should not make that harder. `[ASSUMPTION: hobby scope; solo builder; open-source release is optional]`

## 2. Target User
### 2.1 Jobs To Be Done
- **Frontend/mobile developer:** fetch a document graph (parent, links, child tables) in one request, selecting only the fields needed.
- **Integrator:** query and update Frappe data with typed filters and predictable pagination.
- **AI-agent/tool builder:** discover the schema by introspection and run bounded queries that cost few tokens.
- **Frappe administrator:** choose which DocTypes are exposed and trust that Frappe permissions still hold.

### 2.2 Non-Users (v1)
Frappe v15 or older installs (v16 only); anonymous public access.

### 2.3 Key User Journeys
- **UJ-1.** Dana, a mobile developer, loads a Sales Order screen. One query returns the order, its customer name, its item rows and a masked credit limit (`null` plus a `MASKED` error). She renders the screen from one round trip.
- **UJ-2.** Raj, an administrator, installs DocWeave, opens DocWeave Settings, enables the endpoint and adds Sales Order and Customer. Nothing else is reachable.
- **UJ-3.** Dana pages through 5,000 Sales Orders where the user can see only a few. Pages come back short with a continuation cursor; the client keeps going and never loops.
- **UJ-4.** Dana updates a Sales Order's delivery date with a mutation. A user without write permission gets a permission error.

## 3. Glossary
- **Exposed DocType** — a DocType listed in DocWeave Settings; the only DocTypes present in the schema.
- **Candidate** — a record scanned by a query before the permission check.
- **Scan budget** — the maximum candidates examined per request.
- **Cursor** — signed, opaque token for the last scanned candidate, bound to user and filter.
- **Masked field** — a field whose value Frappe hides from the current user.
- **Planner** — component that batches data loads before GraphQL execution.
- **Data adapter** — the single Frappe v16 data-access layer.

## 4. Features
### 4.1 Schema and exposure
- **FR-1:** The system generates a GraphQL schema from Exposed DocTypes only. Nothing is exposed until configured. Realizes UJ-2.
- **FR-2:** An administrator configures exposure, page-size and scan-budget limits and enable/disable in a DocWeave Settings Single DocType, admin-only and never itself exposed. Changes take effect after commit by invalidating the per-site schema revision.
- **FR-3:** The system exposes the endpoint only when enabled in settings.

### 4.2 Reads
- **FR-4:** A client can query documents with typed filters, field selection, links and child tables in one request. Realizes UJ-1.
- **FR-5:** The planner batches loads so request cost does not grow with the number of parent rows (no N+1). `[ASSUMPTION: benchmark target to be set in architecture]`
- **FR-6:** Every read goes through the data adapter's single authorized query function using the session user, with no unrestricted data paths. Realizes UJ-1.
- **FR-7:** Masked values return `null` plus a field-level `MASKED` error. Masking is detected from field metadata and permissions, not from comparing values.

### 4.3 Pagination
- **FR-8:** Queries use cursor pagination. A request that hits the scan budget returns a short page, `scanLimitReached: true` and a continuation cursor, never an error. Realizes UJ-3.
- **FR-9:** The cursor marks the last scanned candidate, is signed and bound to user and filter, and is returned even on an empty page that has more candidates.
- **FR-10:** `hasNextPage` is true when candidates remain and false only when exhaustion is known. This is documented as a conservative signal.

### 4.4 Writes
- **FR-11:** A client can create, update and delete Exposed DocTypes through mutations that apply Frappe's own write permissions and validation. Updates change only the fields sent, so values hidden from the user are never overwritten. A request's mutations succeed or fail together. Realizes UJ-4. `[ASSUMPTION: submit/cancel/amend and bulk operations are later]`

### 4.5 MCP-readiness (secondary)
*Low-cost design constraints so third parties can build MCP servers on DocWeave. They never take priority over 4.1–4.4. DocWeave ships no MCP server.*
- **FR-12:** The schema supports introspection, and the system enforces query depth and cost limits. `[ASSUMPTION: persisted operations are a later option]`
- **FR-13:** Schema types and fields carry descriptions taken from Frappe field labels and help text.
- **FR-14:** Errors carry actionable messages and machine-readable codes (e.g. `MASKED`, scan limit, depth/cost exceeded).
- **FR-15:** The schema can be exported as SDL.

**Non-goal:** an MCP server, MCP-specific tooling or MCP-driven schema decisions.

## 5. Non-Functional Requirements
- **NFR-1 Security:** no GraphQL read bypasses `_authorized_query`, enforced by an AST lint rule, integration tests and review rules. Document-level `has_permission` hooks are tested explicitly.
- **NFR-2 Compatibility:** Frappe v16 only, tested against the exact installed release because masking and child-table parent-context bugs have been documented.
- **NFR-3 Stack:** pure Python, built on `graphql-core`, no version-compatibility framework.
- **NFR-4 Testing priority:** permissions, masking, cursor correctness.

## 6. Success Metrics
- A Sales Order with customer and items loads in one request with a constant, small number of database queries. *Counter-metric:* no permission leak in any test.
- Pagination over a long run of unauthorized records terminates and visits each candidate once.

## 7. Milestone
First vertical slice: a Sales Order query with tests for restricted Customers, child-table masking, document-level permission hooks and pagination across long unauthorized runs.

## 8. Open Questions
- ~~Does `frappe.qb` apply field masking?~~ Resolved from the v16 source: yes, when `ignore_permissions=False`. A runtime test is still required.
- Is there a v15/v16 branch of `leam-tech/frappe_graphql`?
- Child retrieval: Frappe child queries or explicit permission-aware batches, decided by benchmark and security tests.
- Subscriptions and file uploads: in or out?
- Frappe v16 now ships a built-in MCP server (`/api/v2/mcp`, 14 tools). DocWeave positions itself as a complementary typed, batched read layer. Revisit integration after v1.
