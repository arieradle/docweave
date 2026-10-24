---
review-of: ARCHITECTURE-SPINE.md (DocWeave, 2026-10-24, post round-1 rewrite)
reviewer: rubric (good-spine checklist), round 2
date: 2026-10-24
verdict: MINOR REVISE. Round-1 findings are largely resolved. One high-severity blocker remains in the AD-1 allowlist, plus one v1 FR coverage gap and a handful of medium ambiguities.
---

# Rubric Review, Round 2: DocWeave Architecture Spine

## Verdict

**Minor revisions, then build.** The rewrite closed every round-1 HIGH: the cursor is encrypted, there is a permission projection with no per-candidate loads, a fieldtype map, a permlevel rule, an introspection exemption, a keyset slot in AD-2 and an Operations section. Marking AD-9 and AD-13 as v2 is clean, and v1 now follows a coherent read-only story.

Two problems still block a clean build:

1. The AD-1 allowlist cannot express how `schema/` and `api.py` legally read DocWeave Settings (or `message_log`, or time-zone utilities). The first implementer will either break the boundary test or widen the allowlist ad hoc, which is exactly the divergence AD-1 exists to prevent.
2. FR-3's enable/disable switch and FR-2's admin-only Settings permission still have no home in any AD or convention.

The remaining findings are medium or low ambiguities, a few stale v2 references, and some rules that can be cut for a solo hobby v1.

## Checklist summary

| Criterion | Result |
| --- | --- |
| Fixes the real divergence points, misses none | Mostly. New gaps: how Settings is read, the cost fan-out formula, the orderBy input shape, the HTTP status of limit and parse errors. |
| Every AD Rule is enforceable and prevents its divergence | Mostly. The AD-1 allowlist is incomplete (R2-1). The AD-4 "constant queries per page" claim contradicts AD-8 chunked scanning (R2-4). The AD-11 "Frappe's metadata version" input is vague (R2-12). |
| Nothing under Deferred lets two units diverge | Yes. Child retrieval stays behind the adapter port. The default limits are stated with numbers. |
| Covers every v1 FR/NFR | Partial. FR-3's enable flag and FR-2's admin-only role are missing (R2-2). NFR-1's "review rules" are still unaddressed (R2-15). |
| Every dimension decided, deferred or open | Yes. Deployment, environments (devcontainer, CI, user site), release, upgrade, uninstall and observability are all present. Minor: Frappe Cloud needs a private bench (unstated), and Node is unpinned. |
| Internal consistency (v1 read-only) | Mostly. The `binds` frontmatter still lists FR-11. The Tests convention demands negative tests for the v2 ADs. `hooks.py` has no `after_migrate` although Operations relies on it. `KeysetPosition` is missing from core. The AD-12 rollback may discard Error Log rows (R2-5). |

## Part 1: Round-1 findings, verification

| R1 | Topic | Status | Evidence / residual |
| --- | --- | --- | --- |
| F-1 | Cursor leaks data (signed, not encrypted) | **Resolved** | AD-8 uses Fernet AEAD with an HKDF key and purpose `docweave-cursor-v1`. The plaintext-absence test is implied by the Tests convention but not named. Optional: name it in `test_pagination.py`. |
| F-2 | Mutation partial commits | **Resolved (moved to v2)** | AD-9 makes the transport own the transaction and roll back on any error. AD-3 defines the mutation pipeline. v1 has no Mutation type, and AD-12 rolls back every v1 request. |
| F-3 | has_permission N+1 / undefined doc source | **Resolved, with residue** | AD-4 builds an unsaved doc from the permission projection and adds a query-count test. Residue: the projection over-fetches and can include permlevel-restricted columns (R2-6), and "constant per page" conflicts with chunked scanning (R2-4). |
| F-4 | No fieldtype map; Password not excluded | **Partial** | A map now exists and Password is excluded. Still missing: `HTML Editor`; a default rule for unknown or future fieldtypes; how the standard fields (`owner`, `creation`, `modified`, `modified_by`, `docstatus`, `idx`, and `parent`/`parenttype`/`parentfield` on child types) are exposed; Rating is mapped to `String` although Frappe stores it as a 0-1 float (R2-10). |
| F-5 | Selecting a permlevel field | **Resolved** | AD-5 returns `FORBIDDEN` for unreadable fields, and every field except `name` is nullable. |
| F-6 | Depth limit breaks introspection | **Resolved** | AD-10 exempts `__schema` and `__type`. Cost is computed from the plan, which contains no introspection nodes. The test is not named. Optional: add "introspection query passes under default limits" to the tests. |
| F-7 | Filter and orderBy shape, filter_hash | **Partial** | The filter shape, operators and canonical `filter_hash` are fixed. `orderBy: [SalesOrderOrder!]` is a list, but the shape of `SalesOrderOrder` (field enum plus direction?) is never defined. With several keys in mixed directions, "name tie-break in the **same direction**" is ambiguous (R2-8). |
| F-8 | Closed signature cannot express keyset | **Resolved** | AD-2 has `after: KeysetPosition | None`, and AD-8 defines NULL ordering. Residue: `KeysetPosition` is not listed among the core types (R2-13). |
| F-9 | Schema cache infeasible; triggers incomplete | **Partial** | The per-process LRU, the Redis revision, `after_commit` bumps and the extra triggers are all fixed. But Operations says "`bench migrate` bumps `schema_revision`" while AD-11's trigger list and the `hooks.py` seed comment (`doc_events + after_uninstall`) have no `after_migrate` or `after_install` hook (R2-7). |
| F-10 | Denylist boundary test | **Partial** | It is now an allowlist with aliases resolved. But the allowlist is incomplete for the code the spine itself requires (R2-1, HIGH). |
| F-11 | Exception mapping, HTTP status | **Partial** | `adapter/errors.py` mapping and 200/400/403 are fixed. Still open: is a GraphQL syntax or validation error "malformed" (400) or a GraphQL result (200)? What status do `DEPTH_LIMIT` and `COST_LIMIT` get? And who maps errors that never pass through the adapter (graphql-core validation, depth, cost), given that `adapter/errors.py` is "the only exception mapper"? (R2-9) |
| F-12 | Operations envelope thin | **Resolved** | The Operations section covers deployment, environments, release, upgrade, uninstall and observability. Minor: Frappe Cloud requires a private bench for a non-marketplace app (unstated). |
| F-13 | Floating "latest 16.x" | **Resolved** | CI is pinned to v16.53.0, a range `<17` is declared, and each release states its tested tag. MariaDB 11.8 is pinned. Redis is "what bench provisions" (acceptable). A scheduled HEAD job was not added (optional). |
| F-14 | FR-5 benchmark target | **Partial (acceptable)** | "Constant query count fixed by test" is set and latency is deferred. But "constant" is not defined against chunked rescans (R2-4). |
| F-15 | Scan budget scope | **Resolved** | Per connection occurrence, with a per-request `max_total_candidates`. Children and links do not count. |
| F-16 | Datetime / time-zone | **Partial** | Output is ISO 8601 with the site offset, and Time is mapped. How filter inputs with and without an offset are interpreted is still unstated (R2-14). |
| F-17 | Unpinned tooling | **Partial** | graphql-core `~=3.3.0` is pinned with the API note. Node (needed by bench and the devcontainer) and pre-commit are still unpinned. Low. |
| F-18 | Masking-confirmation Deferred item | **Resolved** | The item was removed. AD-2 and AD-5 now agree: qb masks, the adapter identifies masked fields from metadata and swaps in `MASKED`. |
| F-19 | FR-2 role, NFR-1 review rules, cursor lifetime | **Partial** | Cursor TTL is resolved (24 h). The FR-2 Settings role is **not** named (R2-2). NFR-1 review rules are **not** addressed (R2-15). |

Totals: 9 resolved, 10 partial, 0 not resolved. Two of the partials carry forward as higher-severity new findings (R2-1, R2-2).

## Part 2: Findings on the current spine

### R2-1 [HIGH] The AD-1 allowlist forbids things the spine itself requires
- **Location:** AD-1 allowlist; AD-11 ("built from ... Settings"); AD-12 (access gate reads `allowed_roles` and clears `message_log`); Conventions → Scalars (site time zone); Paradigm diagram (`schema --> Settings`).
- **Problem:** Outside `adapter/`, only the listed `frappe.*` names are legal, and `frappe.get_cached_doc` is banned **everywhere**. Yet:
  - `schema/` must read the exposure list and limits from DocWeave Settings.
  - `api.py` must read `enabled`, `allowed_roles` and `allow_administrator`.
  - `api.py` must clear `frappe.local.message_log` (not allowlisted; only `local.request` and `local.response` are).
  - `schema/scalars.py` needs the system time zone (`frappe.utils.get_system_timezone` or similar, not allowlisted).
  - `execution/` must read limits.

  None of `get_single`, `get_doc`, `get_cached_doc`, `db.get_single_value`, `utils.*` or `local.message_log` is allowed. The rule also does not say whether `from frappe.utils import ...` counts as `frappe.*` use. On day one the boundary test fails or someone widens the allowlist, and every unit picks its own accessor.
- **Fix:**
  - Add one sanctioned accessor, `adapter/settings.py: get_settings() -> core.SettingsView`, a frozen dataclass of limits, exposure, roles and flags. Read Settings there with `frappe.get_cached_doc("DocWeave Settings")`, and narrow the ban to "outside `adapter/settings.py`".
  - Because Settings is not user data, allow the transport to inject `SettingsView` into schema and execution the same way it injects the adapter.
  - Add `local.message_log` (or `clear_messages`) to the allowlist for `api.py`, and allowlist specific pure helpers (`frappe.utils.get_system_timezone`, `frappe.utils.get_datetime`) for `schema/scalars.py`.
  - State that `from frappe.x import y` is checked as `frappe.x.y`.
  - Add `adapter/settings.py` to the seed tree.

### R2-2 [HIGH] FR-3's enable/disable switch and FR-2's admin-only Settings are not bound
- **Location:** AD-12, Conventions → Config, Capability Map (FR-1 to FR-3 → AD-11, AD-12, AD-14).
- **Problem:**
  - FR-3 says the endpoint is exposed only when enabled in Settings, and UJ-2 has Raj "enable the endpoint". AD-12's access gate covers roles and Administrator only. The Config row lists "limits, exposure, `allowed_roles` and `allow_administrator`", with no `enabled` flag. One implementer will read "exposure" as the switch, another as the DocType list, and the disabled behaviour (403 `NOT_EXPOSED`? 404?) is undefined. It is also unclear whether `docweave.api.sdl` honours the switch.
  - FR-2 requires Settings to be admin-only. No AD or convention names the DocPerm (round-1 F-19, still open).
- **Fix:**
  - In AD-12, add "**Enabled.** Settings `enabled` (Check, default 0). When off, both `graphql` and `sdl` return 403 `NOT_EXPOSED` before any schema work." Add `enabled` to the Config row.
  - In AD-14 or the Config row, add "DocWeave Settings DocPerm: System Manager read/write only; never exposable (already stated)."
  - Add a negative test in `test_access.py`.

### R2-3 [MEDIUM] The AD-10 cost formula is ambiguous for nested nodes
- **Location:** AD-10 ("Rows per node: ... `child_fanout_estimate` for child tables, 1 for a Link. Cost is the sum of rows × selected fields").
- **Problem:** It does not say whether rows for a nested node are multiplied by the parent's rows. Take `salesOrders(first:100){ items { itemDoc { ... } } }`. Without multiplying, the cost is about 100 + 50 + 1 rows. With multiplying, it is 100 + 5,000 + 5,000. Two implementers will produce limits that differ by orders of magnitude. The multiplicative version is the one that actually bounds load.
- **Fix:** Define `rows(node) = rows(parent) × per_parent(node)`, where `per_parent` is `first` (or max page) for a root connection, `child_fanout_estimate` for a child table, and 1 for a Link. Then `cost = Σ rows(node) × selected_scalar_fields(node)`. Give one worked example in the AD.

### R2-4 [MEDIUM] "Constant number of queries per page" contradicts chunked scanning
- **Location:** AD-4 (query-count test asserts a constant number of queries per page); AD-8 (adapter fetches candidates in chunks until the page fills or the budget runs out); Deferred (FR-5 target).
- **Problem:** When many candidates fail AD-4 (UJ-3), the adapter fetches more chunks, so the query count grows with the ratio of unauthorized rows. Also, any `has_permission` hook that does its own queries (several ERPNext DocTypes have them) adds per-candidate queries that DocWeave cannot control. As written, the test either fails on legitimate fixtures or gets weakened ad hoc.
- **Fix:** Restate the invariant as follows. Queries are independent of the number of parent rows **returned**. They are bounded by `nodes × ceil(scanned / chunk_size) + fixed overhead`, measured on fixtures whose DocTypes have no query-issuing `has_permission` hook. Hook-issued queries are outside the bound and documented. Fix `chunk_size` as a constant or a Setting.

### R2-5 [MEDIUM] The v1 read-only rollback may discard `INTERNAL` error logs
- **Location:** AD-12 ("transport calls `frappe.db.rollback()` before returning"); AD-15 ("`INTERNAL`, logged with `frappe.log_error`"); Operations → Observability.
- **Problem:** `frappe.log_error` inserts an Error Log row in the request transaction. Whether it commits on its own depends on the Frappe version and on flags. If the transport rolls back after an adapter error was logged, the only operational record of `INTERNAL` failures can disappear silently. The ordering between rollback and logging is unstated, so implementations will differ.
- **Fix:** State the order: the transport rolls back first, then writes the Error Log, then commits only that row. The alternative is that `INTERNAL` details go to `frappe.logger("docweave")` (the file log, which needs no transaction) and `log_error` runs after rollback. Add a test asserting that an Error Log row exists after a forced `INTERNAL`.

### R2-6 [MEDIUM] The AD-4 permission projection over-fetches and may hit permlevel rejection
- **Location:** AD-4 ("the candidate query also fetches ... every non-table field").
- **Problem:**
  1. With `ignore_permissions=False`, Frappe v16's `get_query` validates or strips fields the user cannot read at their permlevel. Asking for every non-table field then either raises or silently drops columns, and implementers will handle that differently.
  2. Fetching around 150 columns, text fields included, for up to 2,000 candidates per connection is a large cost to pay when the DocType has no document-level `has_permission` hook at all. In that case the doc-level check reduces to owner/share/User Permission logic, and those fields are known.
- **Fix:** Make the projection "`name`, `owner`, `docstatus`, plus every non-table field **the user can read at its permlevel**", and document that hooks never see higher-permlevel fields. Optionally, for the hobby scope, fetch the full projection only when `frappe.get_hooks("has_permission")` names the DocType or the controller overrides `has_permission`; otherwise fetch `name`, `owner`, `docstatus` and the User Permission link fields.

### R2-7 [MEDIUM] The schema-revision bump on migrate and install is promised but not wired
- **Location:** Operations → Upgrade ("`bench migrate` bumps `schema_revision`"); AD-11 bump triggers; Seed `hooks.py  # doc_events + after_uninstall`.
- **Problem:** DocType JSON synced during `bench migrate` or app install does not reliably fire `doc_events` in a way the handler can catch. No AD or seed entry registers `after_migrate` or `after_install`, so the Operations claim has no implementation owner. The fingerprint (meta `modified`) partly covers this, but only if every worker recomputes it per request, and AD-11 does not say so.
- **Fix:** Add "`after_migrate` and `after_install` bump the revision" to the AD-11 triggers, and change the seed comment to `doc_events + after_install + after_migrate + after_uninstall`. Also state when the fingerprint is computed (per request, from cached meta).

### R2-8 [MEDIUM] The orderBy input shape and multi-key tie-break are undefined
- **Location:** Conventions → Root fields (`orderBy: [SalesOrderOrder!]`); AD-8 keyset ("`name` tie-break in the same direction").
- **Problem:** The fields of `SalesOrderOrder` are never given, so the schema builder and the planner can disagree. A list allows mixed directions (`[{posting_date: ASC}, {grand_total: DESC}]`), and then "same direction" for the tie-break is ambiguous. The keyset predicate across N keys with NULL branches is also a sizeable, bug-prone piece of code.
- **Fix:** Simplest for v1: `orderBy: SalesOrderOrder` (single, not a list) `{ field: SalesOrderSortField!, direction: SortDirection = ASC }`, with `name` tie-broken in that direction. Multi-key ordering goes to Deferred. If the list stays, define `SalesOrderOrder` explicitly and say the tie-break follows the **last** key's direction.

### R2-9 [MEDIUM] Error-mapping ownership and HTTP status are incomplete
- **Location:** AD-15 ("`adapter/errors.py` is the only exception mapper"); AD-12 Response (200/400/403).
- **Problem:** `DEPTH_LIMIT`, `COST_LIMIT`, GraphQL syntax errors, unknown-field validation errors, and `VALIDATION` for `first` above the maximum are raised in `execution/`, which may not import `adapter/`. So either "only" is false or execution violates AD-1. It is also unclear whether a GraphQL syntax error counts as "malformed" (400) or a GraphQL result (200), and what status limit errors get. Clients and tests will disagree.
- **Fix:**
  - Split ownership. `adapter/errors.py` maps **Frappe** exceptions only. `execution/` maps GraphQL validation and limit errors, using `core.ErrorCode`.
  - State the HTTP mapping: 400 only for a non-JSON body or a missing `query` string; 200 for every GraphQL parse, validation, depth, cost and field error, with `errors[].extensions.code`; 403 for the access gate.
  - Map GraphQL parse and validation failures to `VALIDATION`.

### R2-10 [LOW] Gaps in the fieldtype map
- **Location:** Conventions → Fieldtype map.
- **Fix:**
  - Add `HTML Editor` → `String`.
  - Add "any fieldtype not listed is excluded, and the builder logs a warning", so future Frappe fieldtypes cannot crash the build.
  - Map `Rating` → `Float` (Frappe stores 0 to 1).
  - State the standard fields: `owner`, `modified_by` → `String`; `creation`, `modified` → `Datetime`; `docstatus`, `idx` → `Int`. Child types expose `parent`, `parenttype` and `parentfield`, or explicitly not.

### R2-11 [LOW] Stale v2 references inside v1-binding sections
- **Location and fix:**
  - Frontmatter `binds:` includes `FR-11`. Remove it, or annotate it as `FR-11 (v2, non-binding)`.
  - Conventions → Tests: "Every AD from AD-2 to AD-15 has at least one negative test" includes AD-9 and AD-13, which are not built in v1. Change to "every v1-binding AD (AD-2 to AD-8, AD-10 to AD-12, AD-14, AD-15)".
  - The paradigm diagram labels the adapter's outbound edge "Document API". In v1 the adapter uses only `frappe.qb.get_query`, `frappe.has_permission` and unsaved `frappe.get_doc(dict)`. Relabel it or add "(v2 writes)".
  - The PRD glossary and FR-9 still say "signed" cursor. Add a note that "AEAD (Fernet) encryption satisfies the PRD's 'signed'" so a literal reading cannot cause a downgrade.

### R2-12 [LOW] AD-11 fingerprint input "Frappe's metadata version" is not identifiable
- **Location:** AD-11 → Cache key.
- **Problem:** It is not a named Frappe API or key, so no one can implement or test it uniformly.
- **Fix:** Name the exact source, for example a hash of `frappe.get_meta(dt).modified` plus the latest `Property Setter.modified` and `Custom Field.modified` for the exposed DocTypes, read in one cached query. Or drop it and rely on the triggers plus `clear_cache` (see R2-16).

### R2-13 [LOW] `KeysetPosition` is not a core type
- **Location:** Paradigm table (core owns ... `LoadRequest`, `Row`, `Page`); AD-2 signature (`after: KeysetPosition`).
- **Fix:** Add `KeysetPosition` to the core list and to the `core/types.py` seed comment. Execution builds it from the decrypted cursor, which lives in the adapter. State which side decrypts. Today `adapter/cursor.py` would have to be called by execution, which AD-1 forbids, so route it through a `DataAdapter.decode_cursor()` port method.

### R2-14 [LOW] How Datetime filter inputs are parsed is unstated
- **Location:** Conventions → Scalars, Filter input.
- **Fix:** "Datetime inputs with an offset are converted to the site time zone. Inputs without an offset are taken as site time. Date and Time inputs are ISO 8601 with no offset."

### R2-15 [LOW] NFR-1 "review rules" are still unaddressed
- **Location:** Capability Map NFR-1 row.
- **Fix:** For a solo builder, a one-line convention is enough: "PRs touching `adapter/` or `api.py` must add or update a negative test. The CI boundary test plus `test_permissions.py` are required checks." Alternatively, record in Deferred that formal review rules wait for a second contributor.

## Part 3: Over-engineering for a solo hobby v1

These items can be cut or deferred without opening a divergence or a security hole.

### R2-16 [MEDIUM] Simplify AD-11 schema caching
- Revision **and** fingerprint **and** a Redis build lock **and** a random 64-bit revision start, plus DocPerm and Custom DocPerm triggers, is four mechanisms for one cache.
- The Redis lock only prevents a few workers building at the same moment once per change. A build is milliseconds for a handful of DocTypes, so drop the lock.
- AD-11's own last bullet says the schema never depends on permissions, so the DocPerm and Custom DocPerm triggers are not needed. Drop them.
- Keep the revision plus the triggers, with `after_migrate` (R2-7). Keep the fingerprint only if R2-12 names a concrete source.

### R2-17 [LOW] Cursor `kid` rotation
- The key is derived from the site encryption key, which DocWeave never rotates. Accepting "current and previous `kid`" has no rotation process behind it.
- Drop `kid` (keep `v`). A 24 h TTL already bounds exposure, and changing `encryption_key` invalidates every cursor, which is acceptable.

### R2-18 [LOW] Two scan budgets
- A per-connection budget plus `max_total_candidates` is two knobs. The cost rule already caps how many connections a request can hold.
- Keep the per-connection budget, and let `max_total_candidates` default to `scan_budget × max root connections`, or defer it.

### R2-19 [LOW] Multi-key orderBy
- See R2-8. A single sort key plus the `name` tie-break covers UJ-1 to UJ-3 and removes the hardest keyset code.

### Keep as is (not over-engineering)
- Fernet cursor, the AD-2 chokepoint, the AD-1 boundary test, AD-6 filter and sort rejection, AD-15 no existence disclosure, and the v1 rollback guard. They are cheap and they guard the PRD's counter-metric ("no permission leak").

## Coverage trace (v1 PRD → spine)

| Req | Spine | Status |
| --- | --- | --- |
| FR-1 | AD-11, AD-14, fieldtype map | Covered (map gaps R2-10) |
| FR-2 | AD-10, AD-11, Config | Partial: admin-only role missing (R2-2) |
| FR-3 | AD-12 | **Gap:** no enable flag (R2-2) |
| FR-4 | AD-3, AD-6, AD-7, filter convention | Covered; orderBy shape (R2-8) |
| FR-5 | AD-3, AD-4, query-count test | Covered; invariant wording (R2-4) |
| FR-6 | AD-1, AD-2, AD-4 | Covered; allowlist defect (R2-1) |
| FR-7 | AD-5, AD-6 | Covered |
| FR-8 | AD-8 | Covered |
| FR-9 | AD-8 | Covered (encrypted, which exceeds "signed") |
| FR-10 | AD-8 | Covered |
| FR-11 | AD-9, AD-13 [v2] | Correctly out of v1 scope |
| FR-12 | AD-10 | Covered; cost formula (R2-3) |
| FR-13 | AD-11 | Covered |
| FR-14 | AD-15, Error codes | Covered; ownership and status (R2-9) |
| FR-15 | AD-12 `sdl` | Covered |
| NFR-1 | AD-1, Tests | Partial: review rules (R2-15) |
| NFR-2 | Stack, Operations → Release | Covered |
| NFR-3 | Stack | Covered |
| NFR-4 | Tests | Covered |
