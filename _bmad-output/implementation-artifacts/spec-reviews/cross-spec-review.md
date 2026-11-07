# Cross-spec review: Stories 1.1 to 4.3

- **Date:** 2026-11-01. **Baseline:** `cd5c126`.
- **Inputs:** the 18 draft specs (`spec-1-1` to `spec-4-3`), the per-spec reviews in `spec-reviews/` (5 files: `review-1-1-to-1-4`, `review-1-5-to-1-7`, `review-2-1-to-2-4`, `review-3-1-to-3-4`, `review-4-1-to-4-3`; the request mentioned 7, but only these 5 exist and together they cover all 18 specs), `epics.md`, `ARCHITECTURE-SPINE.md`, the epic context files, Frappe v16.53.0 and ERPNext v16.52.1 under `~/frappe-bench/apps`, and the graphql-core 3.3.1 wheel (downloaded to `/tmp/gqlcore-9jUa`, read as data).
- **Scope:** no spec, review or planning file was edited. Finding IDs refer to the per-spec reviews (for example `R1.5-F1` = review-1-5-to-1-7, spec 1.5, F1; `R3-3.1-2` = review-3-1-to-3-4, finding 3.1-2). New findings from this review are `X-n` (section 2).

**How to read this:** section 1 lists every decision for the human, grouped by theme and deduplicated. Section 2 covers cross-spec consistency and story ownership. Section 3 settles the contradictions between reviews. Section 4 lists the fixes that need no decision, per spec.

---

## 1. Decisions for the human

**Counts:** A. Boundary / AD-1: 4 · B. Gate and HTTP: 6 · C. Errors, leakage and logging: 7 · D. Schema shape: 3 · E. Cache: 1 · F. Filters, pagination and limits: 7 · G. Test fixtures: 1 · H. Release and operations: 3 · I. v2 writes: 16. **Total: 48.**

**Blocking Story 1.1:** **A1** (the checker's policy inside `adapter/`) and **A2** (how `TYPE_CHECKING` imports are treated). Both change how `test_boundaries.py` is designed. Nothing else in 1.1 needs a decision. All other open items are fixes (section 4).

**Blocking the rest of Epic 1:** A3 and B1 to B3 (1.2); D1, D2 and B4 (1.3); E1 (1.4); C1, C2 and F1 (1.5); G1 (1.6); F2 and F6 (1.7). F3 (where `max_cost` lives) should be decided before 1.2, because the recommendation puts the field into 1.2.

Each entry gives the question, the options with their consequences, the affected specs, whether the spine or the epics change, and a recommendation.

### A. Boundary / AD-1

**A1. Inside `adapter/`, is the AD-1 checker an allowlist or a denylist?** *Blocks 1.1.*
- Sources: R1.1-F1, R1.5-F2, R1.6-F1, R1.7-F8, R2.2-F9.
- Options:
  - (a) A per-file allowlist inside `adapter/` too. 1.1 builds the mechanism, including function-scoped rules such as "`frappe.qb` only inside `_authorized_query`". Each story adds its names explicitly: 1.5 adds `frappe.qb`, `get_meta`, `session.user` and the three exception classes; 1.6 adds `frappe.model.get_permitted_fields`; 1.7 adds query-builder terms; 2.2 adds `frappe.utils.password.get_encryption_key`. This enforces "data is read only through `_authorized_query`", at the cost of list upkeep in each story.
  - (b) A denylist inside `adapter/`: the six banned names plus every `frappe.db.*` and `frappe.qb.*` except `get_query` inside `_authorized_query`. No upkeep, but `frappe.get_lazy_doc`, `get_last_doc` and future Frappe readers pass unnoticed.
- Affects: 1.1, 1.5, 1.6, 1.7, 2.2, 3.1, 3.3, 4.3.
- Spine: yes. AD-1 says how the adapter is checked, and that the exact per-file lists live in `test_boundaries.py`.
- **Recommendation: (a).** NFR-1 is the reason the checker exists, and only an allowlist catches readers nobody thought to ban.

**A2. Are imports under `if TYPE_CHECKING:` checked?** *Blocks 1.1.*
- Source: R1.1-F8.
- Options:
  - (a) Exempt from the `frappe.*` name check. The import-direction check still applies to them. This allows `from frappe.model.meta import Meta` for type hints.
  - (b) No exemption. Use string annotations with no import, and type checkers lose those types.
- Affects: 1.1 and every later story.
- Spine: one sentence in AD-1.
- **Recommendation: (a).** These imports have no runtime effect, and type hints on Frappe objects help in `schema/`.

**A3. How do DocType controllers get `Document` and `frappe.throw`?**
- Source: 1.2 Open Question 1.
- Options:
  - (a) Amend AD-1 to allow `frappe.model.document.Document`, `frappe.throw` and `frappe._` in `docweave/docweave/doctype/**` only, and test that scope. The guard stays tight, and the spine changes.
  - (b) Leave the folder out of the checker. No spine change, but a controller can read data unchecked.
- Affects: 1.2, and 1.3 (the collision check imports `schema.naming` from the controller; the Configuration layer is missing from the spine's import arrows, so add Configuration → schema).
- Spine: yes (AD-1 and the arrows).
- **Recommendation: (a).** Controllers run on save, so they are a data path too, and the allowance is tiny.

**A4. May code in `docweave/patches/**` write Settings?**
- Sources: 4.3 Open Question 2, R2.4-F4.
- Options:
  - (a) Amend AD-1 to allow named write calls (`frappe.reload_doc`, `frappe.db.set_single_value`, `frappe.get_single`) in `patches/**` only.
  - (b) Patches call a writer in `adapter/settings.py`, which gives the read-only adapter a write path.
  - (c) Defer. If F3 puts `max_cost` into 1.2 and H1 ships an empty `patches.txt`, v1 has no patch.
- Affects: 2.4, 4.3.
- Spine: (a) yes, (c) not now.
- **Recommendation: (c), and (a) when the first real patch appears.** No v1 patch is needed, so neither rule is exercised before then.

### B. Gate and HTTP behaviour

**B1. What is the default `allowed_roles`?**
- Source: 1.2 Open Question 2.
- Options:
  - (a) An empty table means "any Desk User", and the field description says so. No install-time write, but the UI shows an empty table.
  - (b) An `after_install` hook saves a `Desk User` row. The UI shows the real value, but install writes Settings.
- Affects: 1.2, 4.1 (if B5 picks the shared gate).
- Spine: no. AD-12 already says "default: desk users".
- **Recommendation: (a).** It needs no write at install time, and `enabled` is off by default anyway.

**B2. Requests that Frappe refuses before DocWeave runs: Guest, GET, and an invalid JSON body with a JSON Content-Type.**
- Sources: 1.2 Open Question 3, R1.2-F2, R4.2-F9, plus the dependent items in 4.1 and 4.2.
- Options:
  - (a) Accept Frappe's envelope (403 or 417, with `exc_type` and `_server_messages`). DocWeave's 400 then applies only to a body that parses but has the wrong shape, or that isn't JSON. These requests get no DocWeave log line.
  - (b) `allow_guest=True` on all methods, and refuse inside DocWeave. Bodies are uniform, but CSRF safety then rests on DocWeave's own check, and invalid JSON still fails in Frappe's `make_form_dict` before DocWeave runs.
  - (c) Require a non-JSON Content-Type (`application/graphql+json` or `text/plain`) and parse the body in DocWeave. This is non-standard for clients.
- Affects: 1.2, 4.1, 4.2.
- Spine: one sentence in AD-12: "Bodies written by DocWeave are GraphQL JSON only. Requests refused by Frappe's whitelist or body parser get Frappe's response."
- **Recommendation: (a).** It keeps Frappe's own CSRF and method checks, which AD-12 prescribes, and (b) can't fix the invalid-JSON case anyway.

**B3. Are virtual DocTypes (`is_virtual=1`) rejected as exposed rows?**
- Source: R1.2-F5.
- Options:
  - (a) Reject them on save, as for Single DocTypes.
  - (b) Allow them, and let the read fail later.
- Affects: 1.2, 1.3 (the builder asserts the same rule).
- Spine: yes, the AD-14 list.
- **Recommendation: (a).** `get_query` can't read a table that doesn't exist, so allowing them only fails later and less clearly.

**B4. What does the endpoint do when it is enabled but nothing is exposed?**
- Sources: 1.3 Open Question 3, and the dependent item in 4.1.
- Options:
  - (a) 403 `NOT_EXPOSED` while `exposed_doctypes` is empty. Introspection is blocked too.
  - (b) A fixed placeholder field `_docweave: String`, which every schema then carries.
- Affects: 1.3, 4.1.
- Spine: no (an AD-12 note is optional).
- **Recommendation: (a).** FR-1 says nothing is reachable until it is configured, and there is nothing to introspect.

**B5. Who may export the SDL?**
- Sources: 4.1 Open Question 1, R4.1-F2, epic-4-context.
- Options:
  - (a) The `graphql` gate. Administrator is allowed only with `allow_administrator`. The epics' AC changes.
  - (b) System Manager only, ignoring `enabled` and `allowed_roles`. Administrator then always passes, and AD-12 changes.
  - (c) Both checks, with the gate first. Strictest.
- Affects: 4.1.
- Spine or epics: (a) epics; (b) spine.
- **Recommendation: (a).** Any allowed user can already rebuild the SDL through introspection, so a stricter rule protects nothing.

**B6. What is the body format of a successful SDL export?**
- Source: 4.1 Open Question 2.
- Options:
  - (a) `text/plain; charset=utf-8` with the raw SDL. `curl > schema.graphql` just works, and errors stay JSON.
  - (b) `{"data": {"sdl": "..."}}`. One content type for every response, but clients must unwrap it.
- Affects: 4.1, 4.2 (the log line).
- Spine: (a) needs a small exception in AD-12's "GraphQL JSON only".
- **Recommendation: (a).** Tool builders, the epic's audience, want a file they can save directly.

### C. Errors, leakage and logging

**C1. How are exceptions raised during AD-4 Stage 2 contained?**
- Sources: R1.5-F1, R4.2-F4.
- Stage 2 runs only for names that exist. Today a `has_permission` hook that calls `frappe.throw` returns `VALIDATION` (with the hook's message), a `KeyError` returns `INTERNAL`, and a missing document returns `NOT_FOUND`. That is an existence oracle.
- Options:
  - (a) Any exception while evaluating one candidate denies that candidate. The client sees a body identical to "missing". Exceptions that aren't permission errors are deferred-logged as `INTERNAL` for the admin.
  - (b) Keep AD-15 literally, and document the oracle as a residual.
- Affects: 1.5, 1.7, 2.3, 4.2.
- Spine: (a) adds one sentence to AD-15.
- **Recommendation: (a).** AD-15's purpose is "NOT_FOUND whether or not it exists", and hooks that throw are common.

**C2. What does a "sanitized" `VALIDATION` message contain?**
- Sources: R1.5-F4, 4.2 Open Question 3, R3-3.1-5.
- Options:
  - (a) The class name plus Frappe's message, with HTML stripped, truncated to 200 characters. Actionable, but it can echo values the caller can't see.
  - (b) The class name plus a fixed message per class. Leaks nothing, but less actionable.
  - (c) (b) on the read path, with (a) reconsidered for v2 writes.
- Affects: 1.5, 4.2, and v2's 3.1 to 3.3.
- Spine: one sentence in AD-15 defining "sanitized".
- **Recommendation: (c).** Under C1(a), v1 almost never maps a `ValidationError`. A fixed message costs nothing now, and writes need their own rule (I-section).

**C3. Does the Error Log metadata keep the request body (query, variables, cursors)?**
- Source: R4.2-F6.
- Options:
  - (a) Accept it, because Error Log is System Manager only.
  - (b) Blank `frappe.local.form_dict` before `log_error` in the `finally`. AD-1 then allows `frappe.local.form_dict` in `api.py`.
- Affects: 1.2 (the first `finally`), 4.2.
- Spine: (b) one AD-1 entry.
- **Recommendation: (b).** The epic says no cursor or value ever reaches the log, and the fix is one line.

**C4. At what level is the request log line written?**
- Source: 4.2 Open Question 2.
- Options:
  - (a) Set the `docweave` logger to INFO on first use. The line always appears, in a rotating file.
  - (b) Log at INFO and leave Frappe's level alone. There is no line in production until an admin raises the level.
  - (c) Log at WARNING. Always shown, but every request looks like a warning.
- Affects: 4.2.
- Spine: no.
- **Recommendation: (a).** The epic AC wants one line per request, and (b) silently fails that in production.

**C5. What does the log line's "query count" measure?**
- Sources: 4.2 Open Question 1, R4.2-F12.
- Options:
  - (a) Wrap `frappe.db.sql` on the request's db object. Exact, but AD-1 changes and the DB layer is monkey-patched on the hot path.
  - (b) Count DocWeave's own adapter calls, as `adapter_calls`. This misses hook queries.
  - (c) Drop the count from production, and keep exact counts in tests only.
- Affects: 4.2, plus the epics' 4.2 AC and the spine's Logging convention.
- Spine or epics: (a) AD-1; (b) and (c) the Logging convention or epics wording.
- **Recommendation: (b).** It is the number DocWeave controls (AD-3 batching), with no patching. The wording becomes "adapter query count".

**C6. Does the log line include the user?**
- Source: 4.2 Open Question 4.
- Options:
  - (a) Include `frappe.session.user`. Admins can trace callers, and an email lands in the log.
  - (b) Leave it out. Matches the spine's list.
- Affects: 4.2.
- Spine: (a) yes.
- **Recommendation: (b) for v1.** It matches the spine. Callers can still be traced through API keys and access logs.

**C7. Which accepted residuals does the README document?**
- Sources: R1.5-F7, R2.3-F5, R2.2-F7, R4.2-F13, B2, AD-12.
- One approval for the list:
  - `scanLimitReached`, or `hasNextPage: true` followed by an empty page, can reveal hook-rejected matches (wording from R2.3-F5).
  - A select-only role plus a shared document is more restrictive than REST (fails closed).
  - Frappe's envelope for Guest, GET and invalid JSON (per B2).
  - A deferred Error Log entry is lost when Redis is down.
  - Hooks that commit explicitly break the read-only guarantee.
  - A newly granted unmask stays masked until the DocType cache is cleared.
  - Cursor length leaks name length, unless padded (section 4 pads it).
- Affects: 1.5, 2.3, 4.2, 4.3 (README).
- Spine: AD-15 already lists one residual. Point it to the README list.
- **Recommendation: approve the list.** Every item fails closed or is Frappe behaviour that DocWeave can't change.

### D. Schema shape

**D1. What happens when two fields map to the same GraphQL name?**
- Sources: 1.3 Open Question 1, R1.3-F6, R1.3-F4(c).
- Options:
  - (a) Fail the build, naming both (the epics). A customization can take the whole API down.
  - (b) Drop the custom field with a logged warning (the spine), and fail only when neither side is custom (for example `x_doc` against the derived `xDoc`, or `foo_bar` against `foo__bar`).
- Affects: 1.3, 4.1.
- Spine or epics: (a) the spine Names convention; (b) the epics' 1.3 AC.
- **Recommendation: (b).** One Customize Form edit shouldn't take every client offline. Standard fields always win, and collisions between standard fields still fail loudly.

**D2. How is a Decimal written on the wire?**
- Sources: 1.3 Open Question 2, and the dependent item in 4.1.
- Options:
  - (a) `str(value.normalize())`, which gives `"1E+2"`.
  - (b) `format(value.normalize(), "f")`, which gives `"100"` and `"0.5"`.
- Affects: 1.3, 2.1 (input), 4.1 (scalar description).
- Spine: (b) changes the Scalars convention.
- **Recommendation: (b).** Exponent strings break naive clients, and (b) is still exact.

**D3. Which fieldtypes are non-filterable and non-orderable?**
- Sources: 2.1 Open Question 2, R2.1-F7.
- Options:
  - (a) Add Geolocation, HTML Editor and Table MultiSelect to the spine's non-filterable list.
  - (b) Keep the list literal: Geolocation gets `eq` on JSON, and HTML Editor is filterable.
- Affects: 2.1.
- Spine: (a) the Filter input convention.
- **Recommendation: (a).** Equality on serialized JSON or on HTML is fragile and nobody needs it.

### E. Cache

**E1. Does v1 have a schema build lock (epics 1.4 AC 4; the spine lists it under v2)?**
- Source: 1.4 Open Question.
- Options:
  - (a) Build a Redis lock now. The spine changes.
  - (b) No lock: each worker that misses builds its own copy. The epics' AC 4 is dropped.
- Affects: 1.4.
- Epics: (b) drops the AC; (a) changes the spine.
- **Recommendation: (b).** The schema lives in a per-process LRU and can't be shared across workers, so a lock would only serialize builds ("reuse the result" is impossible) and add a failure mode.

### F. Filters, pagination and limits

**F1. How does one failed plan node avoid nulling the rest of the response?**
- Sources: 1.7 Open Question 2, R1.5-F1 (shape), R1.7-F2, R2.2-F3, and the dependent items in 2.1 and 2.2.
- Options:
  - (a) The port returns `Sequence[Page | list[Row] | Sentinel]`. Planner-side failures sit in `PlanNode.failure`, and `graph.assemble` places either kind at the node's response key. An exception never nulls `data`.
  - (b) The adapter returns rows only, and the executor enforces limits after the load. `max_child_rows` then moves out of the adapter and over-cap rows are fetched first, and per-connection `FORBIDDEN` and `BAD_CURSOR` still need a channel.
- Affects: 1.5 (introduce the shape), 1.7, 2.1, 2.2, 3.4.
- Spine: (a) changes AD-16's port signature.
- **Recommendation: (a), introduced in 1.5.** Every later story needs per-node failure, and 1.5's "a `DocWeaveError` gives `data: null`" contradicts its own alias row.

**F2. Where is the "constant query count from 1 to 50 orders" AC proven?**
- Sources: 1.7 Open Question 1, and the dependent item in 2.2.
- Options:
  - (a) 1.7 proves it over 1 to 50 item rows with `itemCodeDoc`, and 2.2 proves it over 1, 10 and 50 orders. 2.2 already has that task.
  - (b) Batch identical aliased roots into one node, which breaks AD-3's node identity rule.
- Affects: 1.7, 2.2.
- Epics: (a) moves part of the 1.7 AC to 2.2.
- **Recommendation: (a).** It keeps AD-3 intact, and 2.2 already carries the test.

**F3. What is the default `max_cost`, and which story adds it?**
- Source: 2.4 Open Question.
- Options:
  - 10,000: strict. A default-`first` list with a child table fails.
  - 50,000: a 100-row page with 10 scalars and a 10-scalar child table (51,000) still fails.
  - 100,000: permissive.
  - In every case, add the field in 1.2 rather than 2.4. Then no patch is needed (the product is unreleased), 2.4's AD-1 patch problem (R2.4-F4) goes away, and 4.3 ships an empty `patches.txt`.
- Affects: 1.2, 2.4, 4.3, and the epics' 1.2 AC (the defaults list).
- Spine: yes, "Default limit values".
- **Recommendation: 100,000, added in 1.2.** It matches `max_child_rows` of 10,000 × about 10 fields, so the headline "orders with items" list query passes at default settings.

**F4. How is AD-4 work bounded per request? Cost counts leaves, so 100 aliased `first:1` connections cost 100 but make up to 20,000 `get_doc` checks.**
- Source: R2.4-F3.
- Options:
  - (a) Each connection adds `scan_budget × k` to the cost. One estimate, but the published formula changes.
  - (b) A per-request cap on connection occurrences, a new Setting (for example `max_connections` = 5, giving `COST_LIMIT` before planning).
  - (c) Accept it for v1 and leave it to rate limiting.
  - (d) Bring the v2 `max_total_candidates` forward. That breaks the 2.3 AC "one alias exhausting its budget doesn't affect the other".
- Affects: 2.3, 2.4, 1.2 (if a Setting is added).
- Spine: (a), (b) and (d) change AD-10 or "Deferred".
- **Recommendation: (b), default 5, added in 1.2 with the other limits.** It bounds the worst case at 1,000 checks (about 5 REST pages), keeps the cost formula and alias independence, and is easy to explain.

**F5. Is the size of the filter IR capped?**
- Source: R2.1-F8.
- Options:
  - (a) Cap IR nodes plus `in` values at 1,000 per connection, giving `VALIDATION`.
  - (b) Accept the gap.
- Affects: 2.1.
- Spine: (a) adds a line to the Filter input convention.
- **Recommendation: (a).** Otherwise a huge SQL predicate costs 1.

**F6. When `max_child_rows` is crossed, which child nodes fail?**
- Source: R1.7-F5.
- Options:
  - (a) Only the node whose load would cross the remaining budget gets `COST_LIMIT`. Later nodes keep the remaining budget.
  - (b) That node and every later child node fail.
  - Either way: query with `limit = remaining + 1`, and order the nodes in a level by path.
- Affects: 1.7.
- Spine: no.
- **Recommendation: (a).** The fewest fields fail, and the result is still deterministic once nodes are ordered by path.

**F7. Does a forbidden filter reject the whole request, or only its connection?**
- Source: 2.1 Open Question 1.
- Options:
  - (a) Only the connection. Siblings still return, as AD-5's alias test requires.
  - (b) The whole request gets `data: null` (the epics' wording).
- Affects: 2.1.
- Epics: (a) changes the 2.1 AC wording.
- **Recommendation: (a).** It is consistent with AD-5, AD-8 and F1.

### G. Test fixtures

**G1. Which masked Currency field (and which Date and Phone fields) do the masking tests use?**
- Sources: 1.6 Open Question, R1.6-F3, and the dependent item in 2.1.
- Options:
  - (a) Test-only Custom Fields on Customer (`credit_limit` Currency, plus a Date and a Phone field), as Spike 0.3 did. The AC text stays.
  - (b) Mask native Sales Order `grand_total`. The AC text changes.
- Affects: 1.6, 2.1, 3.1, 3.2.
- Epics: (b) only.
- **Recommendation: (a).** Spike 0.3 already proved this route, and it covers Date and Phone too.

### H. Release and operations

**H1. Does the first release ship a patch?**
- Source: 4.3 Open Question 1.
- Options:
  - (a) An empty `patches.txt` with both sections, proved by the list test.
  - (b) One idempotent limits patch.
- Affects: 4.3, 2.4.
- Spine: no.
- **Recommendation: (a).** With F3 in 1.2, there is nothing to migrate.

**H2. Which records survive an uninstall?**
- Source: R4.3-F5.
- Options:
  - (a) Keep `Version` rows for DocWeave Settings, `Patch Log` and Error Log, and list them in the README.
  - (b) Delete them in `after_uninstall`.
- Affects: 4.3.
- Spine: no.
- **Recommendation: (a).** They are audit records, and deleting them would need writes outside the adapter.

**H3. What is the release policy?**
- Source: R4.3-F6.
- Options:
  - (a) Confirm "a patch that changes Settings is at least a minor release". The README states the supported range `>=16.53.0,<17` with the tested tags.
  - (b) Drop the semver detail.
- Affects: 4.3.
- Spine: (a) adds the detail to Operations.
- **Recommendation: (a).** It is standard semver, and the range is already in the spine's Stack.

### I. v2 writes (Epic 3)

None of these block v1. Decide them at v2 kickoff, together with AD-9, AD-13, AD-15 and AD-16 amendments. Recommendations are given so the specs can be fixed in one pass.

| # | Question (sources) | Options and consequences | Recommendation and reason |
|---|---|---|---|
| I1 | Which DocTypes get mutations? (3.1 OQ1, R3-3.4-1) | Every exposed DocType: an upgrade turns read exposure into write exposure. / A per-row `allow_writes` flag, default off: Settings field, patch, fingerprint input. | **Opt-in flag, and refuse it for DocTypes whose insert runs DDL** (DocType, Custom Field, Property Setter). Write exposure should never arrive by upgrade. |
| I2 | What code does a refused write get? (3.1 OQ2, 3.2 OQ1, 3.3 OQ3, R3-3.3-3) | `NOT_FOUND`: one map, but misleading. / `FORBIDDEN` on a readable document, `NOT_FOUND` on an unreadable one: amends AD-15. / A new `PERMISSION` code: amends the code list. | **`FORBIDDEN` on a readable document.** Readability is already proven, so nothing is disclosed. |
| I3 | Where does write code live? (3.1 OQ3, 3.4 OQ3) | `adapter/writes.py` plus `DataAdapter.write`: amends AD-1, AD-16 and the seed. / Inside `frappe_v16.py`. | **`adapter/writes.py`.** One file is allowed `get_doc`, `insert`, `save` and `delete_doc` for writes. |
| I4 | Are required fields non-null in the input? (3.1 OQ4, R3-3.4-4) | All nullable, and Frappe's mandatory check gives `VALIDATION`. / `reqd` fields non-null. | **All nullable.** Frappe and hook defaults keep working. |
| I5 | Do Link validation and `fetch_from` become oracles? (R3-3.1-2, R3-3.1-4) | Accept as REST parity and document it. / Pre-check each sent Link through AD-2 and AD-4, giving field `NOT_FOUND`. | **Pre-check.** It honours AD-7 and AD-15. |
| I6 | Lost updates (3.2 OQ2) | No check. / An optional `expectedModified` argument. | **Optional `expectedModified`.** It is cheap and opt-in. |
| I7 | What does an explicit `null` on a Table field do? (R3-3.2-2) | The same as `[]`. / `VALIDATION`. | **`VALIDATION`.** Clearing all rows should need an explicit `[]`. |
| I8 | 3.2 without 3.3 leaks stored values through `UpdateAfterSubmitError` (R3-3.2-3) | Move the `docstatus` pre-check into 3.2. / Release 3.2 and 3.3 together. | **Move the pre-check into 3.2.** Every story stays safe on its own. |
| I9 | What code does deleting a submitted document get? (3.3 OQ1) | `VALIDATION`. / `FORBIDDEN`. | **`VALIDATION`.** It agrees with Frappe. |
| I10 | Can a cancelled document be deleted? (3.3 OQ2) | Refuse it. / Allow it, as Frappe does. | **Allow it.** Parity with desk and REST. |
| I11 | Can `allow_on_submit` child columns change in a table that isn't `allow_on_submit`? (R3-3.3-2) | Follow Frappe: patch by row `name`, with no rows added or removed. / Stricter: amend the AC. | **Follow Frappe.** That is what the AC's words mean. |
| I12 | Delete removes attachment files on disk, and a rollback can't restore them (R3-3.3-4, R3-3.4-1) | Document it. / Delete must be the only mutation in a request. / Refuse deletes when attachments exist. | **Delete must be the only mutation in its request, and document the rest.** That makes all-or-nothing hold. |
| I13 | Who issues the commit? (3.4 OQ1) | Frappe's request end. / `api.py` calls `frappe.db.commit()`. | **`api.py`.** Explicit, and testable in-process. |
| I14 | What error do mutations get that didn't fail themselves? (3.4 OQ2) | A new `ABORTED` code. / `VALIDATION`. / `null` with no error. | **`ABORTED`.** Clients can tell it from their own error. This lifts 4.2's v1 "no new codes" rule for v2. |
| I15 | How is write volume bounded? (R3-3.1-6) | A `max_mutations` Setting, with input child rows capped by `max_child_rows`. / Accept it. | **Add the bounds.** AD-10's intent applies to writes too. |
| I16 | When are payloads read? (R3-3.1-9) | After all writes. / Interleaved per field. | **Interleaved.** It matches GraphQL's serial mutation semantics. |

### Spine and epics amendments implied by the recommendations

- **Spine:**
  - AD-1: A1, A2, A3, C3, and the Configuration → schema arrow.
  - AD-7: add `parenttype` to the child filter (section 2.2; not a decision).
  - AD-10: F4.
  - AD-11: add Custom DocPerm and DocPerm to the triggers (X-10).
  - AD-12: B2, B6.
  - AD-14: B3.
  - AD-15: C1, C2, C7.
  - AD-16: F1 (port union); `Row.matched_key` as an attribute (X-4); `estimate_cost(plan, settings)` (X-5); float and time filter values (R2.1-F4).
  - Conventions: D1, D2, D3, F5, C5.
  - Default limit values: F3, F4.
  - Deferred: E1 (lock stays in v2).
- **Epics:**
  - 1.2: the defaults list gains `max_cost` and `max_connections`.
  - 1.3: D1.
  - 1.4: drop AC 4 (E1).
  - 1.7: the query-count AC moves to 2.2 (F2).
  - 2.1: wording "connection" (F7).
  - 4.1: B5.
  - 4.2: wording "adapter query count" (C5).

---

## 2. Cross-spec consistency and ownership

### 2.1 Names, signatures and types that differ between specs

| Item | Where they differ | Owner and resolution |
|---|---|---|
| **X-1 `SettingsView` fields and defaults** | 1.2 defines `(enabled, allow_administrator, allowed_roles, exposed_doctypes, max_page_size, scan_budget, max_depth, child_fanout_estimate, max_child_rows, modified)`. 2.4 adds `max_cost` with a patch. The spine's defaults have no `max_cost`. F4 may add `max_connections`. | **1.2 owns every limit**, including `max_cost` (and `max_connections` if F4 is (b)). Drop 2.4's patch task. `exposed_doctypes` is a **sorted** tuple, so the fingerprint and `print_schema` are deterministic (4.1 needs byte-identical SDL). `get_settings()` falls back to the default for a missing or `< 1` limit (R2.4-F4). |
| **X-2 Port result shape** | Spine: `Sequence[Page \| list[Row]]`. 1.5: `Sequence[list[Row]]`. 2.1: widens it "plus a failure form". 1.7 Open Question: `\| Sentinel`. | **1.5** declares `Sequence[list[Row] \| Sentinel]` (F1), and **2.1** adds `Page`. The final form is `Sequence[Page \| list[Row] \| Sentinel]`. |
| **X-3 Sentinels** | 1.5 creates `Sentinel(code)` with only `MASKED`, `FORBIDDEN` and `NOT_FOUND`. 1.7 "adds a `COST_LIMIT` sentinel". 2.2 needs `BAD_CURSOR` and `VALIDATION`, which no task delivers (R2.2-F3). | **1.5** makes `Sentinel(code: ErrorCode)` generic, valid for any code, with the constants as conveniences. No later story needs an "add sentinel" task. `PlanNode.failure` is owned by **2.2**, its first planner-side failure. |
| **X-4 `Row.matched_key`** | Spine AD-16: "Link rows include `matched_key`" (a mapping key). 1.5: an attribute on the immutable mapping. R1.7-F3: one `Row` per matched key. | **1.5**: an attribute, so it can't collide with a real fieldname `matched_key`. Change the spine text. 1.7 emits one Row per true key flag. |
| **X-5 Executor, planner and cost signatures** | 1.3 `execute(schema, request, root_value=None)` → 1.5 `execute(schema, request, adapter)` → 2.1 adds `settings` → 4.2 adds `stats` → 3.4 returns an outcome. 1.5 `plan(schema, document, operation_name, variables)` → 2.1 adds `settings`. Spine and epics `estimate_cost(plan)` → 2.4 `estimate_cost(plan, settings)`, and 3.1 cites the old form. 1.5 `FrappeV16Adapter(user, settings)` → 4.2 adds `stats`. | **1.5** fixes the final v1 forms up front: `plan(schema, document, operation_name, variables, settings)` and `execute(schema, request, adapter, settings, stats=None) -> dict`. **2.4** keeps `estimate_cost(plan, settings)`, and the spine text follows. **4.2** adds `stats=None` to the adapter constructor. |
| **X-6 `ErrorCode` owner** | The epics put `ErrorCode` in 1.5. Spec 1.2 creates it because it needs `NOT_EXPOSED`. | **1.2.** 1.5 only extends `core/types.py`. 4.2's "no new codes" applies to v1 only (I14 adds `ABORTED` in v2). |
| **X-7 `_authorized_query` columns** | 1.6: "queries only the rest plus `name`". 1.7 also selects `parent`, `parentfield`, `idx` and Link source fields. 2.2 needs the order fields (R2.2-F2). R1.7-F3 adds key flags. | **1.6**'s wording becomes: "the readable, unmasked selected fields, plus `name` and the columns the load kind and the resolved order need. Extra columns never enter `Row` unless the client selected them." |
| **X-8 `LoadRequest` and parent names** | `_authorized_query` has `parent_names`, but `LoadRequest` doesn't. | **1.7**: for CHILDREN, `keys` carries the parent names, and the adapter intersects them with the parents its `PermissionChecker` passed (R1.7-F6). No AD-16 change. |
| **X-9 Validation rules** | 1.3 stamps `VALIDATION` on every validation error. 2.4 keeps rule-set codes. R1.1-1.4 says to add `recommended_rules` (wrong; see section 3). | **1.3** uses the default `specified_rules`, which already bound introspection. **2.4** swaps `MaxIntrospectionDepthRule` for a coded subclass and appends the depth rule. |
| **X-10 Trigger list for the revision bump** | Epics and 1.4: Settings, DocType, Custom Field, Property Setter, DocPerm, Custom DocPerm. Spine AD-11 lists only the first four. | **1.4** as written. Update the spine text. (DocPerm changes don't alter the user-independent schema, so these bumps are harmless rather than required.) |

### 2.2 Relied on by a later spec but delivered by no earlier one

- **The adapter allowlist entries** needed by 1.5, 1.6, 1.7 and 2.2 (A1). Each story adds its own names.
- **`BAD_CURSOR` and `VALIDATION` sentinels, and `PlanNode.failure`** (2.2, 2.4 "failed connection costs 0"). Covered by X-3.
- **A "planner-added source field" flag on `PlanNode`** (2.4 needs it to cost only client-selected leaves). **Owner: 1.7**, which adds the source fields.
- **The `parenttype` filter on child loads** (epics 1.7 AC, epic-1-context; missing from spec 1.7 and from AD-7). **Owner: 1.7** (R1.7-F1).
- **`can_read_doctype` applied to Link targets and children** (1.7 assumes a natural `NOT_FOUND`; without it `get_query` raises). **Owner: 1.7** (R1.7-F2).
- **Per-node failure** (2.1 per-connection `FORBIDDEN`, 2.2 `BAD_CURSOR`, 3.4 payload errors). **Owner: 1.5** (F1).
- **A random revision after a full `clear_cache`** (4.3 claims reinstall and migrate start fresh). **Owner: 1.4** (R1.4-F2 = R4.3-F2).
- **The 2.2 "Short page" row under 2.3's loop** (2.3 says the 2.2 suite "passes unchanged", which is false). **Owner: 2.2** writes the row budget-agnostic, and 2.3 lists the superseded `scanLimitReached` formula (R2.3-F1).
- **An exact Decimal sort position** (2.2 assumes `Decimal`, but Frappe's MariaDB `CONVERSION_MAP` maps NEWDECIMAL to `float`, `frappe/database/mariadb/database.py:165`). **Owner: 2.2** (R2.2-F1). Returned values stay float, which is REST parity.
- **A CI site with ERPNext setup complete** (every Sales Order fixture from 1.5 on). **Owner: 1.1** (R1.1-F4). Note: R1.1-F4's option B, `erpnext.setup.utils.before_tests`, **doesn't exist** in ERPNext v16.52.1 (no `before_tests` anywhere in `apps/erpnext`). Use the same `setup_complete` call as `post-create.sh:333-346`.

### 2.3 Delivered by two specs (pick one owner)

| Item | Delivered by | Owner |
|---|---|---|
| Import-direction checks (`core` imports nothing; `schema` and `execution` don't import `adapter`) | R1.1-F2, a 2.1 task, R4.2-F3, a 2.4 fixture | **1.1.** 2.1 and 2.4 add fixtures only. |
| Deferred, locals-free `INTERNAL` logging after the rollback | 1.2 (inline, wrong: R1.2-F1), 1.5 (`errors.py` ContextVar), 4.2 (route the catch-all) | **1.2** does it right in `api.py` (deferred, `with_context=False`, after the rollback, ContextVar reset at request start). **1.5** moves collection into `errors.py`. **4.2** adds post-processing of graphql-core errors (R4.2-F1). |
| Per-step `try/except` in the `finally` | R4.2-F2 | **1.2**, the first `finally`. 4.2 only adds the log line inside it. |
| `SET NX` before `INCR` | R1.4-F2, R4.3-F2 | **1.4.** 4.3 only fixes its verification wording (R4.3-F1). |
| The `Query` cost-formula description | 2.4 (task and AC), 4.1 (AC, "check it is present") | **2.4.** 4.1 asserts it. R4.1-F1 was written before spec 2.4 existed and is now resolved. Fix 4.1's stale text. |
| The constant query-count test over orders | 1.7 AC, 2.2 task | Per F2: **2.2.** |
| `MaxIntrospectionDepthRule` | R1.1-1.4 F1 (1.3), 2.4 | It is already in the defaults. **2.4** customizes it. |
| The admin note "clear the DocType cache after (un)mask changes" | 1.6 defers it to 4.2/4.3 | **4.3** (the README task has it). |
| Exception-map tests | R1.5-F8, 4.2 matrix | **1.5**: one row per mapping. **4.2**: the full class list, locals and finally behaviour. |
| `max_cost` field | 2.4 (with a patch) | **1.2** (F3). |

### 2.4 Signature changes later specs impose on earlier ones

The R2.1-2.4 continuity table holds and is not repeated. Add these:
- **1.2 `api.py`:** 4.1 factors a shared request helper (R4.1-F3: name it, for example `_handle(endpoint, work, parse_body)`), 4.2 adds `RequestStats` and the log line, 3.4 makes `_run` return an outcome (`is_mutation`, `all_writes_ok`), C3 blanks `form_dict`.
- **1.3 `executor.execute`:** 1.5 replaces `root_value` with `adapter`, 1.7 loads breadth-first by depth, 2.4 changes the validation rule set, 4.2 adds `stats`.
- **1.4 `schema/cache.py`:** 4.2 wants it to call `map_exception`, which breaks the import direction (R4.2-F3). It must re-raise, and `api.py` maps the error.
- **1.5 `FrappeV16Adapter(user, settings)`:** 4.2 adds `stats`.
- **Stale references:** 3.1 (2.1 input coercion "not yet written", `estimate_cost(plan)`), 4.1 (2.4 "not yet written"), 4.2 (2.3 and 2.4 "not yet written").

### 2.5 The three most important cross-spec inconsistencies

1. **There is no way to fail one plan node** (X-2, X-3, F1). 1.5 nulls the whole response on any load error. 1.7, 2.1, 2.2 and 3.4 all need per-node `COST_LIMIT`, `FORBIDDEN`, `BAD_CURSOR` and `NOT_FOUND`, the port and sentinel types don't allow it, and the 1.5 behaviour is also an existence oracle (C1).
2. **The adapter side of AD-1 is undefined** (A1). 1.1 says "allowlist" but lists nothing for `adapter/`. 1.5, 1.6, 1.7 and 2.2 each need names that are nowhere listed, while a denylist reading lets unchecked readers through. The NFR-1 gate is ambiguous from day one.
3. **Settings, limits and signatures drift across stories** (X-1, X-5). `max_cost` appears only in 2.4, with a patch that AD-1 forbids. `execute`, `plan`, `estimate_cost` and the adapter constructor change in four stories. 2.2's short-page contract is contradicted by 2.3.

---

## 3. Contradictions between reviews, settled from source

| Contradiction | Source check | Verdict |
|---|---|---|
| Does graphql-core 3.3.1's default validation include `MaxIntrospectionDepthRule`? R1.1-1.4 F1 says no. R2.1-2.4 F1 says yes. Both cite `specified_rules.py:130`. | In the 3.3.1 wheel, `graphql/validation/specified_rules.py:130` has `recommended_rules = (MaxIntrospectionDepthRule,)`, and the `specified_rules` tuple at l.137-170 **ends with `*recommended_rules` (l.169)**. `validate()` defaults to `specified_rules` (`validate.py:103-104`). | **R2.1-2.4 is right.** The rule already runs by default, so 1.3's introspection is bounded from day one. R1.1-1.4 F1's fix `(*specified_rules, *recommended_rules)` would run it twice and give duplicate errors, so don't apply it. Spec 2.4's Code Map ("only in `recommended_rules` … must be added explicitly") is wrong. Apply R2.4-F1/F2 instead (swap in a coded subclass). The rule's message is fixed and has no `extensions.code` (`max_introspection_depth_rule.py`, `MAX_LIST_DEPTH = 3`). |
| Are the graphql-core helpers public? R1.5-F9 says unverified. | `get_variable_values`, `get_argument_values` and `get_directive_values` are exported from `graphql.execution` (`__init__.py:29-31`) and from `graphql` (`__init__.py:499-501`). `Path.key: str \| int` (`pyutils/path.py:18`). | Verified. Drop the "unverified" caveat from 1.5. |
| Does 4.1's `Query` description have an owner? R4.1-F1 says nobody owns it. | Spec 2.4 now has the task (`builder.py`, `Query` description) and an AC. | Resolved: **2.4 owns it** (2.3 above). |
| Does `before_tests` make the CI site equivalent? R1.1-F4 option B. | `grep -rl before_tests ~/frappe-bench/apps/erpnext` finds nothing. | Option B is invalid. Use `setup_complete` in `ci-test.sh`. |
| Is the migrate revision "higher after than before"? 4.3 Verification versus R1.4-F2 and R4.3-F1. | `migrate.py:88` clears the cache before `after_migrate`. | The reviews agree, and the spec is wrong. The revision **differs**, and after the 1.4 fix it is random again. |

No other review pairs conflict. R1.5-F1 and R4.2-F4 are one decision (C1). R1.5-F4, 4.2 Open Question 3 and R3-3.1-5 are one decision (C2). R1.2-F2 and R4.2-F9 merge into B2.

---

## 4. Fixes needing no human decision

One line each, with the finding it implements. "After X" means the fix's exact wording depends on decision X.

### 1.1
- Add the import-direction checks and matrix rows. They take over 2.1's task (R1.1-F2, X-7 in 2.3).
- State the AST rule for dynamic access: a non-root `Name` load of an alias, `sys.modules`, `getattr`, `vars` and `__import__` on frappe, and `import frappe.x.y` counted as use (R1.1-F3).
- `ci-test.sh` runs the same `setup_complete` call as `post-create.sh`, and an AC asserts `frappe.is_setup_complete()` in CI. There is no ERPNext `before_tests` (R1.1-F4, section 3).
- Attribute the charset step to ERPNext's CI (R1.1-F5).
- Default site `${DOCWEAVE_SITE:-dev.localhost}`, and stop if the site is missing (R1.1-F6).
- Load the PR image with buildx `load: true`, accept the double build, ping Redis, and run `getent hosts` early (R1.1-F7a-d).
- The checker supports function-scoped rules (needed by 1.5's "`frappe.qb` only inside `_authorized_query`"), after A1.

### 1.2
- Log `INTERNAL` deferred, with `with_context=False`, after the rollback. Reset the ContextVar at request start (R1.2-F1, R1.5-F5).
- Give each `finally` step its own `try/except`, and report a failure as a fixed logger line (R4.2-F2, moved here).
- Add read-only negative tests: a ToDo inserted in `_run` is gone, on success and on exception (R1.2-F3).
- Mark the `frappe.throw` → `INTERNAL` row as temporary, until 1.5's map (R1.2-F4).
- Pin the 400 and 403 bodies: `{"errors":[{"message","extensions":{"code"}}]}` with no `data` (R1.2-F6).
- Split the malformed-body row, after B2 (R1.2-F2).
- Make `exposed_doctypes` a sorted tuple, and make `get_settings()` fall back to defaults (X-1).
- Add `max_cost` (and `max_connections`), after F3 and F4.

### 1.3
- Use "Foo Bar" and "Foo_Bar" as the clash fixture, and delete the DDL-committed DocTypes in `tearDownClass` (R1.3-F2).
- Copy the spine's naming algorithm word for word, and add the `BOM`, `UOM Conversion Detail` and `po_no` rows (R1.3-F3).
- The builder fails on reserved and generated type-name clashes, and Settings rejects reserved names (R1.3-F4 a, b; c after D1).
- State the standard field types: `owner: String`, `creation` and `modified: Datetime`, `modifiedBy: String`, `docstatus` and `idx: Int` (R1.3-F5).
- Name the logging channel for build diagnostics (R1.3-F7, R4.2-F7).
- Keep the default `specified_rules`. Add a negative test that deep introspection returns `VALIDATION` (it becomes `DEPTH_LIMIT` in 2.4). **Don't** apply R1.1-1.4 F1's fix (section 3).

### 1.4
- Limit the rolled-back row to changes without DDL, and add the "DDL commits; the fingerprint rebuilds" row (R1.4-F1).
- `_incr` and `bump_now` run `SET NX <random>` before `INCR`. Test that the value is above 2^32 after a delete (R1.4-F2, R4.3-F2).
- Put the site prefix in the LRU key, and size the LRU per site (R1.4-F3).
- Pin `after_commit._functions` with a test (R1.4-F4).
- When Redis is unavailable, build without caching and log once (R1.4-F5).
- `cache.py` never imports `adapter`. A build failure re-raises, and `api.py` maps it (R4.2-F3).

### 1.5
- Introduce the port shape `list[Row] | Sentinel` and a generic `Sentinel(code)`. A load failure never nulls `data` (X-2, X-3; after F1).
- Fix the final `plan`, `execute` and `FrappeV16Adapter` signatures now (X-5).
- `Row.matched_key` is an attribute. Note the spine text (X-4).
- Write the per-file adapter allowlist entries and negative fixtures (R1.5-F2, after A1).
- The session check lives in `FrappeV16Adapter.load`, or a required `user=` keyword. It raises a non-Frappe exception, and a test asserts that it maps to `INTERNAL`, never `NOT_FOUND` (R1.5-F3).
- Test the logging row through `graphql()`, not `_run` (R1.5-F5).
- `LoadRequest.fields` holds only `kind == "scalar"` fieldnames plus `name` (R1.5-F6).
- Add a parity fixture for select-only plus a share, as a C7 residual (R1.5-F7).
- Add one row per exception mapping (R1.5-F8).
- Remove the graphql-core "unverified" caveat (R1.5-F9, section 3).
- Add Stage 2 containment rows that compare the full error JSON with the missing-name case (R1.5-F1, after C1).

### 1.6
- `FORBIDDEN` wins over `MASKED` (R1.6-F2).
- Add a revocation row where a Custom DocPerm `mask` edit is removed (R1.6-F4).
- The per-request cache lives on the adapter instance, with a two-user test (R1.6-F5).
- Change the column-selection wording (X-7).
- Add the allowlist entries for `get_permitted_fields` (R1.6-F1, after A1).
- Name the fixture fields, after G1 (R1.6-F3).

### 1.7
- Add `parenttype = parent_doctype` whenever `parent_names` is given, with a Quotation and Sales Order same-name negative test (R1.7-F1). Amend the AD-7 text.
- Apply the `can_read_doctype` short-circuit to Link targets and children (R1.7-F2).
- Use one boolean term per key, emit one Row per match, and add a two-case-variants row (R1.7-F3).
- Table readability uses 1.6's permlevel set, including share level 0, with a share-only parity row (R1.7-F4).
- `keys` carries the parent names, intersected with the parents that passed (R1.7-F6, X-8).
- Add the denied-parent negative test (R1.7-F7).
- State the exact query-count numbers, after F2 (R1.7-F9).
- Flag the source fields the planner adds (2.2 in section 2).
- Specify the `max_child_rows` mechanics: `limit = remaining + 1`, nodes in path order (R1.7-F5, after F6).

### 2.1
- Add IR-walk negatives: nested `or`/`and`, `isNull` and `in: []` on masked fields (R2.1-F1).
- A user with no rights gets an empty connection, and a share-only parity row is added (R2.1-F2).
- Reword the `filter_hash` AC to Decimal versus Decimal (R2.1-F3).
- Name the `float` and `timedelta` value types and their hash tags. Note the AD-16 extension (R2.1-F4).
- State SQL three-valued semantics for `ne`, `nin` and `isNull`, with a NULL row (R2.1-F5).
- The parity test uses the same resolved order and a fixture marker (R2.1-F6).
- `isNull: false` is `Cmp(f, IS_NULL, False)`, so the spine's `FilterOp` set is unchanged.
- The import-direction task becomes fixtures only (2.3 in section 2).

### 2.2
- Exact decimal position through a `CAST(... AS CHAR)` column bound as `Decimal`, with a 17-digit tie row (R2.2-F1).
- Always select the resolved order fields, and test an unselected sort field (R2.2-F2).
- Add `PlanNode.failure`, placed by `assemble` (R2.2-F3, X-3).
- Write out all four keyset branches plus name-only, with a unit test each (R2.2-F4).
- Precedence: `VALIDATION`, then `FORBIDDEN`, then `BAD_CURSOR` (R2.2-F5).
- Build the NULL fixture with `set_value(update_modified=False)` or `bulk_insert` (R2.2-F6).
- Pad the cursor payload to a fixed size (R2.2-F7).
- Fail closed when `encryption_key` is absent (R2.2-F8).
- Interim `limit = min(first, scan_budget)` (R2.2-F9).
- Make the "Short page" row budget-agnostic (R2.3-F1).

### 2.3
- The AC lists what supersedes 2.2's formula (R2.3-F1).
- One `readable` call per node is one scan. Spy on `PermissionChecker` for budget assertions (R2.3-F2).
- Isolate the 5,000-row fixture with a marker filter (R2.3-F3).
- Correct the reference: `frappe.tests.patch_hooks` (R2.3-F4).
- Use the README residual wording (R2.3-F5, C7).
- Add the "more candidates exist" precondition (R2.3-F6).

### 2.4
- Swap `MaxIntrospectionDepthRule` for a coded subclass instead of adding it. Exactly one error (R2.4-F1).
- The subclass message names the limit of 3 (R2.4-F2).
- Remove the patch task if F3 puts `max_cost` in 1.2. Otherwise apply R2.4-F4's settings writer.
- The root field is level 1, with a concrete 8-passes and 9-fails path through `variantOfDoc` (R2.4-F5).
- A failed connection adds 0 including its subtree (R2.4-F6).
- Re-check the graphql-core claims after 1.1 installs it (R2.4-F7).
- Correct the Code Map's `specified_rules` claim (section 3).
- Note `estimate_cost(plan, settings)` in the spine (X-5).

### 3.1 (v2)
- Check write permlevels only for `permlevel > 0`, with create-only, no-create and share-write tests (R3-3.1-1).
- Add an above-permlevel child column row (R3-3.1-3).
- Map `DuplicateEntryError` to `VALIDATION`, with a row (R3-3.1-4).
- Exclude the `Read Only` fieldtype, and handle Table MultiSelect (R3-3.1-7).
- Update the stale references (R3-3.1-8).

### 3.2 (v2)
- Inherit the permlevel > 0 rule, with read-only and share-write rows (R3-3.2-1).
- Add rows for a high-permlevel child column, `null` on a mandatory field, and a child `set_only_once` column (R3-3.2-4).
- Record that `FORBIDDEN` for row names amends AD-13 and AD-15 (R3-3.2-5).
- Replace the "only `delivery_date` changes" oracle with specific assertions (R3-3.2-6).

### 3.3 (v2)
- DocWeave's own `LinkExistsError` message names no referencing document (R3-3.3-1).
- Add a write-without-submit row (R3-3.3-3, after I2).
- State that sent-but-unchanged non-`allow_on_submit` fields are refused (R3-3.3-5).
- Add an AC for the core submitted-document rule, with a `save` spy (R3-3.3-6).

### 3.4 (v2)
- Payload load errors stay in `doc` and never null `data` or change the commit (R3-3.4-2).
- Spell out the transaction-test mechanics (R3-3.4-3).
- Use a failure valid under either I4 option (R3-3.4-4).
- List the non-transactional residuals (R3-3.4-1, after I12).

### 4.1
- 2.4 owns the `Query` description. Remove the "Never" bullet's "and `Query` descriptions" and the stale Code Map text (R4.1-F1).
- Name the shared helper's shape. `sdl` ignores the body and never returns 400 (R4.1-F3).
- Give the `JSON` scalar description text (R4.1-F4).
- Reword AC 2 for the chosen body format (R4.1-F5, after B6).
- Add an Administrator-with-`allow_administrator`-off refusal row (R4.1-F2, after B5).

### 4.2
- Post-process graphql-core `ExecutionResult.errors` in `api.py` through the mapper, with a coercion `KeyError` row (R4.2-F1).
- Use a neutral probe value in the locals test (R4.2-F5).
- The invariant is "exactly one `endpoint=` line" (R4.2-F7).
- `log_error` takes a fixed one-line title and a non-empty message (R4.2-F8).
- The malformed-body row uses a wrong-shape JSON body (R4.2-F9, after B2).
- Add a production-level logger test, and no `with_more_info` (R4.2-F10).
- State the new signatures (R4.2-F11, X-5).
- Document Redis-down loss (R4.2-F13, C7).
- The `finally` hardening moves to 1.2 (R4.2-F2).
- Fix the stale 2.3 and 2.4 references.

### 4.3
- The revision after a migrate **differs** (R4.3-F1).
- Rely on 1.4 for `SET NX` (R4.3-F2).
- The manual uninstall check doesn't prove the hook (R4.3-F3).
- Catch `RedisError` in the cleanup, and test it with a `TimeoutError` patch (R4.3-F4).
- The README gives the supported range, `bench restart` and fetching the new code (R4.3-F6).
- The patch-list test handles `execute:` and `finally:`, and Settings patches go in `[post_model_sync]` (R4.3-F7).
- Resolve the repo root through `get_app_path`, and skip with a reason when a file is missing (R4.3-F8).
