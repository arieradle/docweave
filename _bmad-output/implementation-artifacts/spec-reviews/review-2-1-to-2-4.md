# Spec review: Stories 2.1, 2.2, 2.3, 2.4

**Reviewer:** independent adversarial review · **Date:** 2026-11-01 · **Baseline:** `cd5c126`
**Inputs:** the four specs, specs 1.1–1.7 for continuity, `epics.md` §2.1–2.4, `epic-2-context.md`, `ARCHITECTURE-SPINE.md`, spikes 0.1–0.3, Frappe v16.53.0 (`~/frappe-bench/apps/frappe`, `git describe` = `v16.53.0`), ERPNext under `~/frappe-bench/apps/erpnext`, `cryptography` 50.0.2 in `~/frappe-bench/env`.
**graphql-core:** not installed in `~/frappe-bench/env`. Claims were checked against the graphql-core 3.3.1 wheel fetched with `pip download --no-deps` and unpacked outside the repo. That is the release `~=3.3.0` resolves to today, but it is not the env that will run, so treat those checks as **verified against 3.3.1 source, not against the installed env**.

Severity scale: **High** = a leak of data, masked values or existence, or a defect that blocks a correct implementation (contradiction, false premise that breaks an AC). **Medium** = a missing or wrong contract that an implementer would have to decide silently, or a missing negative test for a leak path. **Low** = clarification or test gap.

## Summary

| Spec | Verdict | High | Medium | Low |
|---|---|---|---|---|
| 2.1 Typed filters and ordering | **needs human decision** (its Open Questions, and 1.7's), then fixes | 0 | 2 | 6 |
| 2.2 Keyset connections with encrypted cursors | **needs fixes** (blocked on 1.7's Open Questions) | 1 | 2 | 6 |
| 2.3 Scan budget and short pages | **needs fixes** | 1 | 2 | 3 |
| 2.4 Depth and cost limits | **needs human decision** (`max_cost` default, plus F3), then fixes | 0 | 4 | 3 |

The specs follow the spine closely. AD-6, AD-8 and AD-10 are carried over almost word for word, and the cursor binding, TTL, HKDF info string and NULL ordering are right. The defects are where the specs assume something about Frappe or graphql-core that the source contradicts (DECIMAL columns come back as `float`, and `MaxIntrospectionDepthRule` is already in `specified_rules`), plus one contradiction between 2.2 and 2.3.

---

## Spec 2.1: Typed filters and ordering

**Verdict: needs human decision.** The two Open Questions (whether a forbidden filter rejects the request or only the connection, and Geolocation) are real intent gaps with fair options. The first one is also decided provisionally in the frozen section ("as written above"), but it is flagged, so nothing is decided silently. The spec also depends on 1.7's failed-node question.

**AC coverage:** AC1 (`FilterIR`, and only the adapter translates it) is covered by the AC at l.86 and the spy task at l.79. AC2 (`filter_hash` equivalence) is covered at l.85 and l.80. AC3 (default order) is covered at l.26 and the matrix row at l.43. AC4 (`FORBIDDEN` before any query) is covered at l.29 and the rows at l.47–48, with the request-versus-connection scope left to the Open Question.

**Verified:** `apply_filters` passes a `Criterion` straight to `.where()` (`frappe/database/query.py:431-433`). `FilterValue = str | int | bool` (`database/utils.py:16`), so a `Criterion` isn't caught by the earlier branch. `if order_by:` (`query.py:333`) applies no ORDER BY when `order_by` is None. Permission conditions are ANDed through a separate `.where()` (`query.py:1620-1621`), and the share OR is inside that criterion (`query.py:1679-1683`), so a client `or` can't escape the permission conditions. The spec's Design Note is right that a `Criterion` filter skips Frappe's above-permlevel filter check, which makes AD-6 the only guard.

### F1. Medium: no negative test proves AD-6 walks the whole IR

- **Section:** Always, AD-6 bullet (l.29); matrix rows l.47–48.
- **Evidence:** The matrix only tests a masked or above-permlevel field as a top-level key. An implementation that checks only the top-level keys of `<Type>Filter`, or only the operators it expects, would pass every listed test. It would still leak hidden values through `or: [{maskedField: {eq: X}}]`, `and: [{and: [...]}]` or `maskedField: {isNull: false}`. AD-6 (spine l.118-119) names equality, range, null and sort as the oracles.
- **Fix:** Add matrix rows that each expect `FORBIDDEN` and no `_authorized_query` call: a masked field nested two levels down inside `or`, an above-permlevel field inside `and`, `isNull` on a masked field, and `in: []` on a masked field (an empty set must still be rejected, not short-circuited to "matches none" before the check). State that the check walks the IR after it is built and before any short-circuiting.

### F2. Medium: the access rule for a user with no permission at all is missing for lists

- **Section:** Always l.31; matrix l.51.
- **Evidence:** Only `select` without `read` is specified. A user with neither right (and no shares) makes `get_query` raise `PermissionError` (`query.py:1655-1660`, `check_select_permission` at l.1432). 1.5 maps that error to `NOT_FOUND`, so the connection would be `null` + `NOT_FOUND`, a different shape from select-only's empty connection. A share-only user passes `can_read_doctype`, because a DocType-level `has_permission` is true when at least one document is shared (`frappe/permissions.py:197-201`). That case is fine, but it needs a test.
- **Fix:** State that a user without DocType-level `read` (select-only or no rights) gets the empty connection without a query. That gives one shape, the one AD-4 prescribes for select-only. Add matrix rows for "no rights" (empty, no query) and "share-only user" (gets exactly the shared documents, matching parity).

### F3. Low: the `filter_hash` AC contradicts itself

- **Section:** AC l.85.
- **Evidence:** The AC says "`1.0` against `1` … identical" and also "changing one … value type changes the hash". If `1` is an Int and `1.0` a Float or Decimal, the two clauses conflict.
- **Fix:** Say "a Decimal `1.0` against a Decimal `1` (normalized)". A different scalar type for the same field can't happen after coercion.

### F4. Low: the Python value types for `TimeOps` and `FloatOps` are unspecified

- **Section:** Always l.25 and l.27; Tasks l.74.
- **Evidence:** AD-16 (spine l.264) lists `Decimal, date, datetime, str, int, bool`, with no `float` and no time type. The spec adds `FloatOps` and `TimeOps` but doesn't say what Python value they produce. MariaDB returns TIME as `timedelta` (2.2 l.72). `filter_hash` needs a type tag for each.
- **Fix:** Name the types (for example `float`, and `datetime.time` converted to `timedelta` when binding), add both to the `filter_hash` type tags, and record the AD-16 extension in the Spec Change Log.

### F5. Low: the NULL semantics of `ne`, `nin` and `isNull` differ from Frappe's and aren't stated

- **Section:** Always l.27.
- **Evidence:** SQL `f != 'x'` excludes NULL rows, and `IS NULL` doesn't match `''`. Frappe's own filters wrap these in `ifnull(...)`, so DocWeave filters will select different rows from Frappe REST filters. This isn't a leak, but integrators will notice.
- **Fix:** Add one sentence fixing the SQL three-valued semantics (and that `isNull` means SQL NULL only), with a matrix row for `ne` over a row whose value is NULL.

### F6. Low: the parity test needs a deterministic order and isolation

- **Section:** Tasks l.81.
- **Evidence:** Sales Order's `sort_field` is `creation DESC` with no tie-break (`sales_order.json:1850-1851`). Comparing "the first `max_page_size` rows" against `get_list` without an explicit `order_by="creation desc, name desc"` can differ at the 100th row. Other Sales Orders on `dev.localhost` also enter both sides.
- **Fix:** Pass the same resolved order and a fixture marker filter on both sides.

### F7. Low: the non-filterable list is ambiguous for some fieldtypes

- **Section:** Always l.25.
- **Evidence:** "Table" doesn't say whether it includes Table MultiSelect. HTML Editor is a `String` (spine l.284) and isn't listed, while Text Editor and Markdown Editor are.
- **Fix:** List Table MultiSelect explicitly, and decide HTML Editor the same way as Text Editor. That decision extends the spine list, so note it next to the Geolocation question.

### F8. Low: no limit on IR size

- **Section:** Always l.25–27.
- **Evidence:** `in` tuples and `and`/`or` breadth are unbounded, and 2.4's cost counts only selected leaves, so a client can send a huge SQL predicate at cost 1.
- **Fix:** Cap the number of IR nodes plus `in` values per connection (for example at 1,000, giving `VALIDATION`), or record that the gap is accepted.

---

## Spec 2.2: Keyset connections with encrypted cursors

**Verdict: needs fixes.** Its Open Questions only defer to 1.7's. Every epics AC is covered: shape (l.44), opacity (l.45), replay, binding, expiry and tampering (l.46–49), ties and NULLs (l.50–51), and `first` over the maximum (l.53).

**Verified:** `get_encryption_key()` is at `frappe/utils/password.py:223`. `Fernet.decrypt(token, ttl)` is at `cryptography/fernet.py:86` and `encrypt_at_time` at l.60 (50.0.2). HKDF with `length=32` → `urlsafe_b64encode` gives a valid Fernet key. MariaDB sorts NULL lowest, so NULLs come first in ASC and last in DESC. The `name` tie-break is unique under `utf8mb4_unicode_ci`, because `name` is the primary key under the same collation, so SQL-side comparison stays consistent with ORDER BY.

### F1. High: Currency, Float and Percent sort values come back as `float`, not `Decimal`, so ties at high precision are skipped

- **Section:** Always l.26 ("position … type-tagged (`Decimal`, …)"), l.28 ("no Python-side comparison"); matrix l.50.
- **Evidence:** Frappe's MariaDB connection converts every DECIMAL column to Python `float`: `CONVERSION_MAP = conversions | {FIELD_TYPE.NEWDECIMAL: float}` (`frappe/database/mariadb/database.py:165-166`, also `mysqlclient.py:195-196`). Currency, Float and Duration are `decimal(21,9)` and Rating is `decimal(3,2)` (`database.py:176,179,197,205`). A `decimal(21,9)` holds up to 21 significant digits and a double holds about 15–17. The position written to the cursor is therefore a rounded value. The keyset branch `f = v AND name > n` is then false for the whole tie group, and `f > v` can skip rows whose true value lies between the stored and the rounded value. The result is rows silently skipped or repeated, which breaks the epics AC "every row appears exactly once". The spec's `Decimal` type tag never occurs in practice. The same applies to Stage 1 values in general, though 1.3 already coerces output through `Decimal(repr(v))`.
- **Fix:** For decimal-backed sort fields, select the sort column a second time as an exact string (for example pypika `Cast(field, "CHAR")` aliased `_dw_pos`, a name Frappe's masking ignores because it matches by key) and encode the position from that as `Decimal`. Bind the keyset parameter as `Decimal`, which pymysql renders as an exact literal. Add a matrix row: ties on `grand_total = 123456789012.123456789` (and on a 17-digit fraction) across a page boundary, ASC and DESC, with each row exactly once.

### F2. Medium: the sort column must be selected for the position, and this isn't stated

- **Section:** Always l.26 and l.29; Tasks l.79.
- **Evidence:** 1.6 queries "only the [readable selected fields] plus `name`" (spec-1-6, Tasks, `frappe_v16.py` bullet). If the client sorts by `transactionDate` but doesn't select it, the row has no sort value to encode. The spec never says to add the order field to `fields`, or that the position is read from the raw query row and not from the sentinel-bearing `Row`.
- **Fix:** Add the following to the `frappe_v16.py` task: "`_authorized_query` always selects the resolved order fields. The position is read from the raw result, before `Row` building, and these extra fields don't appear in the `Row` unless the client selected them." Add a test that sorts by an unselected field across two pages.

### F3. Medium: no task defines the per-connection failure mechanics

- **Section:** Always l.25 and l.33; Tasks l.78–81; Open Question l.62.
- **Evidence:** 1.5 defines only the sentinels `MASKED`, `FORBIDDEN` and `NOT_FOUND` (spec-1-5 Tasks), and 1.7 adds `COST_LIMIT`. 2.2 needs `BAD_CURSOR` and `VALIDATION` sentinels, but no task adds them to `core/types.py`. `first` out of range is raised by the planner "before any adapter call", so 1.7's port `Sentinel` option doesn't cover it. Nothing says how a plan node carries a planner-side failure into `graph.py`. 2.4 relies on this too ("a connection already failed with `VALIDATION` adds 0", spec-2-4 l.31).
- **Fix:** In Tasks, add `core/types.py` sentinels `BAD_CURSOR` and `VALIDATION`, and `PlanNode.failure: Sentinel | None`. Failed nodes are excluded from `load` and placed by `graph.assemble` at their response key.

### F4. Low: only one of the four keyset branches is written out

- **Section:** Always l.28.
- **Fix:** Write out all four cases plus the case where order is `name` alone:
  - ASC after `v`: `f > v OR (f = v AND name > n)`
  - ASC after NULL: `(f IS NULL AND name > n) OR f IS NOT NULL`
  - DESC after `v`: `f < v OR (f = v AND name < n) OR f IS NULL`
  - DESC after NULL: `f IS NULL AND name < n`
  - Order by `name` only: `name > n` / `name < n`

  Add a unit test per branch on the generated SQL.

### F5. Low: precedence between `VALIDATION`, `FORBIDDEN` and `BAD_CURSOR` on one connection is undefined

- **Fix:** Fix the order: planner `VALIDATION` → AD-6 `FORBIDDEN` → `BAD_CURSOR`. Add a test where one connection has both a masked filter and a tampered cursor.

### F6. Low: the NULLs fixture can't be built through the document API

- **Evidence:** `validate_delivery_date` copies the latest item date into the header (`erpnext/selling/doctype/sales_order/sales_order.py:426-437`), so `delivery_date` is rarely NULL on saved orders.
- **Fix:** Have the test null it with `frappe.db.set_value(..., update_modified=False)` or create the orders with `bulk_insert`.

### F7. Low: ciphertext length reveals the length of a hidden row's name and sort value

- **Section:** Matrix l.45 ("Opaque").
- **Evidence:** Fernet doesn't hide plaintext length (to within 16 bytes). When the budget is spent, `endCursor` can be the position of a hook-rejected row.
- **Fix:** Pad the JSON payload to a fixed size (for example 512 bytes) before encryption, and test that two cursors with different name lengths have equal token lengths.

### F8. Low: `get_encryption_key()` writes to site config when the key is missing

- **Evidence:** `password.py:224-229` calls `update_site_config` if `encryption_key` is absent, which is a write on a read path.
- **Fix:** Note that the key always exists on installed sites, or have `cursor.py` fail closed (`INTERNAL`) if `"encryption_key"` isn't in `frappe.local.conf`. That would need one more allowlisted name.

### F9. Low: two interim edge cases

- **Allowlist dependency:** the boundary task (l.84) assumes `adapter/cursor.py` may use `frappe.utils.password.get_encryption_key` and `frappe.session.user`. That depends on the per-file adapter allowlist raised in review 1.5–1.7, F2. List the names explicitly.
- **Budget cap:** the interim one-chunk scan exceeds the scan budget if an admin sets `scan_budget < max_page_size`. Use `limit=min(first, scan_budget)`.

---

## Spec 2.3: Scan budget and short pages

**Verdict: needs fixes.** Every epics AC is covered: 7-of-5,000 (l.44, AC l.80), budget spent (l.45), aliases (l.47), exhausted (l.48) and default 200 (l.46). The precedence rules match AD-8, and the 51-request bound in the AC is correct arithmetic: 50 budget-limited requests plus one that confirms exhaustion.

### F1. High: "the 2.2 pagination suite passes unchanged" is false

- **Section:** AC l.81, against 2.2's matrix row "Short page" (spec-2-2 l.55) and 2.2's `scanLimitReached` rule (spec-2-2 l.32).
- **Evidence:** In 2.2's row, 20 candidates with 5 readable at `first: 20` give `scanLimitReached: true`, `hasNextPage: true` and `endCursor` = the 20th candidate. Under 2.3 at the default budget of 200, the loop fetches a chunk of `min(200, 100) = 100`, gets 20 rows (fewer than requested) and checks them all. Precedence rule 1 applies: `hasNextPage: false`, `endCursor: null`, `scanLimitReached: false` (l.28). If more candidates exist, the loop keeps scanning instead. Either way 2.2's expected output can't occur. 2.2's formula "`scanLimitReached` = `hasNextPage` and fewer than `first` edges" is also replaced by "budget spent". An implementer has to break either the AC or the precedence rule.
- **Fix:** Change the AC to "the 2.2 suite passes, except the Short page row and the `scanLimitReached` formula, which this story supersedes", and list the replacement expectation for that row. Alternatively, write the row in 2.2 as budget-agnostic, for example by asserting only "5 edges, each exactly once over the walk".

### F2. Medium: budget accounting with the shared per-request cache is undefined

- **Section:** Always l.25 and l.32; Tasks l.70; matrix l.47.
- **Evidence:** 1.5's `PermissionChecker` caches per request across nodes. When alias `b` scans names that alias `a` already checked, it's unclear whether the cache hits count against `b`'s budget. The test may spy on `PermissionChecker` or on `frappe.get_doc` (l.70), and the two give different counts. "Check counts are counted per alias" (l.47) can't be asserted with a `get_doc` spy.
- **Fix:** Define each `readable((name,))` call made by a node as one scan for that node, cached or not. That keeps pages deterministic and independent of sibling aliases, as AD-8 requires. Spy on `PermissionChecker.readable` per node for budget assertions, and on `get_doc` only for the "checked once per request" dedupe assertion.

### F3. Medium: the 5,000-row fixture isn't isolated from other Sales Orders on the site

- **Section:** Tasks l.70; AC l.80; matrix l.44 and l.46.
- **Evidence:** `dev.localhost` and the CI site hold other Sales Orders (from earlier test classes and ERPNext fixtures). "Each of the 5,000 checked exactly once", "exactly 200 checks … of 5,000" and "at most `ceil(5000/100)+1` requests" all assume Stage 1 returns exactly the fixture.
- **Fix:** Give the bulk-inserted rows a marker (for example a unique `po_no` per run). Walk with `filter: {poNo: {eq: marker}}`, and have the hook deny everything outside the 7.

### F4. Low: the `patch_hooks` reference is wrong

- **Section:** Code Map l.63.
- **Evidence:** It is `frappe.tests.patch_hooks` (`frappe/tests/classes/context_managers.py:61`, exported at l.271), not a method of `IntegrationTestCase`.

### F5. Low: the documented residual is narrower than the actual disclosure

- **Section:** Always l.34.
- **Evidence:** A page that fills on the last readable row and is followed by hook-rejected candidates gives `hasNextPage: true` and then an empty final page. That reveals the same thing as `scanLimitReached`. 2.1 and 2.2's interim `hasNextPage` rules reveal it too.
- **Fix:** Word the README line as "`scanLimitReached` and a `hasNextPage: true` followed by an empty page can reveal…".

### F6. Low: the "Fills on the last check" row needs a precondition

- **Section:** Matrix l.49.
- **Evidence:** If the check that fills the page is the last row of a short chunk, rule 1 (exhausted) wins and `hasNextPage` is false.
- **Fix:** State that more candidates exist after that row.

---

## Spec 2.4: Depth and cost limits

**Verdict: needs human decision.** The `max_cost` default (Open Question l.62) is a real gap with fair options, and the 51,000 arithmetic is correct. F3 needs a decision too. Every epics AC is covered: introspection (l.45, AC l.84), depth breach (l.47, AC l.86) and cost breach before any adapter call (l.55, AC l.86). The cost-math row (l.50, 1,030) is correct.

### F1. Medium: false premise, because `MaxIntrospectionDepthRule` is already in `specified_rules`

- **Section:** Code Map l.70; Always l.26.
- **Evidence:** In graphql-core 3.3.1, `recommended_rules = (MaxIntrospectionDepthRule,)` (`graphql/validation/specified_rules.py:130`), and `specified_rules` ends with `*recommended_rules` (l.137–169). Following the spec ("must be added explicitly") runs the rule twice and gives duplicate errors. The rule also sets no `extensions.code`. Keeping "a code already set by a rule" (Code Map l.65) therefore can't turn its error into `DEPTH_LIMIT`.
- **Fix:** Build the rule tuple as `specified_rules` with `MaxIntrospectionDepthRule` swapped for a DocWeave subclass that reports with `extensions={"code": "DEPTH_LIMIT"}`, then append the depth rule. Add a test that the deep-introspection query yields exactly one error.

### F2. Medium: the AC "message contains the limit's number" fails for introspection breaches

- **Section:** AC l.86; matrix l.46; AD-10 (spine l.184: "the message names the limit and the value").
- **Evidence:** The rule's message is the fixed "Maximum introspection depth exceeded" (rule docstring, `max_introspection_depth_rule.py`), with `MAX_LIST_DEPTH = 3` and no number in the message.
- **Fix:** Have the subclass from F1 emit "Introspection list depth exceeds the limit of 3". Alternatively, limit the AC to the custom depth rule and record the exception.

### F3. Medium (needs human decision): cost doesn't bound AD-4 work, so a cheap request can run thousands of `get_doc` calls

- **Section:** Always l.27–31; 2.3 l.24 and l.37 (no cross-connection cap).
- **Evidence:** The budget is per connection occurrence, and cost counts only selected leaves. A request with 100 aliases of `salesOrderList(first:1){edges{node{name}}}` has a cost of 100 but may make 100 × 200 = 20,000 permission checks. At Spike 0.2's measured ~1.9 s p95 per 200 checks, that is about 3 minutes of worker time in one request, under a depth of 3. The spine defers `max_total_candidates` to v2, but neither 2.3 nor 2.4 raises the resulting v1 exposure.
- **Proposed Open Question:** (a) Each connection adds `scan_budget` (or `scan_budget × k`) to the cost estimate, so many cheap aliases hit `COST_LIMIT`. This is simple and stays inside AD-10's single estimate, but the published formula changes. (b) Add a per-request cap on root connections, a new Setting. (c) Accept it for v1 and document it next to rate limiting, which the spine defers to Frappe.

### F4. Medium: the patch module falls inside the AD-1 checker scope

- **Section:** Tasks l.76.
- **Evidence:** 1.1 scopes the checker to "every `docweave/**/*.py` except `docweave/tests/`" (spec-1-1 Design Notes). A patch that sets a Single value needs `frappe.db.set_single_value` or `frappe.get_single`, and neither is allowlisted outside `adapter/settings.py`. 1.2's Open Question covers only `docweave/docweave/doctype/**`. The patch itself is needed. Saved Singles load from `tabSingles` without meta defaults (`frappe/model/document.py:496-504`), and `_fix_numeric_types` would turn a missing Int into 0, so every request would fail `COST_LIMIT`.
- **Fix:** Put the write in `adapter/settings.py` (`ensure_limit_defaults()`), and make the patch a one-line call to it. Also make `get_settings()` fall back to the default when the stored value is below 1. Extend the allowlist for `patches/` by name, or fold it into 1.2's Open Question.

### F5. Low: the depth origin and the "too deep" fixture are vague

- **Section:** Always l.24; matrix l.47 and l.49.
- **Fix:** State that the root field counts as level 1. Give the concrete 9-level path, for example `salesOrderList{edges{node{items{itemCodeDoc{variantOfDoc{variantOfDoc{…}}}}}}}` (Item's `variant_of` is a Link to Item, which allows arbitrary depth). Add 8-passes and 9-fails cases on the same path.

### F6. Low: a failed connection's subtree cost is unspecified

- **Section:** l.31.
- **Fix:** Say "a connection already failed with `VALIDATION` adds 0, including its subtree".

### F7. Low: the graphql-core claims rest on a downloaded wheel

- **Evidence:** The `validate(schema, document_ast, rules, max_errors, hide_suggestions)` signature (`validation/validate.py:41-47`) and the `coerce_input_value` and `coerce_input_literal` hooks (`type/definition.py:504-506`) were checked against the 3.3.1 wheel, not an installed env.
- **Fix:** Re-check once 1.1 installs `graphql-core~=3.3.0` into the bench env.

---

## Continuity: signature changes these specs impose on Epic 1

| Epic 1 item | Change | From |
|---|---|---|
| `execution.planner.plan(schema, document, operation_name, variables)` (1.5) | gains `settings: SettingsView` | 2.1 |
| `execution.executor.execute(schema, request, adapter)` (1.5) | gains `settings`; validation runs a custom rule list and keeps rule-set codes (1.3 stamped `VALIDATION` on everything) | 2.1, 2.4 |
| `core.port.DataAdapter.load` (1.5: `Sequence[list[Row]]`) | `Sequence[Page \| list[Row] (\| Sentinel)]` | 2.1 (+1.7 Open Question) |
| `core/types.py` (1.2, 1.5) | adds `FilterOp`, `And`, `Or`, `Cmp`, `Direction`, `OrderKey`, `Page`; needs `BAD_CURSOR`/`VALIDATION` sentinels (2.2 F3); `SettingsView.max_cost` | 2.1, 2.2, 2.4 |
| `adapter.frappe_v16._authorized_query` (1.5) | `filter`, `order`, `after` unlocked; type-guarded (`TypeError`); must also select the order fields (2.2 F2) | 2.1, 2.2 |
| `schema/scalars.py` (1.3, output only) | input coercion added | 2.1 |
| `schema/builder.py` tags (1.3) | new `{"kind": "root_connection", "doctype"}`; input tags `{"fieldname"}`; `Query` description | 2.1, 2.4 |
| `PlanNode` (1.5, 1.7) | `first`/`after`/filter/order in the fingerprint; needs a failure slot (2.2 F3) and a "planner-added" flag (2.4) | 2.1, 2.2, 2.4 |
| DocWeave Settings (1.2) | new Int `max_cost` + patch | 2.4 |
| `test_boundaries.py` (1.1) | import-direction check (2.1); cursor-module names (2.2); `patches/` scope (2.4 F4) | 2.1, 2.2, 2.4 |

The names are otherwise consistent across the specs (`readable_fields`, `masked_fields`, `PermissionChecker.readable`, `LoadKind.ROOT_CONNECTION`, `SettingsView.scan_budget` and `max_page_size`). Nothing relies on an undelivered Epic 1 item, apart from the 1.7 Open Questions the specs already cite and the adapter allowlist from review 1.5–1.7, F2.
