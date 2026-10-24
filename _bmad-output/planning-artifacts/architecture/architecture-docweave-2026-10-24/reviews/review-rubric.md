---
review-of: ARCHITECTURE-SPINE.md (DocWeave, 2026-10-24)
reviewer: rubric (good-spine checklist)
date: 2026-10-24
verdict: REVISE: strong paradigm and security core, but several high-severity divergence points remain open
---

# Rubric Review: DocWeave Architecture Spine

## Verdict

**Revise before build.** The hexagonal split, the single read chokepoint (AD-2), two-phase execution (AD-3) and the cursor contract (AD-8) are the right decisions, and they bind the PRD's hardest requirements. But some contracts that the schema, execution and adapter units must share are still unspecified: the fieldtype map, the filter/orderBy input shape, field-level permlevel behaviour and mutation transaction semantics. Two rules also contain defects that would break a stated requirement: the cursor leaks data despite AD-8, and the depth limit rejects introspection, so FR-12 fails. The operational envelope is only lightly covered.

## Checklist summary

| Criterion | Result |
| --- | --- |
| Fixes the real divergence points, misses none | Partial: the fieldtype map, filter shape, permlevel fields, transaction semantics and the has_permission doc source are missing |
| Every AD Rule is enforceable and prevents its divergence | Partial: AD-1 uses a denylist that is easy to evade; AD-8 leaks data; AD-9 does not stop partial commits; AD-10 breaks introspection; AD-11's cache mechanism is doubtful |
| Nothing under Deferred lets two units diverge | Mostly yes. The masking-confirmation item is worded as if AD-5 depends on it. |
| Named tech is verified current | Mostly: graphql-core 3.3.0 exists (stable, GraphQL.js 17 based) and Python 3.14 for v16 is corroborated. But "latest 16.x" conflicts with NFR-2, and pre-commit, MariaDB, Redis and Node are not pinned. |
| Covers every FR/NFR | FR-1 to FR-15 and NFR-1 to NFR-4 are all mapped. Gaps: no FR-5 benchmark target (the PRD delegated it here), no FR-2 admin-only role, no NFR-1 review rules |
| Every owned dimension decided, deferred or open | Deployment: brief but present. Infra/provider: present (no new infra). Operations (release/versioning, upgrade/migrate, observability, uninstall): mostly silent |

## Findings

### F-1 [HIGH] The cursor is signed but not encrypted, so it leaks unauthorized candidate data
- **Location:** AD-8 (cursor encodes `{..., last_scanned_key}`, "HMAC-SHA256 signed ... encoded as base64url")
- **Problem:** The cursor points at the last scanned candidate. That candidate may be a row that passed SQL permissions but failed `has_permission` (AD-4). `last_scanned_key` holds that row's `name` and its `orderBy` value. Base64url is not encryption, so any client can decode the cursor and read the identifier and sort value of a document it is not allowed to see. The `user` and `filter_hash` fields are also readable. This breaks the PRD counter-metric "no permission leak".
- **Fix:** Make the cursor authenticated-encrypted. Use AES-GCM or Fernet with a key derived (HKDF with a `docweave-cursor-v1` label) from the site `encryption_key`. Then decryption failure is `BAD_CURSOR`. Add a negative test in `test_pagination.py` that decodes a cursor and asserts that no plaintext `name` or sort value appears in it.

### F-2 [HIGH] Mutation transaction semantics allow partial commits
- **Location:** AD-9 ("One request is one transaction: Frappe commits on success and rolls back on error"), AD-3
- **Problem:** `graphql-core` catches resolver exceptions and returns them in `errors[]`. The whitelisted method then returns normally, so Frappe **commits**. Take a request with two mutation fields where the second fails validation. The first write is committed and the client sees an error, so the "one request is one transaction" claim is false as built. AD-3 also describes only the query pipeline. It does not say when writes happen relative to planning and preloading for the mutation's result selection, so `writes.py` and `planner.py` authors will choose differently.
- **Fix:** Add a rule to AD-9:
  1. Mutation root fields run serially.
  2. If any mutation field records an error, the transport calls `frappe.db.rollback()` before responding. The alternative is to allow at most one mutation per request and reject more with `VALIDATION`. Pick one.
  3. The pipeline for a mutation is: write phase through the adapter, then plan and preload the result selection through AD-2 and AD-5, then execute.

  Add a test where one of two mutations fails and nothing is persisted.

### F-3 [HIGH] Per-candidate `has_permission` can cause N+1 queries, conflicting with FR-5 and the success metric
- **Location:** AD-4 ("checks each candidate with `frappe.has_permission(doctype, "read", doc, user)`"), §6 success metric "constant, small number of database queries"
- **Problem:** The rule does not say what `doc` is. If implementers pass a name, Frappe calls `get_doc` per candidate, which is up to 2,000 extra queries per request with the default scan budget. If they pass a partial row, `has_permission` hooks and owner or User Permission checks may read fields that were never loaded and decide wrongly. Either way the units diverge, and the "constant number of queries" metric cannot be met as written.
- **Fix:** Specify the following:
  - Candidates are materialized as in-memory `Document` objects from the batched row, with no DB read.
  - The adapter loads the full column set that the permission checks need (`owner`, `docstatus`, and every Link field used by User Permissions), not just the selected fields.
  - The per-doc check is skipped when the DocType has no `has_permission` hook and no controller `has_permission` override (`frappe.get_hooks("has_permission")`).

  Add a query-count assertion test (`test_query_count.py`) for the Sales Order slice.

### F-4 [HIGH] No Frappe fieldtype to GraphQL type map; Password and other sensitive fieldtypes not excluded
- **Location:** Consistency Conventions → Scalars / Field names
- **Problem:** Only Decimal, Date, Datetime, JSON, Link and Table are covered. The rest are unspecified: Int, Float/Currency/Percent (Decimal or Float?), Check (Boolean?), Select (enum or String? Enums make option edits break the schema), Dynamic Link (union or String?), Table MultiSelect, Attach/Attach Image, Duration, Rating, Geolocation, Text Editor, and layout fields (Section/Column/Tab Break, HTML, Button). Most importantly, **Password** fields are not excluded. `builder.py`, `scalars.py`, the planner and the adapter's coercion will each make their own choices, so the schema will not be stable across units.
- **Fix:** Add a fieldtype map table to the conventions with one row per Frappe v16 fieldtype giving the GraphQL type or "excluded". Always exclude Password, layout and display-only fieldtypes. Also state how standard fields (`name`, `owner`, `creation`, `modified`, `docstatus`, `idx`, `parent*`) are exposed.

### F-5 [HIGH] Selecting a permlevel-restricted field has no rule
- **Location:** AD-5, AD-6, conventions ("nullable unless mandatory and never maskable")
- **Problem:** AD-6 covers filtering and sorting on permlevel-restricted fields, but no AD says what happens when a client **selects** one. The client could get null plus `FORBIDDEN`, the field could be silently omitted, the whole query could error, or the adapter could crash because `frappe.qb.get_query` drops or rejects the column. The nullability convention also ignores permlevel. A mandatory field at permlevel 1 would be non-null, so a user without level-1 read nulls out the whole parent object.
- **Fix:** Add a rule, for example: "A selected field the user cannot read at its permlevel returns `null` plus `FORBIDDEN`. The adapter computes the readable-field set from `meta.get_permlevel_access('read')`, the same way it computes masked fields." Then amend nullability: a field is non-null only if it is mandatory, at permlevel 0 and not maskable. Add a negative test.

### F-6 [HIGH] The default depth limit rejects standard introspection, breaking FR-12
- **Location:** AD-10, Deferred (default depth 8)
- **Problem:** The standard introspection query (the `TypeRef` `ofType` chain) nests well past 8 levels. A depth validation rule applied to every operation will reject the introspection that FR-12 and the agent-builder JTBD depend on.
- **Fix:** State in AD-10 that `__schema` and `__type` selections are excluded from depth and cost rules, or carry a separate fixed introspection depth allowance. Add a test that runs `graphql.get_introspection_query()` under the default limits.

### F-7 [MEDIUM] The filter and orderBy input shape is not fixed, and filter canonicalization for the cursor is missing
- **Location:** Conventions → Root fields (`salesOrders(filter, orderBy, first, after)`), AD-8 `filter_hash`
- **Problem:** FR-4 promises "typed filters", but the input type names, operator set (eq, ne, in, like, gt, ... and/or nesting?), orderBy shape (enum versus input with direction, single or multiple keys) and null handling are undecided. The schema builder and the adapter's translation into Frappe filters must agree on all of this. `filter_hash` also needs a canonical serialization, or the same filter produces different hashes and gets `BAD_CURSOR`.
- **Fix:** Add a convention row such as `SalesOrderFilter { field: {eq, ne, in, nin, lt, lte, gt, gte, like, isNull}, and: [..], or: [..] }` and `orderBy: SalesOrderOrder { field: SalesOrderSortField!, direction: ASC|DESC }`. Allow a single sort key, with `name` appended as the tie-breaker. Define `filter_hash = sha256(canonical JSON of the parsed filter, keys sorted)`.

### F-8 [MEDIUM] The closed `_authorized_query` signature cannot express the keyset predicate
- **Location:** AD-2 (closed parameter set) versus AD-8 (keyset on `(orderBy, name)`)
- **Problem:** A keyset continuation needs `(f > v) OR (f = v AND name > n)`. Frappe's list-style `filters` cannot express that cleanly, and the closed signature has no slot for it. Implementers will either break AD-2 by adding a kwarg or a raw criterion, or fall back to offset.
- **Fix:** Add a typed `after: KeysetPosition | None` parameter (holding the order field, direction, value and name) to `_authorized_query`. It is translated inside the adapter with `frappe.qb` criteria. Also specify NULL ordering for nullable sort fields: either sort fields must be non-null, or NULLs sort first and are encoded in the cursor.

### F-9 [MEDIUM] The schema cache mechanism is likely infeasible as stated; revision triggers are incomplete
- **Location:** AD-11 ("cached in `frappe.cache` under `docweave:schema:{schema_revision}`"), `hooks.py`
- **Problem:**
  1. `frappe.cache` pickles values into Redis. A built `GraphQLSchema` holds resolver callables and is impractical to pickle and slow to unpickle on every request. Implementers will each build their own in-process caches.
  2. The bump triggers are DocType, Custom Field, Property Setter and Settings `doc_events`. These may not catch DocType JSON synced during `bench migrate` or app install and upgrade, and they also fire for non-exposed DocTypes, which is harmless but noisy.
  3. Where `schema_revision` itself is stored (a Redis key or a Settings field) is not said.
- **Fix:** Specify the following:
  - Redis holds only `docweave:schema_revision`.
  - Each worker keeps an in-process `{revision: GraphQLSchema}` memo and rebuilds when the revision differs.
  - The revision is also bumped from `after_migrate` and `after_install`.
  - The bump happens via `frappe.db.after_commit.add(...)`.

  Optionally, include the SDL hash in the revision so FR-15 exports are reproducible.

### F-10 [MEDIUM] The AD-1 boundary test is a denylist and is easy to evade
- **Location:** AD-1
- **Problem:** The listed functions omit `frappe.db.sql`, `frappe.db.get_value`, `frappe.get_value`, `frappe.get_cached_doc`, `frappe.get_last_doc`, `frappe.get_single`, `frappe.client.*` and `frappe.model.*`. They also miss aliased imports (`from frappe import get_all as ga`). "`frappe.db.*` data methods" is not mechanically checkable. It is also unclear which accessor `schema/` uses to read Settings (`get_single` or `get_cached_doc`).
- **Fix:** Invert the rule into an allowlist. Outside `adapter/`, only these frappe names may be used: `frappe.whitelist`, `frappe.session`, `frappe.get_meta`, `frappe.cache`, `frappe.logger`, `frappe.log_error`, `frappe.throw`, `frappe._`, exception classes, and one named `adapter.settings.get_settings()`. Any other `frappe.*` attribute access or `from frappe... import` fails the AST test.

### F-11 [MEDIUM] No mapping from Frappe exceptions to error codes, and no HTTP status convention
- **Location:** Conventions → Error shape; AD-12 ("404-equivalent `NOT_EXPOSED`")
- **Problem:** `writes.py`, the adapter and the transport will map exceptions differently. The unmapped cases include `frappe.PermissionError`, `ValidationError`, `MandatoryError`, `DuplicateEntryError`, `LinkValidationError`, `TimestampMismatchError`, `DoesNotExistError` and `CSRFTokenError`. The HTTP status rules are also unset: is it always 200 with `errors[]`, or 4xx for request-level errors? What does "404-equivalent" mean? FR-14 needs predictable codes.
- **Fix:** Add an exception-to-code table to `execution/errors.py`, a convention all units import, plus an HTTP rule. For example: 200 for any executed operation, including field errors; 400 for parse, validation and limit errors; 404 with `NOT_EXPOSED` when the endpoint is disabled; 401/403 come from Frappe auth. Also consider a `CONFLICT` code for `TimestampMismatchError`.

### F-12 [MEDIUM] The operational envelope is thin: release, upgrade, observability and uninstall are silent
- **Location:** Structural Seed deployment paragraph; no operations section
- **Problem:** Deployment (`bench get-app` / `install-app`) and infra (no new services, self-hosted or Frappe Cloud) are decided, but there is no operations section:
  - No app versioning or release scheme, and no compatibility statement linking a DocWeave version to tested Frappe v16 releases.
  - No upgrade path (`patches.txt`, Settings schema changes, cache invalidation on upgrade).
  - Observability stops at a logger name. There is no request timing, no query-count or scan-budget telemetry, and no slow-query logging for the admin persona.
  - No uninstall behaviour (clearing Redis keys, removing Settings).
  - Frappe Cloud support assumes a private bench, which goes unstated.
- **Fix:** Add an "Operations" section, or explicit Deferred or open-question entries, covering:
  - semver releases tagged on GitHub, with a compat matrix recorded in the README and CI;
  - patches in `patches.txt` plus the `after_migrate` revision bump;
  - `frappe.logger("docweave")` emitting one structured line per request (operation name, duration, candidates scanned, DB query count, error codes, no values);
  - a `before_uninstall` hook that deletes the `docweave:*` cache keys.

### F-13 [MEDIUM] "Latest 16.x" conflicts with NFR-2's exact-release testing
- **Location:** Stack → Frappe Framework; CI row
- **Problem:** NFR-2 requires testing against the exact installed release because of known masking and child-context bugs. "Latest 16.x" floats, so CI and users diverge silently. The research addendum names v16.32.0.
- **Fix:** Pin a tested baseline in CI (for example `v16.32.0` or whatever is current at build start). Add a scheduled CI job against `version-16` HEAD to catch regressions, and record the tested release in a compat file. Do the same for MariaDB and Redis: pick one concrete version each for the CI services.

### F-14 [MEDIUM] FR-5's benchmark target, delegated to architecture by the PRD, is not set
- **Location:** PRD FR-5 `[ASSUMPTION: benchmark target to be set in architecture]`; Capability Map FR-4/FR-5 row
- **Problem:** The spine does not state the target, so "no N+1" is not testable and the deferred "child retrieval mechanism" choice has no criterion.
- **Fix:** State a target, for example: "Sales Order + customerDoc + items (+ item Link), any page size up to max, executes at most K SQL queries, where K = 1 per (DocType, level) + the fixed permission and meta overhead, independent of row count. Asserted with `frappe.db` query counting in `test_query_count.py`."

### F-15 [MEDIUM] The scan budget's scope across multiple root connections is ambiguous
- **Location:** AD-8, AD-10, PRD glossary ("maximum candidates examined per request")
- **Problem:** A request can hold several root connection fields, plus aliased copies of one. One unit may apply the budget per connection while another shares it across the request, and the `scanLimitReached` semantics differ between the two. Child-table and Link loads may or may not count as candidates.
- **Fix:** State it, for example: "The scan budget applies per root connection field. The count of root connection fields is capped by the cost rule. Link and child loads are bounded by the parent page and do not consume the scan budget."

### F-16 [LOW] Datetime and time-zone serialization are ambiguous
- **Location:** Conventions → Scalars ("ISO 8601, in the site time zone")
- **Problem:** It is unclear whether the output carries a UTC offset, how filter inputs with an offset are interpreted, and how Frappe user time zones interact. The serializer and the filter parser may diverge.
- **Fix:** Output ISO 8601 with an explicit offset of the system time zone. Inputs without an offset are taken as the system time zone; inputs with an offset are converted. Also map the Time fieldtype.

### F-17 [LOW] Unpinned or unmentioned tooling
- **Location:** Stack
- **Problem:** "pre-commit current" is not a version. Node (v24 for v16 benches, needed by bench setup and the devcontainer) is missing. graphql-core 3.3.0 is current and stable but breaks 3.2: AST nodes are frozen and `ExecutionContext` became `Executor`. The pin should be explicit so examples written against 3.2 aren't copied in.
- **Fix:** Pin pre-commit and Node 24. Add the note "graphql-core 3.3.x API (Executor, frozen AST), not 3.2 examples". Pin `graphql-core>=3.3.0,<3.4` in `pyproject.toml`.

### F-18 [LOW] The Deferred masking-confirmation item reads as if AD-5 depends on it
- **Location:** Deferred, last bullet; the addendum says "No evidence found that direct frappe.qb queries apply masking"
- **Problem:** AD-5 already computes masking in the adapter from metadata, which is correct whether or not `frappe.qb` masks. The Deferred wording ("the source shows masking ...") contradicts the research addendum and may lead an implementer to rely on qb masking.
- **Fix:** Reword: "AD-5 masking is applied by the adapter regardless of whether `frappe.qb` masks. If qb does return placeholder strings, the adapter must replace them before coercion. `test_masking.py` confirms the behaviour on the pinned release."

### F-19 [LOW] Minor coverage gaps: FR-2 role, NFR-1 review rules, cursor lifetime
- **Location:** AD-11 / docweave_settings; NFR-1 mapping; AD-8
- **Problem and fix:**
  - FR-2 says the Settings DocType is admin-only, but no role is named. Fix: "DocWeave Settings permissions: System Manager only."
  - NFR-1 calls for "review rules", which are not reflected. Fix: add a PR checklist item or CODEOWNERS on `adapter/`.
  - Cursors have no expiry or version-rotation policy beyond `v`. Fix: add an issued-at field and an optional maximum age, or state explicitly that cursors do not expire.

## Coverage trace (PRD → spine)

| Req | Spine | Status |
| --- | --- | --- |
| FR-1 | AD-11 | Covered |
| FR-2 | AD-11, AD-10, conventions | Covered; role unnamed (F-19); revision triggers (F-9) |
| FR-3 | AD-12 | Covered; HTTP status unclear (F-11) |
| FR-4 | AD-3, AD-7, conventions | Partial: filter shape (F-7), fieldtypes (F-4), permlevel select (F-5) |
| FR-5 | AD-3 | Partial: no target (F-14); has_permission N+1 (F-3) |
| FR-6 | AD-1, AD-2, AD-4 | Covered; boundary test weak (F-10) |
| FR-7 | AD-5, AD-6 | Covered |
| FR-8 | AD-8 | Covered; budget scope (F-15) |
| FR-9 | AD-8 | Covered, but leaks data (F-1) |
| FR-10 | AD-8 | Covered |
| FR-11 | AD-9 | Partial: transaction semantics (F-2), error mapping (F-11) |
| FR-12 | AD-10, AD-12 | Defect: introspection versus depth (F-6) |
| FR-13 | AD-11 | Covered |
| FR-14 | Conventions → errors | Partial (F-11) |
| FR-15 | AD-12 `docweave.api.sdl` | Covered |
| NFR-1 | AD-1, test conventions | Mostly; review rules (F-19) |
| NFR-2 | Stack | Conflict: floating 16.x (F-13) |
| NFR-3 | Stack | Covered |
| NFR-4 | Test conventions | Covered |
