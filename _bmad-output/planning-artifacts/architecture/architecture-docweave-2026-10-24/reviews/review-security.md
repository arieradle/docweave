---
name: 'DocWeave architecture spine: security review'
type: architecture-review
lens: security (authorization and data leaks)
target: '../ARCHITECTURE-SPINE.md'
created: '2026-10-24'
reviewer: ad-hoc security reviewer
---

# Security Review: DocWeave Architecture Spine

## Verdict

**Not ready to bind as written.** The read path is sound in concept: one chokepoint (AD-2), per-document `has_permission` (AD-4), masking driven by metadata (AD-5) and its own authorization for links and children (AD-7). The gaps are at the edges. The cursor leaks data about documents that AD-4 rejected. Child rows are not bound to their `parentfield`. The mutation input surface is undefined. The endpoint accepts GET by default, which skips CSRF. Caught field errors break the "one request is one transaction" rule. None of these needs a paradigm change. Each needs either a new AD or a tightened rule.

Severity counts: **0 critical, 5 high, 8 medium, 7 low.**

Claims about Frappe behavior come from the `version-16` branch: `frappe/database/query.py`, `frappe/permissions.py`, `frappe/model/document.py`, `frappe/model/meta.py`, `frappe/model/__init__.py`, `frappe/query_builder/utils.py`, `frappe/auth.py`, `frappe/__init__.py`, `frappe/app.py` and `frappe/utils/response.py`.

---

## High

### H1. The keyset cursor leaks the name and sort value of documents that AD-4 rejected

- **Affected:** AD-8, AD-4
- **Facts:** The cursor is HMAC-signed and base64url-encoded, but not encrypted. It carries `last_scanned_key`, which is the (`orderBy` value, `name`) of the **last scanned candidate**, and it is issued even for an empty page. Candidates are rows that passed SQL-level permissions but have **not yet** passed `frappe.has_permission`. Several kinds of document pass SQL but fail `has_permission`:
  - documents denied by a controller `has_permission` hook
  - every document for a user who holds only `select` (`get_query` checks `select` in `check_select_permission`, and `select` is granted widely so users can pick Link values)
  - documents denied by `if_owner` edge cases
- **Attack:** User U has `select` on Customer, or a `has_permission` hook hides "key accounts". U runs `customers(first: 1, orderBy: {field: CREATION})` and decodes `pageInfo.endCursor` with base64. The page is empty, but the cursor shows `name="Key Account Ltd"` and its creation timestamp. U walks the cursor to enumerate every hidden name and sort value. The cursor also carries `user` (an email address) in plaintext, so cursors in client logs or screenshots disclose PII. With a filter, the decoded cursor becomes a membership oracle. "Did any candidate match `territory = X`?" is answered by whether `last_scanned_key` moved.
- **Context:** Frappe's own `/api/resource` list never calls per-document `has_permission`, so it would show hook-denied rows outright. Still, AD-4 exists precisely to be stricter, and the cursor quietly reverses that guarantee.
- **Fix:**
  1. Make the cursor opaque. Encrypt it with AEAD: AES-GCM or Fernet, using a key derived with HKDF from `encryption_key` and the label `docweave/cursor/v1`. Alternatively, store the scan position in `frappe.cache` under a random 128-bit id bound to the user and filter hash, with a TTL, and return only the id.
  2. Drop `user` from the plaintext. Bind it through the AEAD associated data instead.
  3. Add a negative test to `test_pagination.py`: decoding a cursor issued over unauthorized rows must not reveal any name.

### H2. Child rows are not bound to `parentfield`, so permlevel on table fields can be bypassed

- **Affected:** AD-7, AD-3 (batched preload)
- **Facts:** AD-7 sets only `parent_doctype` for child loads. In Frappe, one child DocType can back several Table fields on the same parent, each with its own `permlevel`. `has_child_permission` checks `parent_meta.get_field(parentfield).permlevel` against `get_permlevel_access`, but only when it receives a concrete `child_doc` that carries `parentfield`. `get_query` with `parent_doctype` checks the parent's `select`/`read` permission, not the permlevel of a specific table field. AD-3 batches child loads per (DocType, level). If that batch filters on `parenttype` and `parent IN (...)` but not on `parentfield`, the rows of a restricted table land beside the rows of an open one.
- **Attack:** A parent has `items` at permlevel 0 and `restricted_items` at permlevel 1, both of child type `Pricing Row`. The schema exposes `items: [PricingRow!]!`. The batched loader fetches every `Pricing Row` for the parent names and groups them by parent, so `restricted_items` rows appear inside `items`. The same thing happens if the planner merges two selections of the same child type.
- **Fix:** Add to AD-7: every child load filters on `parenttype`, `parentfield` **and** `parent IN (authorized parents)`. Before the load, the adapter checks the permlevel of the table field on the parent for the user (`get_permlevel_access("read")`). An unreadable table field returns `null` plus `FORBIDDEN`, so `[ChildType!]!` must become nullable for any table field with permlevel above 0. Masking for child rows uses `get_masked_fields(parenttype=parent)`. Add a negative test for two table fields of the same child type at different permlevels.

### H3. The mutation input surface is undefined, and Frappe's write-side guards are partial or silent

- **Affected:** AD-9, Consistency Conventions (root fields, inputs), Deferred (submit/cancel, child patch)
- **Facts (v16 `document.py`):**
  - `validate_higher_perm_levels` *silently* resets parent fields the user cannot reach by permlevel. For a **new** document it returns before resetting child tables ("If new record then don't reset the values for child table"). On `insert`, a user can therefore set **child-row fields above their permlevel**.
  - `_restore_masked_fields_from_db` restores masked values only on update, only for non-new rows and only by matching `row.name`.
  - `child.db_update()` runs `UPDATE ... WHERE name=%s` with no check on `parent` or `parenttype`. I found no ownership guard for child rows in `document.py` or `base_document.py`, so this needs a test to confirm. `update_child_table` deletes the parent's rows that are missing from the payload.
  - Frappe does not generally enforce `read_only` on the server. Fields such as `status`, totals and `per_billed` hold whatever is sent unless a controller recomputes them.
  - Setting `docstatus` from 0 to 1 through `save()` performs a **submit**, gated only by the `submit` permission (`check_docstatus_transition`). That brings in-scope a flow the spine lists as deferred.
- **Attacks:**
  1. On `createSalesOrder(input: {items: [{..., margin_rate: 99}]})`, the permlevel-1 child field `margin_rate` is persisted.
  2. If the child input type exposes `name`, the attacker can update an order they own with `items: [{name: "<child row of someone else's order>", qty: 0}]`. The row is updated by name and re-parented to the attacker's document (`set_parent_in_children`). That is cross-document tampering and theft.
  3. If the child input type omits `name`, "replace wholesale" turns every row into an insert. Masked values and child values above the user's permlevel are lost or reset to defaults, so a plain edit **destroys data the user cannot see**.
  4. `updateX(input: {docstatus: 1})` or `{workflowState: "Approved"}` runs submit or workflow transitions outside the deferred design. Workflow is validated in `validate_workflow`, but its effect still needs a test.
- **Fix:** Add a new AD, "Mutation input contract":
  - Input types are generated only from fields the schema marks as writable.
  - Exclude standard and system fields (`name` unless autoname is Prompt, `owner`, `creation`, `modified*`, `docstatus`, `idx`, `parent*`, `amended_from`, `workflow_state`, `_*`).
  - Exclude `read_only`, `fetch_from` (unless `fetch_if_empty`), virtual and computed fields, plus Password, Button, HTML and other display fieldtypes.
  - Exclude `set_only_once` fields from update inputs.
  - At request time, the adapter rejects any provided field whose permlevel the user cannot write, or which is masked for them, with `FORBIDDEN`. Never rely on Frappe's silent reset.
  - Child rows: either (a) forbid `name` and define replace semantics that keep hidden and masked columns of matched rows (a server-side merge keyed by a validated row identity), or (b) allow `name` only after the adapter checks that the row belongs to this `parent` and `parentfield`.
  - Reject mutations on submitted or cancelled documents except fields marked `allow_on_submit`.
  - Add negative tests for each case.

### H4. GET is accepted by default, so mutations bypass CSRF

- **Affected:** AD-12
- **Facts:** `frappe.whitelist(methods=None)` defaults to `["GET", "POST", "PUT", "DELETE"]`. `HTTPRequest.validate_csrf_token` returns early when the method is not in `UNSAFE_HTTP_METHODS`, so GET carries no CSRF check. `app.py` commits only for unsafe methods, but controllers and hooks that enqueue jobs, send email, call external systems or call `frappe.db.commit()` will produce side effects anyway. The mutation response also says "success" even though the core write rolls back.
- **Attack:** A logged-in victim loads `<img src="https://erp.example.com/api/method/docweave.api.graphql?query=mutation{deleteX(name:\"...\")}">`, or a mutation whose hooks send email. The cookie session authenticates the request with no CSRF token. Query strings also end up in proxy and access logs and in the Referer header.
- **Fix:** In AD-12, use `@frappe.whitelist(methods=["POST"])` and reject any operation other than a `query` (and introspection) that does not arrive by POST with a JSON body. Do not accept `query` in the URL query string. Require `Content-Type: application/json`, which also blocks simple form-encoded cross-site POSTs, alongside Frappe's CSRF check. Add a negative test.

### H5. Field errors break "one request is one transaction", so partial writes get committed

- **Affected:** AD-9, AD-3, error shape
- **Facts:** GraphQL returns partial success: a resolver error becomes an `errors[]` entry, and the HTTP request still succeeds. Frappe commits on any request that completes without an exception (`app.py`). If a mutation's `insert()`/`save()` raises *after* earlier writes have run, and DocWeave turns that into a `VALIDATION` field error, the request does not raise and Frappe **commits the partial writes**. Earlier writes can include `db_set` in hooks, linked-document updates, Version and Comment rows, or child inserts. The same applies to several mutation fields in one operation (aliases).
- **Attack:** An agent sends `a: updateX(...)` then `b: updateY(...)` where `b` fails validation. Mutation `a`, plus any half-applied side effects of `b`, is committed. A controller that writes before it throws in `validate`/`on_update` leaves inconsistent state, which can amount to a validation bypass.
- **Fix:** In AD-9, wrap each mutation field in `frappe.db.savepoint(...)` and roll back to it on any exception before turning the exception into a field error. Alternatively, define that any mutation error fails the whole operation: roll back explicitly and set `data: null`. Allow at most N mutation fields per operation, with N as a setting defaulting to 1 for v1. Add a test where a hook writes and then throws.

---

## Medium

### M1. Reads have no field-level `FORBIDDEN`, and mandatory permlevel fields are non-null

- **Affected:** AD-5, AD-11, conventions (scalars)
- **Facts:** `get_query(..., ignore_permissions=False)` **silently drops** selected fields the user cannot reach by permlevel (`apply_field_permissions`), with no error. The spine handles masks (AD-5) but not permlevel. The convention "nullable unless mandatory and never maskable" makes a *mandatory* permlevel-1 field `Type!`.
- **Impact:** A user without permlevel 1 gets `null` on a non-null field. graphql-core then propagates the null up to the nearest nullable parent, wiping the edge, the connection or `data` entirely. That is a correctness failure, and an attacker-triggerable denial of results for others in shared agent sessions. An omitted field also looks the same as a genuine null, which hides the security posture.
- **Fix:** A field is non-null only if it is mandatory, at permlevel 0, never maskable, and not under a Table field with permlevel above 0. The adapter computes `get_permitted_fields(..., permission_type="read", parenttype=...)` itself and returns a `FORBIDDEN` marker per field, parallel to `MASKED`. `xDoc` is always nullable.

### M2. Existence oracles: `NOT_FOUND` versus `FORBIDDEN`

- **Affected:** AD-7, conventions (root fields, error shape), AD-9
- **Attack:** `salesOrder(name: "SO-0042")` returns `NOT_FOUND` when the document is absent and `FORBIDDEN` when it exists but is hidden, which confirms names and enumerates the numbering series. The same oracle appears on `updateX`/`deleteX`, and on `xDoc`, where a dangling link returns null/`NOT_FOUND` and a hidden one returns `FORBIDDEN`. `createX` on DocTypes with Prompt naming raises `DuplicateEntryError` for names the user cannot read.
- **Fix:** For a single-document lookup by name, return `NOT_FOUND` unless the user has read on the DocType *and* the document passes AD-4. Return `FORBIDDEN` only for field-level denial on a document already authorized. For updates and deletes, check read first and return `NOT_FOUND` on failure. Map a duplicate name to a generic `VALIDATION` error without the name, and document the residual oracle. Add negative tests.

### M3. Frappe's response envelope leaks messages that DocWeave already turned into codes

- **Affected:** error shape ("No tracebacks go to clients"), AD-12, Logging
- **Facts:** `frappe/utils/response.py` (`_make_logs_v1`) copies `frappe.local.message_log` into `_server_messages` on *every* JSON response. In developer mode it also copies `exc`, `_exc_source` and `_debug_messages`. `frappe.throw` and `msgprint` inside `get_query`, `has_permission`, controllers or ERPNext validators append to `message_log` even when DocWeave catches the exception. Examples are "Insufficient Permission for {doctype}", "You do not have permission to access field: Sales Order.margin" and the ERPNext credit-limit message, which states a customer's outstanding amount.
- **Fix:** In AD-12, the transport clears `frappe.local.message_log`, `frappe.local.error_log` and `frappe.local.debug_log` before it returns. It writes the GraphQL body itself (a `Response` object, or `frappe.response` set by hand) so no `_server_messages`, `exc` or `message` envelope is emitted. The text of a `VALIDATION` error comes from an allow-list: the exception class plus a sanitized message. `INTERNAL` logs use `frappe.log_error` without local-variable context, so no cursors or values end up in the Error Log. Add a test that asserts the exact set of top-level response keys.

### M4. The cost and scan limits fail under aliases, child tables, link fan-out and batching

- **Affected:** AD-10, AD-4, AD-3
- **Facts:**
  - The scan budget (2,000 candidates) appears to apply per connection. AD-4 runs `has_permission` for each candidate. If the adapter passes a name, `has_permission` calls `get_lazy_doc`, roughly one query per candidate, plus any hook queries.
  - `[ChildType!]!` is unpaginated and absent from the "rows × fields" formula. Sales Orders with thousands of items are common.
  - `xDoc` fans out per row.
  - The spine does not say how JSON-array batching, document size or token count are handled.
- **Attack:** 50 aliases × `salesOrders(first: 100)`, each scanning 2,000 hook-denied candidates, gives 100k `has_permission` evaluations in one request. Alternatively, `salesOrders(first: 100) { items { itemCodeDoc { ... } } }` loads 100 × 5,000 children. Add a megabyte-scale query or deep `__type { ofType { ... } }` introspection.
- **Fix:**
  - Make the scan budget **request-global**: one counter shared across all aliases and connections.
  - Cost must include an estimated child-row count (configurable per table, defaulting to `max_children`) and link fan-out. Enforce a hard cap on child rows per parent: truncate with a `COST_LIMIT` error.
  - Set a `max_aliases` / `max_root_fields` limit, reject JSON-array batches (or count them as one budget), and use graphql-core `parse(..., max_tokens=...)` with a cap on body size.
  - Introspection counts toward depth, or is answered from a precomputed result.
  - Set a wall-clock timeout per request. Do not leave per-user rate limiting deferred if the endpoint targets agents. At minimum, document Frappe's `rate_limit` decorator on the endpoint.

### M5. `has_permission` on partial candidate rows evaluates hooks against incomplete documents

- **Affected:** AD-4
- **Facts:** `frappe.has_permission(doctype, "read", doc, user)` evaluates role permissions, `if_owner`, User Permissions on Link fields (`has_user_permission` skips empty links when strict mode is off) and controller hooks. All of these read fields from `doc`. If the adapter passes a dict holding only the *selected* fields, then `owner`, link fields and hook-relevant fields read as empty. Hooks written as `if doc.company and doc.company not in allowed: return False` fail **open**. Passing a name string fails closed, but costs a query per candidate (M4).
- **Fix:** Specify that AD-4 always selects a "permission projection": `owner`, `docstatus`, every Link field without `ignore_user_permissions`, and every field declared by a DocWeave permission hint for a hook. The adapter builds a `frappe._dict` or lazy document from that projection. Document that apps whose hooks need more fields must declare them, and test this with a hook that reads an unselected field.

### M6. The filter and sort grammar is not pinned down, so AD-6 has holes

- **Affected:** AD-6, AD-2, conventions
- **Facts:**
  - AD-6 says "cannot read", but `get_query` permits *select-only* users to filter and sort on **all permlevel-0 fields** (`_get_filterable_fields`). Masked fields are also allowed, because they fall within permlevel read access.
  - `get_query` accepts dotted Link-target and child-table filters. The check on the joined target happens at the DocType level, not per document, so a join filter probes attributes of linked documents the user cannot read under User Permissions.
  - `fields` and `order_by` accept SQL function strings and pypika `Term`s, which pass `apply_field_permissions` unchecked.
- **Fix:** Define AD-6 as a closed grammar. Filters and sorts apply only to the DocType's own scalar fields. A field qualifies only if it is in `get_permitted_fields(permission_type="read", parenttype=...)` minus `get_masked_fields(...)`. A user without `read` on the DocType gets no filtering at all. No dotted, child or Link-target filters in v1. `orderBy` is a generated enum, and the adapter writes the `order_by` string itself. `fields` contains plain validated fieldnames only, never strings or Terms. Extend `_authorized_query` with a typed `after: KeysetPosition` parameter so the keyset predicate is never added to the query afterwards. Adding it afterwards also risks dropping `_doctype`/`_fields_list`, the metadata Frappe needs for masking.

### M7. Exposure policy: Dynamic Link fields, links to DocTypes that are not exposed, child or Single roots, and core DocTypes

- **Affected:** AD-11, AD-7, conventions (field names)
- **Gaps:**
  1. **Dynamic Link** fields are not mentioned. A generated `xDoc` would resolve to whatever DocType the companion field names, *including DocTypes that are not exposed*.
  2. A Link to a DocType that is not exposed (User, Role, DocType...) needs a rule. The spine only says that `xDoc` is generated.
  3. Child DocTypes as Exposed roots, where `get_query` fails without `parent_doctype` or the client could supply one, and Single DocTypes (`issingle`), have no defined root shape.
  4. For `CORE_DOCTYPES` other than User, `get_permitted_fields` returns **all columns**, ignoring permlevel.
  5. Password fields, along with `api_key`/`api_secret` on User, must never be in the schema.
- **Fix:**
  - Generate `xDoc` only when the target is exposed. A Dynamic Link resolves only to exposed targets, through a union or interface; otherwise it returns `FORBIDDEN`.
  - Forbid child DocTypes and Singles as roots in v1.
  - Keep a hard-coded denylist that the settings cannot override: DocWeave Settings, User, Has Role, User Permission, DocShare, DocPerm, Custom DocPerm, OAuth*, Access Log, Error Log, Session Default, System Settings, Contact Us Settings, Integration Request and the other core DocTypes.
  - Never generate fields of type Password.

### M8. Portal (Website) users get the endpoint and full introspection

- **Affected:** AD-12, AD-11
- **Facts:** `allow_guest=False` still admits **Website Users** (customers and suppliers on the portal). Introspection exposes every exposed DocType, field name and help text, which reveals internal data models and field names such as `margin_rate` and `credit_limit` to external parties. Data access is still permission-checked, but portal roles often hold `if_owner` or shared access, and the schema itself is reconnaissance.
- **Fix:** Add `allowed_roles` to DocWeave Settings, defaulting to System Users only. Gate introspection by role (`introspection_roles`), or disable it for Website Users. Strip help text marked internal. Add a test where a Website User receives `NOT_EXPOSED`.

---

## Low

### L1. A raw Link name (`x: String`) reveals names of linked documents the user cannot read

- **Affected:** conventions (field names), AD-7
- This matches Frappe desk and REST behavior, so it is not a regression. It does matter where names carry content (Employee "HR-EMP-0001", Customers named after people, naming by `full_name`). **Fix:** State the parity decision in AD-7. Optionally add a per-DocType setting, `redact_unreadable_link_names`, that nulls `x` when `xDoc` would be `FORBIDDEN`.

### L2. Schema cache: user-dependent build inputs and races on revision bumps

- **Affected:** AD-11
- **Issues:**
  - The first requester's language (descriptions passed through `_()`) or any user-dependent call (`get_masked_fields` caches per user) would be baked into the site-wide schema.
  - A request can read the new `schema_revision` while `frappe.get_meta` still serves stale meta, caching a stale schema under the new key indefinitely.
  - `bench migrate` and app installs may not fire `doc_events`.
  - A Custom Field whose name collides in camelCase (`a_b` and `a__b`) fails the build "loudly", so anyone with Customize Form rights can take the API down site-wide.
- **Fix:**
  - Build as a fixed context: English or the site language, with no `session.user` calls; enforce this with a boundary test.
  - Key the cache on (`schema_revision`, the hash of the relevant meta `modified` timestamps), and bump in `after_migrate` and `after_install`.
  - On collision, skip the offending field, log it, and surface it in Settings rather than failing the whole build.

### L3. Cursor key management

- **Affected:** AD-8
- The spine gives no key id, no rotation, no TTL, and no KDF label (raw reuse of `encryption_key` across Frappe's Fernet use and this HMAC). The cursor also binds to neither `schema_revision` nor role-set changes.
- **Fix:** Use HKDF with a purpose label, put a `kid` in the cursor, accept the current and previous key, and set a TTL (for example 24h, `iat` in the cursor). Treat expiry or a `kid` mismatch as `BAD_CURSOR`. This is mostly hygiene, because the cursor never grants authority.

### L4. Count and timing oracles via `scanLimitReached`, `hasNextPage` and `has_permission` latency

- **Affected:** AD-8, AD-4
- Even with an opaque cursor, `first: 1` plus a filter reveals whether at least N hidden candidates match (`scanLimitReached`). Per-candidate `has_permission` time correlates with the hidden count. **Fix:** Accept this as documented residual risk, at parity with Frappe list APIs. Never add `totalCount` or aggregates without AD-4 semantics, and add that rule to AD-8.

### L5. Administrator and privileged API keys

- **Affected:** AD-2, AD-5, AD-12
- `has_permission` returns True for `Administrator`. `apply_fieldlevel_read_permissions`, `validate_higher_perm_levels` and `_restore_masked_fields_from_db` all skip Administrator. Integrations often use an Administrator API key, which returns everything unmasked to an agent. **Fix:** Add a setting `deny_administrator` (default on), or a loud warning. Recommend a dedicated integration user. Enable `track_changes` on DocWeave Settings so changes to exposure are audited, and limit writes to it to System Manager.

### L6. Mutation re-read when the user can create but not read

- **Affected:** AD-9
- AD-9 re-reads through AD-2. If the user has `create` but not `read` (for example `if_owner` edge cases or a custom role), the payload must return `null` plus `FORBIDDEN` for the document, never the document as inserted. Add a test.

### L7. The prohibition on resolver I/O conflicts with mutations

- **Affected:** AD-3, AD-9
- AD-3 says resolvers may only read the result graph, but mutation resolvers must write. Without an explicit carve-out, implementers will invent ad-hoc paths. **Fix:** State that mutation root resolvers call adapter write methods only, run sequentially under H5's savepoints, and that their selection sets go through the AD-3 planner for the re-read.

---

## Tests the spine should require (in addition to its convention that each AD has a negative test)

1. A decoded cursor over hook-denied or select-only rows reveals no name or value (H1).
2. Two table fields of the same child type at permlevels 0 and 1 (H2).
3. A child permlevel field on insert, a foreign child row `name` on update, and masked child values kept across replace (H3).
4. A mutation over GET is rejected, and a POST without a CSRF token is rejected (H4).
5. A hook that writes and then throws leaves no committed rows (H5).
6. A mandatory permlevel-1 field for a user without access does not null the edge (M1).
7. `NOT_FOUND` is returned the same way for absent and hidden documents (M2).
8. Response keys are exactly `{data, errors}`, with no `_server_messages` (M3).
9. The scan budget is shared across aliases (M4).
10. A `has_permission` hook that reads an unselected field (M5).
