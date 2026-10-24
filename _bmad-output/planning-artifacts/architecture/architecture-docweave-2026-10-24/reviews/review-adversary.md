---
type: architecture-review
lens: adversarial (compliant-but-incompatible unit pairs)
target: ../ARCHITECTURE-SPINE.md
prd: ../../../prds/prd-docweave-2026-10-24/prd.md
reviewer: BMAD adversarial architecture reviewer
date: 2026-10-24
verdict: NOT READY. The spine fixes the boundaries but not the data that crosses them. Two teams can follow every AD to the letter and still ship a data leak (H-1, H-2), silent data loss on update (H-3), or a paginator that skips rows (H-6).
---

# Adversarial Review: DocWeave Architecture Spine

## Method

For each hole I name two units one level below the spine (modules from the Structural Seed, or roles inside them). Each unit is built by a separate, careful implementer who obeys AD-1 to AD-12 and the Consistency Conventions literally. The hole is the way their outputs still fail to fit. Every hole ends with proposed AD text. The spine itself is not edited.

Severity scale:
- **Critical:** a permission or masking leak, or silent data corruption, is possible.
- **High:** wrong results (skipped or duplicated rows, wrong nulls), or a v1 FR cannot be met.
- **Medium:** integration breakage that tests would catch, but only after rework.
- **Low:** friction or inconsistency.

## Summary

| # | Units in conflict | Clash type | Severity |
| --- | --- | --- | --- |
| H-1 | Adapter masking vs planner link/child key collection | Derived loads from hidden source fields | Critical |
| H-2 | `cursor.py` (signed, not encrypted) vs AD-4 candidate filtering | Cursor leaks unauthorized rows | Critical |
| H-3 | Read path (masked becomes `null`) vs `writes.py` (update and wholesale child replace) | Masked/unreadable values overwritten on round trip | Critical |
| H-4 | `execution/graph.py` vs `adapter/` | Two owners of the MASKED sentinel, error enum and row shape; dependency direction forbids sharing | High |
| H-5 | AD-3 batch preload vs AD-4 per-candidate `has_permission` | Either N+1 or hooks see partial docs | High |
| H-6 | Adapter chunked query vs `cursor.py` "last scanned" | Scanned = fetched vs checked: skipped rows | High |
| H-7 | Keyset SQL builder vs `cursor.py` comparator | Tie-break direction, NULLs, collation, value encoding | High |
| H-8 | Planner's filter hash vs adapter's filter hash; schema filter input vs adapter `filters` | No filter grammar, no canonical form | High |
| H-9 | Planner plan key (DocType, level) vs aliases and shared child DocTypes | Plan format collapses distinct loads | High |
| H-10 | Generic AD-4 loader vs child loader; Settings vs builder | Child DocTypes: `has_permission` semantics and root exposure | High |
| H-11 | `schema/builder.py` nullability vs adapter masking/permlevel at data time | Non-null fields resolve to null; revision misses DocPerm changes | High |
| H-12 | `hooks.py` revision bump vs `frappe.get_meta` cache vs `cache.py` | Cache invalidation race; storage of revision and schema | High |
| H-13 | `api.py` transaction handling vs `writes.py` vs GraphQL partial errors | Two owners of commit/rollback | High |
| H-14 | Scan budget: root connection loader vs link/child loaders vs multiple root fields | Budget owner and scope undefined | High |
| H-15 | `rules.py` (pre-plan cost) vs `planner.py` (plan cost) | Cost computed twice, on different inputs; children unbounded | Medium |
| H-16 | `naming.py` vs `builder.py` | Field-name collisions; Link to non-exposed, Dynamic Link, Table MultiSelect | High |
| H-17 | Link loader vs root single-get | FORBIDDEN vs NOT_FOUND as an existence oracle | Medium |
| H-18 | Writes re-read vs read planner | Two paths assemble mutation results | Medium |
| H-19 | Default ordering: planner (None) vs adapter (meta `sort_field`) vs cursor `order` | Implicit order not bound into cursor | Medium |
| H-20 | `rules.py` depth limit vs introspection | Default depth 8 rejects standard introspection | Medium |
| H-21 | `schema/` resolvers vs `execution/` resolvers | Who attaches resolvers; import cycle | Medium |
| H-22 | Page-size handling: schema default vs planner clamp vs adapter limit | Clamp vs reject | Low |
| H-23 | Child row ordering across a batched load | `idx` grouping undefined | Low |

---

## H-1: Masked or unreadable source fields feed derived loads [Critical]

**Units:** `adapter/frappe_v16.py` (masking, AD-5) vs `execution/planner.py` (collecting Link keys for `xDoc` and parent names for child tables, AD-3/AD-7).

**Divergence:**
- AD-5 tells the adapter to replace masked values with `MASKED`. The adapter author does this on the row it returns.
- The planner author needs the raw values of Link field `x` to batch-load `xDoc`. Nothing says the planner may only use the post-mask value. To get keys it either (a) asks the port for "link keys" that the adapter returns unmasked, as a separate list, or (b) reads the masked row and passes `MASKED` into `name in (...)`.
- With (a), `customerDoc { name }` returns the customer name that `customer` itself masked. Every AD is obeyed: the target is loaded through `_authorized_query` (AD-7), and the masked field is `null` (AD-5). It is still a leak.
- The same thing happens with permlevel. A Table field at permlevel 1 that the user cannot read still gets its children loaded under AD-7, because AD-7 only requires that the parent passed AD-4.

**Proposed AD-13: Derived loads honour source-field readability.**
> A Link target (`xDoc`) or child table may be loaded only if the source field (`x`, or the Table fieldname) is readable and unmasked for the user on that specific parent row. If the source is masked, the derived field resolves to `null` with `MASKED`. If it is unreadable (permlevel), it resolves to `null` with `FORBIDDEN`. Keys for derived loads come only from post-mask rows returned through the port. The port exposes no unmasked key channel. A negative test covers a masked Link and a permlevel-restricted Table field.

---

## H-2: The cursor discloses unauthorized candidates [Critical]

**Units:** `adapter/cursor.py` vs `adapter/frappe_v16.py` (AD-4 candidate filtering).

**Divergence:**
- AD-8 says the cursor holds `last_scanned_key` (the `orderBy` value plus `name` of the last **scanned candidate**). It is signed with HMAC and base64url-encoded, but not encrypted.
- The last scanned candidate is often a row that failed `has_permission`. That is exactly UJ-3's case (a long unauthorized run, empty page, cursor issued anyway).
- So base64-decoding `endCursor` gives the client the `name` and sort-field value of a document it is not allowed to see. Stepping with `first: 1` lists every unauthorized name one at a time. Every AD is satisfied.

**Proposed amendment to AD-8 (cursor confidentiality):**
> Cursors are authenticated **and encrypted** (AEAD, e.g. AES-GCM or Fernet, keyed from the site encryption key with a DocWeave-specific derivation label). No field of the cursor is client-readable. Cursor contents are never logged. A test decodes a cursor issued after an unauthorized run and asserts that no candidate `name` or sort value appears in plaintext.

---

## H-3: Masked values destroyed by read-modify-write [Critical]

**Units:** the read path (AD-5: masked becomes `null`) vs `adapter/writes.py` (AD-9 plus Deferred: "update, child tables replaced wholesale").

**Divergence:**
- A client reads a Sales Order. `creditLimit` and masked child-row fields come back `null`. The client edits the delivery date and sends the object back as `updateSalesOrder(input)`, which is normal GraphQL client behaviour.
- `writes.py` does `doc.update(input); doc.save()`. Frappe's write permission allows it, and the masked field is overwritten with `null`.
- For child tables, wholesale replacement deletes the old rows and inserts the client's rows. Every masked and permlevel-hidden child value is lost. Child-row `name`s are regenerated, which breaks references to them.
- Each unit is AD-compliant. Data is silently corrupted.

**Proposed AD-14: Update input is a patch, and hidden fields are write-protected.**
> `update*` inputs are sparse. An omitted field is untouched, and only an explicit `null` clears a field. Input that sets a field which is masked or unreadable for the user is rejected with `FORBIDDEN` before any write. Child tables in update input are matched by child `name`: rows that keep their `name` keep their hidden fields, rows without a `name` are inserted, and omitted rows are deleted only if every hidden field on them is readable by the user (otherwise `FORBIDDEN`). Input types are separate from output types, and masked fields are never non-null in input. A negative test round-trips a masked parent field and a masked child field.

---

## H-4: No shared kernel for the sentinel, error codes and row shape [High]

**Units:** `execution/graph.py` ("result graph + MASKED/FORBIDDEN markers", Structural Seed) vs `adapter/frappe_v16.py` ("replaces each masked value with a MASKED sentinel", AD-5). Also `execution/errors.py` (error enum) vs adapter code that must raise `FORBIDDEN`, `BAD_CURSOR` and `VALIDATION`.

**Divergence:**
- Dependencies point `execution → port → impl`, so the adapter may not import `execution/graph.py` or `execution/errors.py`.
- The adapter author defines `adapter.MASKED = object()`. The graph author defines `graph.MASKED`. The resolver's `is graph.MASKED` check never fires, and graphql-core serializes the adapter sentinel through the `Decimal` scalar, which crashes or emits its repr.
- The sequence diagram says the adapter returns "rows, masked sets, cursor". So a second adapter author returns raw values plus a masked set and leaves the replacement to the graph builder, which puts masked values into execution memory, against the intent of AD-5. The same split hits FORBIDDEN-per-field (permlevel) and FORBIDDEN-per-link.
- The row format is unspecified (dicts keyed by `fieldname` or by camelCase? `name` always present? child rows nested or flat with `parent`/`idx`?). Two implementers will pick differently.

**Proposed AD-15: Port types are the shared kernel.**
> `docweave/adapter/port.py` (or a dependency-free `docweave/types.py` importable by every layer) is the sole owner of: the `MASKED` and `FORBIDDEN` sentinel singletons, the `ErrorCode` enum, and the typed records `Row`, `LoadRequest`, `LoadResult` and `PageResult`. A `Row` is keyed by Frappe `fieldname` (never GraphQL names), always carries `name` (plus `parent`, `parenttype`, `parentfield` and `idx` for child rows), and already has sentinels substituted. Masking is applied only inside the adapter, and no raw masked value crosses the port. `execution/errors.py` maps `ErrorCode` to `GraphQLError` and defines no codes of its own. The boundary test also forbids `adapter → execution` imports.

---

## H-5: Batched preload vs per-candidate `has_permission` [High]

**Units:** the batch loader that AD-3 requires (one query per DocType and level, selected fields only) vs the AD-4 checker (`frappe.has_permission(doctype, "read", doc, user)` per candidate).

**Divergence:**
- `has_permission` hooks and `if_owner` checks read fields such as `owner`, `company` and custom fields that the client did not select.
- Implementer A passes the partial row as `doc`. Hooks see missing fields and silently allow or deny.
- Implementer B passes `name`, so Frappe calls `get_doc` per candidate: N+1, which breaks FR-5 and AD-3, and loads every column including masked ones.
- Both implementations follow AD-4 as written.

**Proposed AD-16: Permission-check projection.**
> The adapter always fetches a fixed **permission projection** alongside the requested fields: `name`, `owner`, `docstatus`, every field named in the DocType's User Permission-relevant Link fields, and any fields a registered DocWeave `permission_fields` hook declares. It builds a lightweight doc (`frappe._dict` or an unsaved `Document` via `frappe.get_doc(dict)` without a DB load) for `has_permission`. Per-candidate DB loads are banned, and a query-count test asserts constant queries per page. Permission-projection fields are stripped before the row crosses the port unless they were also selected.

---

## H-6: "Last scanned" means fetched in one unit and checked in another [High]

**Units:** the adapter's candidate loop (fetches chunks through `_authorized_query(limit=…)`) vs `cursor.py` (encodes `last_scanned_key`).

**Divergence:**
- The adapter fetches 50 candidates per chunk. The page (`first: 20`) fills at candidate 30.
- Implementer A sets `last_scanned_key` to the last **fetched** row, candidate 50. Candidates 31 to 50 are never returned, and authorized rows are skipped.
- Implementer B uses the last **checked** row, candidate 30, which is correct. But B counts all 50 against the budget while A counts 30.
- `hasNextPage: false` "only when candidates are known to be exhausted": A infers exhaustion from `len(chunk) < limit`, while B issues one more query.
- Both follow AD-8 and AD-4 literally.

**Proposed amendment to AD-8 (scan semantics):**
> A candidate is "scanned" when it has been evaluated by `has_permission`, not when it was fetched. The cursor points at the last evaluated candidate. Only evaluated candidates count toward the scan budget. Fetched-but-unevaluated rows are discarded and re-fetched by the next page. Candidates are exhausted only when a chunk query returns fewer rows than its `limit`, and every row of that chunk has been evaluated. Each page stops at whichever comes first: `first` returned rows, the remaining scan budget, or exhaustion.

---

## H-7: Keyset ordering is underspecified [High]

**Units:** the adapter's keyset WHERE-clause builder vs `cursor.py` (serializes the key and compares it when re-checking).

**Divergence:**
- **Tie-break direction:** AD-8 says `name` is always the tie-breaker but not its direction. With `orderBy: {grandTotal: DESC}`, one unit emits `ORDER BY grand_total DESC, name ASC` and the predicate `(grand_total, name) < (v, n)`. That mixed-direction tuple comparison is wrong and skips or duplicates rows.
- **NULLs:** MariaDB sorts NULL first in ASC. `grand_total > NULL` is never true, so rows with a NULL sort value vanish or loop.
- **Collation:** MariaDB `utf8mb4_unicode_ci` compares names case-insensitively. Any Python-side comparison in `cursor.py` (e.g. the "issued even for an empty page" logic) disagrees with SQL.
- **Value encoding:** a `Decimal`, `Datetime` (site time zone) or `Date` sort value is stored in the cursor JSON. Float round-tripping or a time zone shift makes the predicate miss the boundary row.

**Proposed amendment to AD-8 (keyset algebra):**
> Order is always `(<orderBy field> <dir>, name <same dir>)`. The keyset predicate is expanded explicitly as `f <op> v OR (f = v AND name <op> n)`, never as a row-value tuple. NULL sort values are treated as `IS NULL` partitions: NULLs last for ASC and first for DESC, with explicit `IS NULL` branches in the predicate. All comparisons happen in SQL, and Python never compares keys. Cursor values are encoded with a typed codec (`Decimal` as string, `Datetime` as naive site-time-zone ISO with microseconds, `Date` as ISO). Tests cover NULL sort values, equal sort values across a page boundary, and mixed-case names.

---

## H-8: No filter grammar and no canonical filter hash [High]

**Units:** `schema/builder.py` (generates the `filter` input type), `execution/planner.py` (translates it), `adapter/frappe_v16.py` (`filters` parameter of `_authorized_query`), and `cursor.py` (`filter_hash`).

**Divergence:**
- No AD or convention defines the filter input. Builder A emits `{ creditLimit: { gt: "100" } }` with implicit AND. Builder B emits `[{ field, op, value }]`. The planner has to match the builder, but which one?
- The adapter accepts Frappe filters in either dict or list-of-lists form. AD-2 calls the parameters "closed, typed" but does not give the type.
- `filter_hash`: the planner hashes the raw GraphQL input (camelCase, input key order, variables unresolved). The adapter hashes the normalized Frappe filter list. Equivalent queries then yield `BAD_CURSOR` (inputs in a different key order), or the two sides never match at all.
- AD-6's FORBIDDEN check needs Frappe fieldnames and user permissions. The planner has neither (no Frappe access), and the adapter only sees post-translation filters, so either could own it.

**Proposed AD-17: Filter IR.**
> GraphQL filter input has one shape per DocType: `<Type>Filter { and: [..], or: [..], <field>: <ScalarOps> }`, with operators fixed per scalar (`eq ne in nin lt lte gt gte like isNull`). The planner translates it into a typed `FilterIR` (a tree of `(fieldname, op, value)` with typed values) defined in the port. The adapter is the only unit that turns `FilterIR` into `frappe.qb` criteria. It also runs the AD-6 readable/unmasked check on every fieldname in `FilterIR` and in `order_by`. `filter_hash = SHA-256(canonical JSON(FilterIR))`, where canonical means sorted keys, `and`/`or` children sorted, and typed values encoded with the H-7 codec. Only the adapter computes it.

---

## H-9: Plan key (DocType, level) collapses distinct loads [High]

**Units:** `execution/planner.py` (plan format) vs `execution/graph.py` (assembly), with AD-3's "one batched query per (DocType, nesting level)".

**Divergence:**
- Aliases: `open: salesOrders(filter: A)` and `late: salesOrders(filter: B)` are the same DocType at level 0. A literal reading forces one query, which the planner cannot build correctly (different filters, cursors and budgets).
- Shared child DocTypes: `Sales Taxes and Charges` is a child of both Sales Order and Sales Invoice. Reached at the same level from two parents, it would merge into one query with one `parent_doctype`, which misapplies AD-7's parent-aware masking for one of them.
- The graph keys results by field name while graphql-core's default resolver reads by **field name**, not response key. Two aliases of one field with different arguments then read the same slot.
- It is also unspecified whether a child table counts as a level.

**Proposed amendment to AD-3 (plan identity):**
> A load node's identity is `(DocType, parent_doctype, parentfield or link fieldname, argument fingerprint, path-from-root)`. Loads are batched only across sibling parent rows of one node, never across nodes. Each node with arguments (connection, filter, cursor) is its own query. Assembled results are stored under the GraphQL **response key** (alias), and resolvers read `info.path.key`. A child table and a Link each count as one level. The plan is a typed tree defined in `execution/planner.py` and is never passed to the adapter. The adapter receives only `LoadRequest`s (AD-15).

---

## H-10: Child DocTypes under AD-4, and as root fields [High]

**Units:** a generic loader that applies AD-4 to "each candidate" vs a child loader under AD-7. Also `docweave_settings` validation vs `schema/builder.py`.

**Divergence:**
- Child DocTypes (`istable`) have no DocPerms. A generic loader that calls `frappe.has_permission("Sales Order Item", "read", row)` gets a denial or a Frappe-version-specific fallback, so every child list comes back empty. A child loader that skips the call is a different code path, and AD-4 says "each candidate".
- Nothing stops an admin from listing a child DocType in Settings. The builder then emits `salesOrderItems(...)` as a root connection. Child rows become readable without their parent passing AD-4, which bypasses AD-7.

**Proposed AD-18: Child DocType handling.**
> Child DocTypes are never root-exposable. Settings validation rejects `istable=1` and the builder asserts it. Child types appear in the schema only through their parent's Table field. For child rows, AD-4's per-candidate check is the parent's `has_permission` (already passed), and no per-child `has_permission` call is made. Child queries always pass `parent_doctype`, `parentfield` and `parent in (authorized parent names)`.

---

## H-11: Per-site nullability vs per-user masking and permlevel [High]

**Units:** `schema/builder.py` (convention: "nullable unless mandatory and never maskable") vs the adapter at data time (AD-5, permlevel).

**Divergence:**
- "Never maskable" is decided at build time from DocPerm and Custom DocPerm `mask` settings. AD-11's revision bump list is DocWeave Settings, DocType, Custom Field and Property Setter. It omits **Custom DocPerm** and **DocPerm**, and Role changes.
- An admin enables masking on a mandatory field. The schema still says `String!`, the adapter returns `MASKED`, the resolver returns `null`, and graphql-core null-bubbles the whole parent object (or the whole page).
- The same happens for a mandatory field at permlevel 1 for a user without that level. The spine defines no representation for "unreadable" field values at all, only for masked ones.

**Proposed amendment to AD-11 plus a convention change:**
> Every DocType field is nullable in the output schema except `name`. Non-null is used only in input types (and never for masked or permlevel > 0 fields). A selected field the user cannot read (permlevel) resolves to `null` with `FORBIDDEN`, using the shared `FORBIDDEN` sentinel (AD-15). If nullability ever depends on permissions, the `schema_revision` bump list must include DocPerm, Custom DocPerm and Role.

---

## H-12: Schema revision race and schema storage [High]

**Units:** `hooks.py` (doc_events that bump `schema_revision` "after commit") vs Frappe's own `get_meta` cache clearing vs `schema/cache.py`.

**Divergence:**
- **Race:** the DocWeave after-commit bump can run before Frappe clears the meta cache for the changed DocType (or it can run in another worker's view first). Worker W2 sees revision r+1, builds the schema from the stale `get_meta`, and caches it under `docweave:schema:r+1`. It never rebuilds.
- **Stampede:** N workers each miss and build at the same time.
- **Storage:** a `GraphQLSchema` object holding resolver callables does not pickle reliably into Redis. Cache author A stores SDL text and rebuilds with `build_schema` (losing custom scalars and resolvers). Author B stores the object in a per-process dict. Both "cache in frappe.cache".
- **Where the revision lives:** in a DocWeave Settings field, bumping it saves Settings, which fires the Settings doc_event, which bumps again. In Redis, `bench clear-cache` resets it. That is harmless only if the schema keys are also cleared, which Frappe does not guarantee for every key prefix.

**Proposed amendment to AD-11 (cache mechanics):**
> `schema_revision` is a Redis integer (`docweave:schema_revision`, created on first read as a random 64-bit value, so a cache flush can never collide with an older revision) incremented by `INCR` in `frappe.db.after_commit`. The bump handler first calls `frappe.clear_cache(doctype=…)` for the affected DocTypes, then increments. Redis stores a **build input fingerprint** (a hash of Settings plus the relevant meta `modified` timestamps) next to the SDL. The built `GraphQLSchema` object lives in a per-process LRU keyed by `(revision, fingerprint)`. Builds take a short Redis lock to prevent a stampede. A worker that finds a cached fingerprint different from its own freshly computed one rebuilds.

---

## H-13: Two owners of commit and rollback [High]

**Units:** `api.py` (transport) vs `adapter/writes.py` vs the executor's error handling. AD-9 says "one request is one transaction: Frappe commits on success and rolls back on error."

**Divergence:**
- graphql-core catches resolver exceptions and returns 200 with `errors[]`. To Frappe the whitelisted method succeeded, so it **commits**.
- With `mutation { a: updateSalesOrder(...) b: updateSalesOrder(...) }`, if `b` fails validation, `a` is committed and reported as successful. If `api.py` instead rolls back whenever `errors[]` is non-empty, any `MASKED` error in the mutation's re-read (AD-9 requires a masked re-read) rolls back a successful write while `data` still reports success.
- `writes.py` might use savepoints for per-field atomicity. That is a third policy.

**Proposed AD-19: Transaction ownership.**
> `api.py` alone owns the transaction. Writes run before the response is built. If any mutation root field raised (error codes `VALIDATION`, `FORBIDDEN`, `NOT_FOUND`, `INTERNAL`), `api.py` calls `frappe.db.rollback()` and nulls **every** mutation root field in `data`, with a `ROLLED_BACK` note in each error's extensions. Data-time read errors (`MASKED`, and `FORBIDDEN` on a re-read Link) never trigger rollback. `writes.py` never commits, rolls back or uses savepoints. Queries run with `frappe.db` in read-only mode where v16 supports it.

---

## H-14: Scan budget owner and scope [High]

**Units:** the root-connection candidate loop vs the Link and child batch loaders. Also two root connection fields in one request.

**Divergence:**
- The glossary says the budget is per **request**. Implementer A gives each connection field the full 2,000. Implementer B shares 2,000 across the request, in which order? Field order? Execution order?
- AD-4 says "the scan budget counts candidates". Link-target candidates (each needs `has_permission`) are candidates too. If they count, a page of 100 orders with 100 customers can trip `scanLimitReached` on the **root** connection, whose cursor then does not reflect where scanning stopped.
- Child tables are plain lists with no limit at all, so the budget is unbounded on that axis.

**Proposed amendment to AD-8/AD-10 (budget scope):**
> The scan budget applies per connection field occurrence (per plan node), not per request, and counts only that connection's root candidates. Link and child loads are not budgeted. They are bounded by the parent page size times the per-parent fan-out, and they count toward the AD-10 cost limit instead. A separate per-request ceiling, `max_total_candidates`, caps the sum across connections. Reaching it marks every unfinished connection `scanLimitReached: true`, and each one's cursor is computed under H-6 semantics.

---

## H-15: Cost is computed twice, before and after planning [Medium]

**Units:** `execution/rules.py` (graphql-core validation rule; AD-10: "limits run **before planning**") vs `execution/planner.py` (AD-10: "rows × fields, summed **over the plan**").

**Divergence:**
- The cost formula needs the plan (rows per node), but the rule runs before the plan exists.
- The rule author estimates from the AST, using `first` (maybe a variable that is not yet bound during validation) and a guessed child count. The planner author computes from the plan. Their numbers differ, so a query passes one check and fails the other, with different `COST_LIMIT` messages.
- Child tables have no `first`, so their row estimate is arbitrary.

**Proposed amendment to AD-10:**
> Depth is enforced as a graphql-core validation rule. Cost is enforced once, by the planner, after variables are bound and before any adapter call, using one function `estimate_cost(plan)` in `rules.py`. Rows per node are `first` (or max page size if absent) for connections, `child_fanout_estimate` (a Settings value, default 50) for child tables, and 1 for Links. A request whose cost depends on unbound variables is costed at max page size.

---

## H-16: Name collisions and Link variants [High]

**Units:** `schema/naming.py` vs `schema/builder.py`.

**Divergence:**
- The convention fails the build on **type** name collisions only. Field collisions slip through: a Link `customer` produces a synthetic `customerDoc`, which clashes with a real field `customer_doc`. Likewise `credit_limit` and a custom `creditlimit`/`credit__limit` both map to `creditLimit`. `naming.py` dedupes with a suffix and `builder.py` assumes the names are unique. Or the reverse.
- A Link whose target is **not exposed**: naming emits `xDoc: <Type>` by convention. The builder must either omit it, or include the target type and expose a non-exposed DocType (violating FR-1).
- Dynamic Link (target DocType chosen by another field) and Table MultiSelect have no convention, so each implementer invents one.
- The mutation names `createX`, `updateX` and `deleteX` can collide with a DocType whose name starts with "Create".

**Proposed amendment to the naming convention:**
> `naming.py` is the only producer of GraphQL names and raises on **any** collision within a type (field, synthetic `xDoc`) or in the root type. No silent suffixing. `xDoc` is emitted only if the Link target is exposed. Dynamic Link `x` is emitted as `x: String` plus `xDoctype: String`, with no resolved field in v1. Table MultiSelect is treated as a child table. `naming.py` also provides the reverse map (GraphQL name to fieldname), which the planner and writes use exclusively.

---

## H-17: Existence oracle in FORBIDDEN vs NOT_FOUND [Medium]

**Units:** the Link loader (AD-7: unreadable target becomes `FORBIDDEN`) vs the root `salesOrder(name:)` resolver (convention: `NOT_FOUND`).

**Divergence:**
- `_authorized_query` returns no row both for a missing document and for an unauthorized one. To return the right code, an implementer adds `frappe.db.exists(...)`, which the adapter may legally call under AD-1. It bypasses permissions and turns the code into an oracle for which names exist.
- The other implementer returns `NOT_FOUND` for both. The behaviours diverge.

**Proposed AD-20: No existence disclosure.**
> When a document cannot be read through `_authorized_query` and AD-4, the adapter reports `NOT_FOUND` whether or not it exists. Link fields additionally return their raw key in `x` (if readable), so `xDoc: null` with `NOT_FOUND` reveals nothing new. `FORBIDDEN` is reserved for operations where the target's existence is already known to the caller (a write to a document they can read, or a filter on an unreadable field). `frappe.db.exists` and unpermissioned lookups are banned in the read path by the boundary test.

---

## H-18: Mutation result assembly [Medium]

**Units:** `adapter/writes.py` vs the read planner and adapter.

**Divergence:**
- AD-9 requires re-reading through AD-2 and AD-5. Writer A re-reads only the scalar fields inside `writes.py` and returns a row. The mutation selection `{ customerDoc { name } items { rate } }` then has no loader.
- Writer B returns the saved `Document`, and execution re-plans. Two units both "own" the result shape, and B passes an in-memory Document (unmasked values) across the port.

**Proposed amendment to AD-9:**
> A write method returns only the affected `name` (or names). Execution then runs the mutation's selection set as an ordinary read plan rooted at that name, through the same planner, adapter, masking and AD-13 rules. No `Document` object or raw value ever crosses the port from a write.

---

## H-19: Implicit default order is not bound into the cursor [Medium]

**Units:** the planner (passes `order_by=None` when the client omits `orderBy`) vs the adapter (applies the meta's `sort_field`/`sort_order`, Frappe's default) vs `cursor.py` (encodes `order`).

**Divergence:**
- The cursor records `order: null`. An admin changes the DocType's default sort (Property Setter). Old cursors still validate, but now walk a different order, so rows are skipped or duplicated.
- Another implementer defaults to `modified desc`, a third to `name asc`.

**Proposed amendment to AD-8:**
> The planner never sends an empty order. A missing `orderBy` resolves to `(name ASC)` (stable and immutable), or to the meta default resolved explicitly by the adapter, before the query runs. The resolved order, never `null`, is encoded in the cursor. A cursor whose resolved order differs from the current resolution returns `BAD_CURSOR`.

---

## H-20: Depth limit vs introspection [Medium]

**Units:** `execution/rules.py` (depth 8) vs graphql-core introspection (FR-12, AD-12: introspection available).

**Divergence:**
- The standard introspection query nests `ofType` about 7 to 9 levels below `__schema`. A depth rule that counts introspection fields rejects GraphiQL and every MCP tool builder's introspection call with `DEPTH_LIMIT`.
- A rule that skips `__`-prefixed fields lets attackers build deep `__type` queries.

**Proposed amendment to AD-10:**
> Depth and cost rules ignore fields under `__schema` and `__type`. Introspection has its own fixed depth cap of 15, and introspection responses are cached per `schema_revision`.

---

## H-21: Who attaches resolvers [Medium]

**Units:** `schema/builder.py` vs `execution/executor.py`.

**Divergence:**
- The builder creates `GraphQLField`s and needs resolvers that read the result graph and raise the stored sentinel errors. Those resolvers live in `execution/`, but dependencies point `execution → schema`.
- Builder A imports execution resolvers, creating an import cycle and violating the arrows. Builder B uses default resolvers, so graphql-core's default `dict.get(field_name)` reads by field name (see H-9) and returns the sentinel object raw.

**Proposed amendment to the paradigm:**
> `schema/` builds a resolver-free schema. `execution/executor.py` supplies one `field_resolver` to `graphql.execute(...)` that reads `info.path.key` from the parent dict and converts `MASKED`, `FORBIDDEN` and `NOT_FOUND` sentinels into `GraphQLError`s with codes. Scalars (`scalars.py`) never see sentinels.

---

## H-22: Page size over the maximum [Low]

**Units:** the schema (`first: Int` with or without a default) vs the planner vs the adapter `limit`.

**Divergence:** one unit clamps `first: 500` to 100 silently, while another rejects it with `VALIDATION`. The client cannot tell which happened, and cost estimates differ (H-15).

**Proposed convention:**
> `first` defaults to 20 and must be between 1 and `max_page_size`. Out-of-range values are rejected with `VALIDATION`, and the message states the limit. Values are never clamped silently.

---

## H-23: Child row order in batched loads [Low]

**Units:** the child batch loader vs graph assembly.

**Divergence:** a batched child query across many parents returns rows in whatever order `_authorized_query` picks. One assembler groups by `parent` and keeps the arrival order. Another sorts by `idx`. Item order then differs between implementations, and clients render lines out of order.

**Proposed convention:**
> Child loads use `order_by = (parent ASC, idx ASC)`. The assembler groups by `parent` and preserves `idx` order. Child lists are always returned in `idx` order.

---

## Cross-cutting observation

Almost every hole comes from the spine fixing **who may call what** (AD-1, AD-2) without fixing **the types that cross the port**. Adopting AD-15 (shared kernel), AD-17 (filter IR) and the plan-identity amendment to AD-3 closes or simplifies H-4, H-8, H-9, H-18 and H-21 at once. The three critical holes (H-1, H-2, H-3) are each closed by one rule, and each needs a negative test added to NFR-4's suite before the first vertical slice ships.
