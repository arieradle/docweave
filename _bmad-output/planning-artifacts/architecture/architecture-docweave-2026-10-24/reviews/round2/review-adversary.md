---
type: architecture-review
round: 2
lens: adversarial (compliant-but-incompatible unit pairs)
target: ../../ARCHITECTURE-SPINE.md
prior: ../review-adversary.md
prd: ../../../../prds/prd-docweave-2026-10-24/prd.md
reviewer: BMAD adversarial architecture reviewer
date: 2026-10-24
verdict: NOT READY YET, but close. The rewrite closes all three round-1 criticals that are still in v1 scope, and most of the highs. It now names the shared kernel but does not pin its shapes. Two compliant teams can still ship a masking leak through the Dynamic Link `xDoctype` field (N-1), build execution and adapter against incompatible ports (N-2), produce cursors that are always `BAD_CURSOR` or that skip rows under multi-key ordering (N-3), and blank out a whole response when one connection fails (N-5).
---

# Adversarial Review, Round 2: DocWeave Architecture Spine

## Method

This round has the same method as round 1. For each hole I name two units one level below the spine. Each unit is built by a careful, separate implementer who obeys every v1-binding AD (AD-1 to AD-8, AD-10 to AD-12, AD-14, AD-15) and the Consistency Conventions to the letter. The hole is the way their outputs still fail to fit. Every hole ends with proposed AD text. The spine is not edited. AD-9 and AD-13 are marked `[v2]`, so I do not attack them, and write-only round-1 holes are skipped.

Severity scale (unchanged):
- **Critical:** a permission or masking leak, or silent data corruption, is possible.
- **High:** wrong results (skipped or duplicated rows, wrong nulls), or a v1 FR cannot be met.
- **Medium:** integration breakage that tests would catch, but only after rework.
- **Low:** friction or inconsistency.

---

## Part 1: Status of round-1 holes

| # | Round-1 hole | Status | Where closed, and what remains |
| --- | --- | --- | --- |
| H-1 | Derived loads from hidden source fields | **Closed** | AD-6 (readable and unmasked source, keys only from masked `Row`s) and AD-7 (Table field readable at its permlevel). One residual path is new: the Dynamic Link `xDoctype` synthetic field (N-1). |
| H-2 | Cursor discloses unauthorized candidates | **Closed** | AD-8 now uses Fernet with HKDF. The source of `kid` is undefined (N-20, low). |
| H-3 | Masked values destroyed by read-modify-write | Skipped | Write-only. AD-9 and AD-13 are v2. |
| H-4 | No shared kernel | **Partial** | `core/` now owns sentinels, `ErrorCode` and the type names. But `KeysetPosition` is missing from core's list, the `DataAdapter` methods are not named, and the shapes of `Row`, `Page`, `LoadRequest`, `FilterIR` and `OrderSpec` are not pinned (N-2). |
| H-5 | Batched preload vs per-candidate `has_permission` | **Partial** | AD-4 defines a permission projection and bans per-candidate loads. The projection's contents clash with how `get_query` treats permissions, and the way the document is built is not pinned (N-4). The "constant queries per page" test contradicts chunked scanning (N-8). |
| H-6 | "Scanned" means fetched vs checked | **Partial** | AD-8 now says *scanned* means permission-checked, and `position` is the last checked row. Chunk size and the exhaustion test ("known to be exhausted") are still undefined (N-8). |
| H-7 | Keyset ordering underspecified | **Partial** | Tie-break direction, NULL placement, the `IS NULL` branch and Decimal and Datetime encoding are fixed. Still open: `orderBy` is a **list** (multi-key, mixed direction), so "the same direction" is ambiguous; who appends the tie-break; and how Datetime is decoded (N-3, N-17). |
| H-8 | No filter grammar or canonical hash | **Partial** | The grammar, `core.FilterIR`, the adapter-only translation and the canonical JSON hash are all in place. Still open: the semantics of sibling keys and multi-operator `ScalarOps`, the typed-value codec, empty `in`, time zone handling of filter values, and which function computes the hash (N-12). |
| H-9 | Plan key collapses distinct loads | **Closed** | AD-3 plan identity, batching only within one node, response-key resolver. |
| H-10 | Child DocTypes under AD-4 and as roots | **Closed** | AD-14. |
| H-11 | Per-site nullability vs per-user masking | **Closed at field level** | AD-5 makes every field except `name` nullable. Residual: the root connection is declared non-null (`SalesOrderConnection!`), which contradicts AD-5's intent and null-bubbles (N-5). |
| H-12 | Schema revision race and storage | **Partial** | Revision mechanics, LRU and lock are adopted. The fingerprint cannot do what AD-11 claims, "Frappe's metadata version" is undefined, child DocTypes are left out, and there is no policy for revision initialization, build failure or lock waits (N-9). |
| H-13 | Two owners of commit and rollback | Skipped | v2. The v1 replacement (the AD-12 read-only rollback) has its own hole (N-10). |
| H-14 | Scan budget owner and scope | **Closed** | AD-8 budget scope. Residual: the order in which `max_total_candidates` is consumed, and the cursor for a connection that never started (N-18, low). |
| H-15 | Cost computed twice | **Partial** | One `estimate_cost(plan)` after variables are bound. The formula is ambiguous: per-node or cumulative rows, which fields count, and how depth counts `edges`/`node` (N-11). |
| H-16 | Name collisions and Link variants | **Partial** | Fail-on-collision, the reverse map, `xDoc` only for exposed targets, Dynamic Link and Table MultiSelect are all settled. The name-mangling algorithm itself is unspecified (N-16), and `xDoctype` creates a leak (N-1). |
| H-17 | FORBIDDEN vs NOT_FOUND oracle | **Closed** | AD-15, plus `frappe.db.exists` banned in AD-1. |
| H-18 | Mutation result assembly | Skipped | v2. |
| H-19 | Implicit default order not in cursor | **Closed** | `creation DESC, name DESC`, always encoded. This depends on `creation` being a schema-visible, orderable field, which is not stated (N-6). |
| H-20 | Depth limit vs introspection | **Closed** | `__schema` and `__type` are exempt. Low residual: exempt subtrees have no cap of their own. |
| H-21 | Who attaches resolvers | **Closed** | The generic resolver lives in `core`. |
| H-22 | Page size clamp vs reject | **Closed** | Reject with `VALIDATION`. Residual: the default `first` when the argument is absent is not stated (AD-10 costs it at the maximum page size, but nothing says that is also the page size used) (N-11). |
| H-23 | Child row order | **Closed** | `idx ASC` within each parent. |

Tally of the 20 in-scope holes: 10 closed, 10 partial, 0 open.

---

## Part 2: New holes in the rewritten text

### Summary

| # | Units in conflict | Clash | Severity |
| --- | --- | --- | --- |
| N-1 | `naming.py`/`builder.py` (Dynamic Link `xDoctype`) vs adapter masking (AD-5/AD-6) | Synthetic field bypasses masking of the real options field | **Critical** |
| N-2 | `execution/planner.py` vs `adapter/frappe_v16.py` via `core/port.py` | Port methods and kernel type shapes unpinned; `KeysetPosition` has no owner | **High** |
| N-3 | Planner's `OrderSpec` vs `cursor.py` order check vs keyset builder | Multi-key mixed-direction `orderBy`; who appends the tie-break | **High** |
| N-4 | AD-4 permission projection vs AD-2 `get_query` permission behaviour vs AD-15 | Projection asks for fields `get_query` rejects or cannot select; mask-placeholder fidelity; how the doc is built | **High** |
| N-5 | Root field convention (`Connection!`) vs AD-5/AD-15 error paths | One failing connection nulls the whole `data` | **High** |
| N-6 | `fieldtypes.py`/`builder.py` vs AD-8 default order vs AD-6 | Standard fields (`creation`, `owner`, `docstatus`...) not in the schema contract | **High** |
| N-7 | AD-1 allowlist vs `schema/`, `execution/`, `api.py`, Settings controller | No allowed way to read DocWeave Settings or the site time zone outside `adapter/` | **High** |
| N-8 | AD-4 query-count test vs AD-8 chunked scanning vs third-party hooks | "Constant queries per page" is not achievable as written; chunk size and exhaustion undefined | Medium |
| N-9 | `schema/cache.py` fingerprint vs Frappe's meta cache | Fingerprint cannot catch hook-less changes; init race; build-failure policy | Medium |
| N-10 | AD-12 read-only rollback vs AD-15 `frappe.log_error` | Rollback erases the Error Log row; "even from a hook" is overstated | Medium |
| N-11 | `estimate_cost` vs documented limits vs depth rule | Per-node or cumulative rows; which fields count; how `edges`/`node` count toward depth | Medium |
| N-12 | `FilterIR` producer (planner) vs consumers (adapter, `filter_hash`) | Filter semantics and canonical value codec unpinned | Medium |
| N-13 | Link batch loader vs graph assembly | Case-insensitive collation and empty Link values make false `NOT_FOUND`s | Medium |
| N-14 | Per-edge `cursor` vs `endCursor` (AD-8 position) | Clients that page from the last edge re-scan and can stall | Medium |
| N-15 | Child loader vs AD-10 cost | Child loads have no runtime bound | Medium |
| N-16 | `naming.py` algorithm vs `builder.py` vs operators | camelCase, PascalCase and pluralization rules unspecified; one collision takes the API down | Medium |
| N-17 | Scalars and the cursor codec vs MariaDB naive values | Datetime decode, `Time` as timedelta, gaps in the fieldtype map | Medium |
| N-18 | `max_total_candidates` across connections | Consumption order and start-position cursor | Low |
| N-19 | AD-12 HTTP status vs GraphQL-over-HTTP vs Frappe pre-method errors | 400 vs 200 for parse and validation errors; Frappe envelope still appears | Low |
| N-20 | `cursor.py` key ids | `kid` source undefined | Low |
| N-21 | Schema descriptions vs "never per user"; `sdl` gate vs open introspection | Translated labels; inconsistent gating | Low |
| N-22 | `scanLimitReached` vs AD-15 | Residual counting oracle for hook-rejected documents | Low |
| N-23 | Spine vs PRD | Budget glossary "per request"; FR-2 enable/disable flag missing from the gate | Low |

---

### N-1: Dynamic Link `xDoctype` leaks a masked or unreadable options field [Critical]

**Units:** `schema/naming.py` and `builder.py` (Link variants convention: "Dynamic Link `x` becomes `x: String` plus `xDoctype: String`") vs the adapter's masking and permlevel logic (AD-5, AD-6).

**Divergence:**
- A Dynamic Link field such as `party` takes its target DocType from another real field, its `options` field (here `party_type`). That field is already in the schema as `partyType`.
- The convention adds a synthetic `partyDoctype`. Nothing says which field's readability and masking govern it. AD-5 and AD-6 only talk about real fields, and AD-7 says the raw value "follows the source field's readability", meaning `party`.
- Implementer A fills `partyDoctype` from the `party_type` column inside the adapter and gates it on `party`'s readability, because that is the "source field". If `party_type` is masked or sits at a higher permlevel while `party` is readable, the masked value is returned in the clear. Every AD is obeyed, and it is a masking leak.
- Implementer B gates it on `party_type`. Both implementations comply. Also, `partyDoctype` is a second name for `partyType`, and the naming convention's "any collision fails the build" does not catch duplicates by meaning.
- AD-6's FilterIR check also says nothing about whether `partyDoctype` is filterable.

**Proposed amendment to the Link variants convention:**
> A Dynamic Link `x` is emitted as `x: String` only. Its target DocType is exposed through the options field's own GraphQL name (e.g. `partyType`), which follows that field's readability and masking under AD-5. No synthetic `xDoctype` field exists. If the options field is not otherwise exposable, the Dynamic Link field is excluded. A negative test masks `party_type` while `party` is readable and asserts that no field returns the masked value.

---

### N-2: The port and the shared kernel are named but not shaped [High]

**Units:** `execution/planner.py` and `graph.py` (the producer of `LoadRequest`s and consumer of `Row`/`Page`) vs `adapter/frappe_v16.py` (the implementer of `DataAdapter`). Each is built by a different team against `core/types.py` and `core/port.py`.

**Divergence:**
- **Port methods.** The spine names a `DataAdapter` protocol but no methods. Team E writes `adapter.load(req: LoadRequest) -> Page` for everything. Team A writes `get_one`, `list_connection`, `load_links` and `load_children`, with different return types for links and children (no paging). Both are "the DataAdapter protocol".
- **`KeysetPosition` has no owner.** AD-2's signature uses `KeysetPosition`, but core's list of owned types and `core/types.py` in the seed omit it. Team E puts the opaque cursor **string** in `LoadRequest.after`, leaving decryption to the adapter. Team A expects `LoadRequest.after: KeysetPosition`, so execution would have to call `cursor.py`, which it may not import. So who verifies `user`, `filter_hash` and `order`, and who mints `endCursor`?
- **`Row` keys.** Keyed by Frappe fieldname or by GraphQL name? AD-6 says "Rows where the source is hidden get `xDoc` ... set to the same sentinel". `xDoc` is a GraphQL name, so team A puts a synthetic `customerDoc` key into the `Row`, while team E checks `row["customer"] is MASKED` in assembly. Is `name` always present, and do child rows carry `parent` and `idx`? None of this is stated. Round 1's proposal (fieldname keys, `name` always present, child rows with `parent`, `parentfield`, `idx`) was not adopted.
- **`Page`.** Does it carry rows only, or rows plus per-row cursors (needed for `edges.cursor`, see N-14), `end_cursor`, `has_next_page` and `scan_limit_reached`? Are cursors encrypted strings or positions?
- **`FilterIR` and `OrderSpec` shapes.** Node classes, operator enum names (`nin`/`not_in`, `isNull`/`is_null`), the value representation (Python `Decimal` and `datetime`, or strings), and whether `OrderSpec` includes the tie-break (N-3).

**Proposed AD-16: Port contract.**
> `core/types.py` defines, as frozen dataclasses: `FilterIR = And(children) | Or(children) | Cmp(fieldname, op: FilterOp, value)` with `FilterOp` an enum of `EQ NE IN NIN LT LTE GT GTE LIKE IS_NULL`, values as Python-native typed values (`Decimal`, `datetime.date`, naive site-time-zone `datetime`, `str`, `int`, `bool`, tuples for `IN`/`NIN`); `OrderSpec = tuple[OrderKey(fieldname, direction), ...]` as given by the client, **without** the tie-break; `LoadRequest(kind: ROOT_ONE | ROOT_CONNECTION | LINK | CHILDREN, doctype, fields: frozenset[fieldname], filter, order, first, after: str | None, keys: tuple[str, ...], parent_doctype, parentfield)`; `Row` = a mapping from **Frappe fieldname** to value-or-sentinel that always contains `name`, plus `parent`, `parentfield` and `idx` for child rows, and never contains GraphQL names; `Page(rows, edge_cursors, end_cursor, has_next_page, scan_limit_reached)`. `KeysetPosition` is private to `adapter/cursor.py`. Cursors cross the port only as opaque strings, and only the adapter encrypts, decrypts or validates them. `core/port.py` defines exactly one method, `DataAdapter.load(requests: Sequence[LoadRequest]) -> Sequence[Page | list[Row]]`, with results aligned to requests. Derived-field sentinels (`xDoc`, child list) are set by `execution/graph.py` from the source field's value in the `Row`.

---

### N-3: Multi-key `orderBy` and tie-break ownership break the keyset [High]

**Units:** the planner (builds `OrderSpec` from `orderBy: [SalesOrderOrder!]` and resolves the default "before planning") vs `adapter/cursor.py` (encodes `order` and compares it on the next page) vs the keyset predicate builder.

**Divergence:**
- **List order.** The root-field convention makes `orderBy` a list, so `[{status: ASC}, {grandTotal: DESC}]` is legal. AD-8 says "OrderSpec plus a `name` tie-break in the **same direction**". The same direction as what? Team A uses the first key (ASC), team B the last (DESC). The keyset predicate for mixed directions must be expanded lexicographically. A row-value tuple, `(a, b, name) > (...)`, is wrong as soon as directions differ. AD-8 does not require the expanded form (round 1's H-7 proposal did), so a tuple implementation complies and skips rows.
- **NULL branches across several keys.** "The predicate includes an explicit `IS NULL` branch". One branch, or one per nullable key at each lexicographic level? With two nullable keys, a single branch is wrong.
- **Who appends the tie-break.** The planner resolves the default to `creation DESC, name DESC`, which already includes `name`. For a client order, AD-8 doesn't say whether the planner or the adapter appends `name`. If the planner appends it, `OrderSpec` arrives as `[grandTotal DESC, name DESC]`. If the adapter appends it, it arrives as `[grandTotal DESC]`. `cursor.py` encodes whatever it was given. If request 1 was encoded post-append and request 2 is compared pre-append (or the client's `orderBy` itself names `name`), every second page returns `BAD_CURSOR`.
- **Duplicates.** `orderBy: [{grandTotal: ASC}, {grandTotal: DESC}]` is unspecified: reject it or keep the first?

**Proposed amendment to AD-8 (keyset):**
> `OrderSpec` is exactly the client's keys (or the default `creation DESC`), with duplicates rejected (`VALIDATION`), and `name` allowed only as the last key. The adapter alone appends `name` with the direction of the **last** key, unless `name` is already last. The cursor encodes and compares the **effective** order (after the append). The predicate is the lexicographic expansion `k1 ⊳ v1 OR (k1 = v1 AND (k2 ⊳ v2 OR (k2 = v2 AND ... name ⊳ n)))`, with `⊳` chosen per key direction, and each nullable key expanded into its own `IS NULL` / `IS NOT NULL` branch at its level. Row-value tuple comparison is banned. All key comparisons happen in SQL, never in Python. Tests cover mixed directions, two nullable keys, and ties across a page boundary.

---

### N-4: The permission projection conflicts with `get_query`'s own permission handling [High]

**Units:** the AD-4 candidate query (projection: "`name`, `owner`, `docstatus` and every non-table field") vs AD-2 (`get_query(..., ignore_permissions=False)`, "so that Frappe's masking applies") vs AD-15 (`PermissionError` becomes `NOT_FOUND` on reads).

**Divergence:**
- **Fields the user cannot read.** "Every non-table field" includes fields at permlevels the user lacks. With `ignore_permissions=False`, Frappe either drops non-permitted fields silently or raises. The spine pins neither behaviour. If it raises `PermissionError`, AD-15 maps the error to `NOT_FOUND`, so a user who cannot read one permlevel-1 field gets an empty or `NOT_FOUND` connection. Team A strips unreadable fields before calling, and its hooks then see a doc without them. Team B passes them and relies on Frappe dropping them, which works on some v16 patch versions and not on others. Both comply.
- **"Non-table" is ambiguous.** Team A reads it as "every field except Table/Table MultiSelect" and selects Section Break, Column Break, Button and HTML fields, plus `is_virtual` fields. None of those are columns, so the SQL fails. Team B uses the meta's valid columns. Only B works, but A obeys the text.
- **Mask placeholders.** AD-4 says hooks "see Frappe's mask placeholders". Whether `frappe.qb.get_query(...).run()` applies masking (rather than only the `get_list`/`DatabaseQuery` path) is exactly what AD-2 asserts without pinning. If qb does not mask, team A masks the projection itself to make the AD-4 test pass, and team B passes raw values. Their `has_permission` hooks return different results for the same user and document. Beyond that, a hook that sees placeholders where desk's `has_permission` (which loads the full document) sees real values gives answers that **diverge from Frappe REST and desk**. That is a fidelity bug, not just a limitation: rows readable in desk vanish from DocWeave, or the reverse.
- **How the document is built.** "An unsaved document built from that row." Team A uses `frappe.get_doc({"doctype": dt, **row})`. Team B uses `frappe.new_doc(dt)` and then `.update(row)`, which applies defaults and sets `__islocal`. Frappe's permission code and hooks may treat local (new) documents differently (`is_new()`). Same AD, different authorization.

**Proposed amendment to AD-4:**
> The permission projection is `name`, `owner`, `docstatus`, `modified`, plus every field in `meta.get_valid_columns()` that the user can read at its permlevel. It never includes virtual or no-column fields, and never fields above the user's permlevel. The adapter computes this list itself and passes `get_query` only fields it knows are permitted, so `get_query` never raises for field permissions. The document passed to `has_permission` is `frappe.get_doc({"doctype": dt, **projection_row})`, with no `__islocal` and `is_new()` false. Masking is applied by the adapter after `has_permission`, from AD-5 metadata. Whether hooks see raw or placeholder values is decided once (recommended: raw, server-side only, never crossing the port), and a **parity test** asserts that, for a fixture user with a `has_permission` hook, DocWeave returns exactly the names that `frappe.get_list` plus `frappe.has_permission(doc=frappe.get_doc(...))` returns.

---

### N-5: A non-null root connection null-bubbles the whole response [High]

**Units:** the root-field convention (`salesOrders(...): SalesOrderConnection!`) vs AD-5 ("every output field except `name` is nullable") vs the error paths of AD-6 (`FORBIDDEN` filter), AD-8 (`BAD_CURSOR`, `VALIDATION` on `first`) and AD-15.

**Divergence:**
- AD-5's intent is that no error nulls more than its own field. But the connection field is declared `!`. When a connection fails with `FORBIDDEN` (filter on a masked field), `BAD_CURSOR` or `VALIDATION`, graphql-core propagates the null to `data`. One bad alias, `late: salesOrders(after: "stale")`, wipes `open: salesOrders(...)` and `customer(name: ...)` in the same request. That breaks FR-14's "actionable" errors and costs MCP agents their tokens.
- A user with no DocType-level read (the type is exposed but they hold no read DocPerm) is also undefined. Team A returns an empty connection (as if no candidates matched). Team B lets `get_query` raise `PermissionError`, which AD-15 maps to `NOT_FOUND`, which bubbles. Both comply.
- The nullability of `edges`, `node`, `pageInfo` and the child list (`[ChildType]` vs `[ChildType!]`) is not stated.

**Proposed amendment to AD-5 and the root-field convention:**
> All root fields are nullable: `salesOrders(...): SalesOrderConnection`, `salesOrder(name: String!): SalesOrder`. Inside a connection, `edges: [SalesOrderEdge!]!`, `node: SalesOrder!`, `pageInfo: PageInfo!` and the `PageInfo` booleans are non-null. Child lists are `[ChildType!]`, with the list itself nullable so it can carry a sentinel. A user without DocType-level read on an exposed DocType gets an **empty** connection (`hasNextPage: false`), and `null` plus `NOT_FOUND` for a single get, never an error that bubbles past the field. A test runs two aliased connections, one of them invalid, and asserts that the other still returns data.

---

### N-6: Standard fields are outside the schema contract [High]

**Units:** `schema/fieldtypes.py` and `builder.py` (the fieldtype map iterates `meta.fields`) vs AD-8 (the default order is `creation DESC, name DESC`) vs AD-6 (rejects filter and sort fields that are unreadable or masked).

**Divergence:**
- `meta.fields` does not contain the standard columns `name`, `owner`, `creation`, `modified`, `modified_by`, `docstatus`, `idx` or `_assign`/`_user_tags`/`_comments`/`_liked_by`. Builder A emits only `meta.fields` plus `name`. Clients then cannot select or filter `creation`, `docstatus` or `owner`, and `SalesOrderOrder` has no `creation` key, even though AD-8 orders by it implicitly. The cursor, though, encodes the `creation` value. Builder B adds all standard fields, including `_`-prefixed ones whose camelCase names are invalid or clash (`_assign` becomes `_assign` or `assign`).
- AD-6's readability check consults the user's permitted fields. Standard fields have no DocField, so team A's checker treats `creation` as unknown and rejects it with `FORBIDDEN` (now the default order fails AD-6), while team B treats unknown fields as permlevel 0.
- The fieldtype map assigns no types to standard fields. `docstatus` could be `Int` or an enum, and `owner` could be `String` or a Link to User.

**Proposed convention: Standard fields.**
> Every exposed type includes `name: String!`, `owner: String`, `creation: Datetime`, `modified: Datetime`, `modifiedBy: String`, `docstatus: Int`, and, for child types, `idx: Int`. They are treated as permlevel 0, never masked, and filterable and orderable. `_`-prefixed columns, `parent`, `parenttype` and `parentfield` are never exposed. `owner` and `modifiedBy` get no `Doc` variant in v1. The fieldtype map and the AD-6 checker share one `standard_fields` table in `schema/fieldtypes.py`, which the adapter mirrors by fieldname.

---

### N-7: The allowlist leaves no legal way to read Settings or the time zone [High]

**Units:** AD-1's allowlist (outside `adapter/`: `get_meta`, `cache`, `session.user`, `get_roles` and so on, with `get_cached_doc` banned everywhere) vs `schema/builder.py` (AD-11: built "from Settings plus meta"), `execution/rules.py` (AD-10: "limits come from DocWeave Settings"), `api.py` (AD-12: `allowed_roles`, `allow_administrator`), `schema/scalars.py` (Datetime needs the site time zone), and the Settings controller (validation needs `frappe.throw`).

**Divergence:**
- `frappe.get_single`, `frappe.db.get_single_value` and `frappe.utils.*` are not on the allowlist, and `frappe.get_cached_doc` is banned outright. No layer outside `adapter/` can read Settings or the system time zone.
- Team S adds `frappe.get_single` to the allowlist ad hoc. Team X routes Settings through the adapter, but execution may not import the adapter, so the transport must inject the values. In what shape? Team Y reads the Settings row with `frappe.db.get_value`, which is banned. Each team either fails `test_boundaries.py` or invents a private contract.
- The Settings controller in `docweave/docweave/doctype/` is "outside `adapter/`" and needs `frappe.throw` and `frappe.model.document.Document`. Either the boundary test excludes that folder, which nobody wrote down, or it fails.

**Proposed amendment to AD-1 and core:**
> `core/types.py` defines a frozen `SettingsSnapshot` (exposed DocTypes, limits, `allowed_roles`, `allow_administrator`, `enabled`, `site_tz`). Only `api.py` reads it, through `frappe.get_single("DocWeave Settings")` and `frappe.utils.get_system_timezone()` (both added to the allowlist **for `api.py` only**), and passes it to `schema` and `execution`, which never read Settings themselves. The boundary test exempts `docweave/docweave/doctype/**`, `hooks.py` and `patches/`, which may use any Frappe API except the global bans.

---

### N-8: "Constant queries per page" contradicts chunked scanning [Medium]

**Units:** the AD-4 query-count test ("constant number of queries per page") vs the AD-8 candidate loop ("fetches candidates in chunks" until the page is full or the budget runs out) vs ERPNext's `has_permission` hooks.

**Divergence:**
- With a run of 1,900 unauthorized rows, the loop issues about `1900 / chunk` queries for one page. The count is bounded but not constant. Team A writes a test that passes on fixtures with no unauthorized runs. Team B, testing UJ-3 (the PRD's first slice includes "pagination across long unauthorized runs"), finds the test cannot be met, and either fetches the whole budget in one query (memory blow-up, and it breaks "position = last checked") or weakens the test.
- The chunk size is unpinned. It could be `first`, `first + 1`, a fixed 50, or the remaining budget. It changes query counts, budget granularity and the exhaustion inference.
- "Known to be exhausted" is undefined. A short chunk? An extra probe query?
- Frappe's own `has_permission`, and ERPNext's hooks, may run their own queries per document (shares, User Permissions). The test is constant only for hook-free DocTypes.

**Proposed amendment to AD-4 and AD-8:**
> The chunk size is `min(max(2 × first, 50), remaining budget)`. Candidates are exhausted only when a chunk returns fewer rows than requested and every row of it has been checked. Otherwise `hasNextPage` is true, and no probe query is issued. The query-count test asserts **at most** `nodes + ceil(budget / min_chunk)` DocWeave-issued queries, independent of the number of parent rows and children. It counts only queries issued from `adapter/` (measured by wrapping `_authorized_query`), so hook-issued queries are excluded, and it runs on a fixture with a 1,900-row unauthorized run.

---

### N-9: The fingerprint cannot catch hook-less changes; cache policy gaps [Medium]

**Units:** `schema/cache.py` (key `(revision, fingerprint)`; the fingerprint hashes Settings, each exposed DocType's meta `modified` and "Frappe's metadata version") vs Frappe's meta cache vs the build lock.

**Divergence:**
- **The claim is false.** The fingerprint is computed from `frappe.get_meta`, which is itself cached. A hook-less Property Setter delete (for example via `frappe.db.delete`) clears neither the meta cache nor anything else, so the fingerprint is unchanged. Separately, a Property Setter change does not update `DocType.modified`. So the fingerprint catches only changes that were already caught.
- **"Frappe's metadata version" is undefined.** There is no documented global meta version in v16. Team A hashes `frappe.__version__`, team B hashes a `frappe.cache` key it hopes exists, and team C omits it.
- **Scope.** The text says "each exposed DocType". Child DocTypes (Sales Order Item custom fields) and the exposure of Link targets (which decides whether `xDoc` is emitted) are not included.
- **When it is computed.** Per request means O(exposed DocTypes) meta reads on every request. Per revision means it adds nothing. The two teams diverge.
- **Initialization race.** "Initialized to a random 64-bit value" with a plain `SET`: two workers initialize at once and one overwrites the other's value. `INCR` on a missing key yields 1, which can collide with an earlier lifetime.
- **Failure and waiting.** A build that fails (a name collision after a user adds a Custom Field, N-16) has no policy: serve `INTERNAL` forever, or serve the previous schema? The lock has no TTL and waiters have no timeout. The seed's `hooks.py` lists `doc_events` and `after_uninstall` but no `after_migrate`, yet Operations says `bench migrate` bumps the revision.

**Proposed amendment to AD-11:**
> The fingerprint covers Settings, plus `modified` of each exposed DocType, of each of their child DocTypes, and of every Custom Field and Property Setter row on them (one aggregate `MAX(modified)`/`COUNT(*)` query per table). It is computed once per revision per process, not per request. Hook-less deletions are **not** detected, and that is documented. Recovery is by `bench clear-cache` or `migrate`. The revision is created with `SET NX` of a random 63-bit value, and bumped with `INCR`. The build lock has a 30-second TTL. Waiters wait up to 5 seconds and then build without the lock. A failed build is logged and returns `INTERNAL` with the message "schema build failed: <reason>" to System Managers and plain `INTERNAL` to everyone else. The previous schema is never served across a revision bump, because exposure may have been withdrawn. `hooks.py` registers `after_migrate` and `after_install` to bump the revision.

---

### N-10: The read-only rollback erases error logs, and its guarantee is overstated [Medium]

**Units:** AD-12 ("the transport calls `frappe.db.rollback()` before returning, so no v1 request can persist a write, even from a hook") vs AD-15 (`INTERNAL` is "logged with `frappe.log_error`", which inserts an Error Log row in the current transaction).

**Divergence:**
- Team E logs at the point of failure (inside the adapter's mapper, which is the only exception mapper). The transport's rollback then deletes the Error Log row. `INTERNAL` errors leave no trace, which defeats the Operations observability line.
- Team T logs after the rollback and relies on Frappe's end-of-request commit. Both comply.
- "Even from a hook" is false for a hook that calls `frappe.db.commit()` itself, or that enqueues a job. The rollback cannot undo either.
- It is unspecified whether the rollback runs in a `finally` or on the success path only.

**Proposed amendment to AD-12:**
> The transport wraps execution in `try/finally`. The `finally` block calls `frappe.db.rollback()`, **then** flushes deferred `INTERNAL` log entries (collected by `adapter/errors.py`, never written inline) with `frappe.log_error`, then lets Frappe's request commit persist only those. The guarantee is restated as "DocWeave issues no writes, and discards uncommitted writes made by hooks". Hooks that commit explicitly are out of scope and documented. A test asserts that an `INTERNAL` error leaves exactly one Error Log row and no other row changes.

---

### N-11: The cost formula and depth counting are ambiguous [Medium]

**Units:** `execution/rules.py` `estimate_cost(plan)` vs the Settings defaults (`child_fanout_estimate` 50, maximum page 100) vs the depth rule vs client-side cost estimates (FR-12 and FR-13 MCP builders).

**Divergence:**
- "Cost is the sum of rows × selected fields" with "rows per node: `child_fanout_estimate` for child tables". Implementer A uses node-local rows, so `items` costs 50 × fields. Implementer B multiplies down the path, so `items` under `salesOrders(first: 100)` costs 100 × 50 × fields. That is a factor of 100. Under B, a default `COST_LIMIT` that suits A rejects nearly every nested query.
- Do the synthetic fields `edges`, `node`, `cursor`, `pageInfo` and `__typename`, and object fields such as `customerDoc`, count as "selected fields"?
- Depth: does `salesOrders { edges { node { customerDoc { name } } } }` have depth 5 or 2 relationship hops? With depth 8 counting every selection level, the connection wrapper uses 3 levels per hop, so only about two hops fit. Counting only DocType hops allows eight.
- The default `first` is unstated (H-22 residual). AD-10 costs an absent `first` at the maximum page size, but the adapter may use another default.

**Proposed amendment to AD-10:**
> `rows(node)` = `rows(parent) × local(node)`, with `local` = `first` (default `max_page_size`, which is also the page size used) for connections, `child_fanout_estimate` for child tables, 1 for Links, and `rows(root single get)` = 1. `cost = Σ rows(node) × |scalar leaf fields selected on node|`. Synthetic connection fields and `__typename` cost 0. Depth counts **object-typed field levels only**, and `edges` and `node` do not count. The formula is published in the SDL description of the `Query` type so agents can compute it.

---

### N-12: `FilterIR` semantics and canonical values are unpinned [Medium]

**Units:** the planner (GraphQL filter input to `FilterIR`) vs the adapter (`FilterIR` to qb criteria) vs the `filter_hash` producer (cursor issue time vs cursor check time).

**Divergence:**
- **Semantics.** `{status: {eq: "Open"}, or: [...]}`: are sibling keys implicitly ANDed with the `or`? `{grandTotal: {gt: 1, lt: 5}}`: AND of the operators? `isNull: false` means IS NOT NULL? An empty `and: []`: match all or none? Two planner authors pick differently, and the adapter faithfully translates whatever arrives.
- **Empty `in`.** `{status: {in: []}}`. If the adapter passes it to `get_query` as a Frappe-format filter, some Frappe paths drop an empty `IN`, which **returns every row**. That is a filter widened silently.
- **Typed-value codec.** "Typed values" in the canonical JSON. Is `Decimal("100")` the same as `Decimal("100.00")`? Is a client Datetime with `Z` normalized to naive site time before hashing? Are `in` lists sorted and deduplicated? If the hash is computed by two functions (planner at issue time, adapter at check time), or the input arrives as a variable on one page and a literal on the next, a valid cursor fails with `BAD_CURSOR`.
- **`like`.** Are `%` and `_` client wildcards or literals? Is `like` allowed on non-String scalars?
- **Which fields** are filterable: Text Editor, JSON, `Link`, `Check`?

**Proposed amendment to the Filter input convention:**
> Sibling keys in one `<Type>Filter` object, and several operators in one `ScalarOps`, are ANDed. Empty `and` matches all. Empty `or` matches none. `in: []` matches none and `nin: []` matches all, both decided in the adapter before qb, and tested. `isNull: true/false` means IS NULL / IS NOT NULL. `like` is allowed on String only, with `%` and `_` as client wildcards and `\` as the escape. JSON, Text Editor, Markdown Editor, Code and Long Text are not filterable or orderable. `core.filter_hash(ir: FilterIR) -> str` is the **only** hash function. It canonicalizes Decimals with `normalize()`, Datetimes as naive site-time ISO with microseconds, sorts and deduplicates `IN`/`NIN` values, sorts `And`/`Or` children by their canonical JSON, and flattens nested same-kind nodes.

---

### N-13: Link key matching breaks under case-insensitive collation [Medium]

**Units:** the Link batch loader (adapter: `name IN keys`) vs graph assembly (execution: looks up each parent's `x` value among the returned `Row`s to set `xDoc`, or `NOT_FOUND` when absent).

**Divergence:**
- MariaDB's `utf8mb4_unicode_ci` matches `customer = "acme ltd"` to name `"ACME Ltd"`, as Frappe desk does. The adapter returns `Row(name="ACME Ltd")`. The assembler's dict lookup on `"acme ltd"` misses and emits `NOT_FOUND` for a document the user can read. Trailing spaces (`PAD SPACE` collation) behave the same way.
- Empty Link values (`""` or `NULL`). Team A sends `""` in the keys and emits `NOT_FOUND` for every row with no customer. Team B skips the key and returns `xDoc: null` with no error.

**Proposed amendment to AD-7:**
> Empty or NULL Link values yield `xDoc: null` with no error and are never sent as keys. For `LINK` requests the adapter returns each `Row` tagged with the requested key(s) it matched (`Row.__key__`, matched in SQL), and the assembler joins only on that tag, never on Python string equality of `name`.

---

### N-14: Per-edge cursors vs `endCursor` [Medium]

**Units:** `cursor.py` / `Page` (AD-8: `position` is the last **checked** candidate) vs the Relay convention (`edges { cursor node }`).

**Divergence:**
- After an unauthorized run, `endCursor` points past the last returned edge. The spine doesn't say what an edge's `cursor` is. Team A gives each edge the position of its own row. Team B gives every edge the end cursor (wrong for Relay `after: edge.cursor`).
- Clients using Apollo's `relayStylePagination`, or a "page after the last item" approach, use the last edge's cursor. With team A, they re-scan the unauthorized run on every page. If that run is longer than the scan budget, each request ends at the same place: no rows, `scanLimitReached`, and the client keeps resubmitting the last edge cursor. That is a permanent stall, the exact failure AD-8 claims to prevent.

**Proposed amendment to AD-8 (page info):**
> Each edge's `cursor` encodes that row's own position. `endCursor` encodes the last **checked** position and may lie beyond the last edge. The SDL description of `endCursor` states "always continue from `pageInfo.endCursor`". When `scanLimitReached` is true, `endCursor` must differ from the request's `after`, unless the budget was zero, so progress is guaranteed. A test pages across a run longer than the budget and asserts that it terminates.

---

### N-15: Child loads have no runtime bound [Medium]

**Units:** the child loader (`_authorized_query` with `parent IN (...)`, and a `limit` that is meaningless for children) vs AD-10 (cost uses `child_fanout_estimate`, an estimate, not a cap).

**Divergence:** a page of 100 Sales Orders whose children include one with 20,000 items passes the cost check (100 × 50) and then loads 20,000+ rows into memory. Team A passes `limit=None`. Team B passes `limit = parents × fanout` and silently truncates children, which arrive arbitrarily across parents. Neither is ruled out.

**Proposed amendment to AD-7 and AD-10:**
> Child loads are capped at `max_child_rows` per request (Settings, default 10,000). Exceeding it fails the child field with `COST_LIMIT` (the parent rows still return), and nothing is ever silently truncated.

---

### N-16: The name-mangling algorithm is unspecified [Medium]

**Units:** `schema/naming.py` (only producer of names) vs `builder.py`, the operators' expectations, and documentation and agents that predict names.

**Divergence:**
- **camelCase.** `item_code_2`, `customer__name`, `UOM`, `bom_no`: does `bom_no` become `bomNo`, `BOMNo` or `bOMNo`? Fieldnames with a leading digit (illegal in GraphQL) are not handled. **PascalCase** of DocType names with `-`, `&`, `(`, `.` or non-ASCII characters (`Item-Variant`, `Sales Taxes & Charges`) is not handled either.
- **Root names.** The root singular/plural rule (`salesOrders`, `companies`?, `addresses`?, `series`?) is unstated. A naive `+s` vs an inflection library gives different public APIs and different collisions, for example "Activity Type" and "Activity Types" both existing.
- **Synthetic types.** `<Type>Connection`, `<Type>Edge`, `<Type>Filter`, `<Type>Order` and the `StringOps`/`IntOps` types can collide with a real DocType such as "Sales Order Filter". "Any collision fails the build" is good. But combined with N-9's missing build-failure policy, one user-added Custom Field takes the whole API down site-wide.

**Proposed amendment to the Names convention:**
> The algorithm: split on `[^A-Za-z0-9]+` and on `_`, drop empty parts, lowercase every part, capitalize the first letter of each part (all parts for PascalCase, all but the first for camelCase), and prefix `_` + `N` if the result starts with a digit (`_N2fa`). The plural is the singular plus `List` (`salesOrderList`), which avoids an inflection dependency and plural collisions. Synthetic type suffixes are reserved, and Settings validation rejects exposing a DocType whose PascalCase name ends in a reserved suffix. A field-level collision on a non-exposed-by-default custom field **drops that field** with a logged warning and a Settings validation message. A collision among exposed DocType or root names fails Settings validation **before save**, so a failing schema can never be committed.

---

### N-17: Scalar and codec gaps [Medium]

**Units:** `schema/scalars.py` and the fieldtype map vs `adapter/cursor.py` (the typed codec) vs MariaDB's returned types.

**Divergence:**
- **Datetime decode.** "ISO 8601 with offset" on output and in the cursor. On decode, team A converts to site time and drops the offset, while team B converts to naive UTC and compares against naive site-time columns, so the boundary row is missed. Datetime values in filters raise the same question.
- **`Time`.** Frappe returns a `timedelta` for `Time` columns. The scalar's serialization (`HH:MM:SS[.ffffff]`) and its cursor encoding are unstated.
- **Missing fieldtypes.** `HTML Editor` is in v16 but missing from both the map and the exclusions. The policy for an unknown or unmapped fieldtype (skip, fail the build, or `String`) is not stated, and future v16 fieldtypes need one. `Rating` is stored as a 0–1 float, so mapping it to `String` is lossy. `Percent` and `Currency` are stored differently but both map to `Decimal`, without a stated serialization precision.

**Proposed amendment to the Scalars and Fieldtype map conventions:**
> All Datetimes, in cursors, filters and output, are converted to the site time zone and then made naive before reaching SQL. The offset is informational only. `Time` is serialized as `HH:MM:SS[.ffffff]` from the `timedelta`. `HTML Editor` maps to `String`. `Rating` maps to `Float`. Any fieldtype not in the map is **excluded**, logged once per build, and listed in `docweave.api.sdl` output comments. `Decimal` is serialized with `str(value.normalize())`.

---

### N-18: Consuming `max_total_candidates` [Low]

**Units:** the per-connection budget vs the per-request cap (AD-8).

**Divergence:** with three root connections and a cap of 10,000, the spine doesn't say which connection is starved: execution order, document order, or a proportional split. A connection that starts after the cap is exhausted has no `position`, and its cursor content is unspecified.

**Proposed text:**
> Connections consume the per-request cap in document order of their plan nodes. A connection that starts with zero remaining budget returns no edges, `scanLimitReached: true`, `hasNextPage: true`, and an `endCursor` equal to the request's `after` (or a start-position cursor if `after` was absent).

---

### N-19: HTTP status and the Frappe envelope [Low]

**Units:** AD-12 ("200 for GraphQL results with errors, 400 for malformed requests") vs GraphQL-over-HTTP vs Frappe's pre-method handling.

**Divergence:**
- Is a parse error or a `DEPTH_LIMIT` validation error "malformed" (400) or a GraphQL result with errors (200)? The spec distinguishes by response media type, and two implementers will split.
- Unauthenticated, guest and CSRF failures are raised by Frappe **before** `api.graphql` runs, so they still carry Frappe's `exc` and `_server_messages` envelope, contrary to "never appears".

**Proposed text:**
> 400 only for a non-JSON body, a missing `query`, or wrong types in `variables` or `operationName`. Parse, validation, `DEPTH_LIMIT` and `COST_LIMIT` errors return 200 with `errors` and `data` absent. Authentication and CSRF failures raised by Frappe before dispatch are out of DocWeave's control and are documented as Frappe-format 401/403/400 responses.

---

### N-20: The cursor `kid` has no source [Low]

**Units:** `cursor.py` instances in two releases.

**Divergence:** the key is derived from the single site encryption key, so what changes `kid`? Team A sets `kid` to a truncated hash of the derived key. Team B uses a counter in Settings. "Current and previous kid accepted" only means something if rotation is defined. Fernet also carries its own timestamp, which makes `iat` redundant: should the TTL be checked through Fernet's `ttl=` or through `iat`?

**Proposed text:**
> `kid` = the first 8 hex characters of SHA-256 of the derived key, and rotation happens only when the site encryption key changes. The previous key is the HKDF output under `docweave-cursor-v1-prev`, configured only in Settings as an optional field. The TTL is enforced with `MultiFernet.decrypt(token, ttl=86400)`, and `iat` is dropped from the payload.

---

### N-21: Translated descriptions; inconsistent SDL gating [Low]

**Divergence:** "Descriptions come from labels and help text." Team A wraps them in `frappe._()`, which follows the request user's language, so the per-site schema becomes per-language and the cache key is wrong. Separately, `sdl` is limited to System Managers while introspection through `graphql` is open to every allowed user, so the restriction protects nothing.

**Proposed text:**
> Descriptions use untranslated source strings. `sdl` is gated exactly like `graphql`, or else introspection is gated like `sdl`. Pick one; the recommendation is to gate both by `allowed_roles`, because FR-12 requires introspection.

---

### N-22: `scanLimitReached` is a residual counting oracle [Low]

**Divergence:** candidates are already filtered by roles, User Permissions and `permission_query_conditions`. Only rows rejected by `has_permission` hooks are invisible but still scanned. With filters on readable fields, `scanLimitReached: true` on an empty page reveals that at least *budget* hook-rejected documents match, which slightly weakens AD-15's no-existence-disclosure promise.

**Proposed text:** add to AD-15:
> `scanLimitReached` may reveal that many hook-rejected documents exist in a filter range. This is accepted and documented, and the scan budget is never client-settable.

---

### N-23: Drift between the spine and the PRD [Low]

**Divergence:**
- The PRD glossary defines the scan budget as "per request", while AD-8 applies it per connection with a separate per-request cap.
- FR-2 calls for an "enable/disable" switch in Settings. AD-12's access gate never checks it, so team A returns 403 `NOT_EXPOSED` when disabled, and team B returns 404 or ignores the flag.

**Proposed text:** update the PRD glossary to match AD-8, and add to the AD-12 access gate:
> If Settings `enabled` is off, every request returns 403 `NOT_EXPOSED` before any other check.

---

## Contradictions introduced by the rewrite

1. **AD-5 vs the root-field convention:** "every output field except `name` is nullable" vs `SalesOrderConnection!` (N-5).
2. **AD-4 vs AD-8:** "constant number of queries per page" vs chunked scanning until the page fills (N-8).
3. **AD-1 vs AD-10, AD-11 and AD-12:** Settings must be read in three layers, and the allowlist permits it in none of them (N-7).
4. **AD-12 vs AD-15:** the read-only rollback erases `frappe.log_error` output (N-10).
5. **AD-11's text vs its mechanism:** the fingerprint "catches hook-less Property Setter deletes" but is computed from the cache that those deletes do not touch (N-9).
6. **AD-8 vs the fieldtype map:** the default order `creation DESC` uses a field the schema contract never declares (N-6).
7. **AD-2 vs the core list and the seed:** `KeysetPosition` appears in the chokepoint signature but has no owner in `core/` (N-2).

## Cross-cutting observation

The round-1 lesson ("the spine fixes who may call what, not what crosses the port") was half-applied. The kernel now has an owner and type **names**, but a name is not a contract: N-2, N-3, N-12 and N-14 are all one missing page of dataclass definitions. Adopting AD-16 (port contract) together with the N-3 keyset text closes or shrinks five of the seven high and critical findings. N-1 is a one-line convention deletion. N-4 needs a decision (raw vs placeholder values for hooks), backed by a parity test against `frappe.get_list` plus `has_permission`, which also protects NFR-1 against v16 patch drift.
