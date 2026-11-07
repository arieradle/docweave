# Spec review: Stories 3.1 to 3.4 (Epic 3, v2 writes)

Reviewer: adversarial spec review, 2026-11-01. Each spec was reviewed on its own against epics.md (Epic 3 ACs), ARCHITECTURE-SPINE.md (incl. AD-9 and AD-13 [v2]), Frappe v16.53.0 / ERPNext v16.52.1 source in `~/frappe-bench`, the Ready-for-Development standard, and continuity with specs 1.1 to 1.7 and 2.1 to 2.4. No spec or planning file was edited.

Paths: `document.py` = `~/frappe-bench/apps/frappe/frappe/model/document.py`; `delete_doc.py` = `.../frappe/model/delete_doc.py`; `meta.py` = `.../frappe/model/meta.py`; `exceptions.py` = `.../frappe/exceptions.py`; `file.py` = `.../frappe/core/doctype/file/file.py`.

Verified correct (no finding): `insert()` at document.py:675 and its `check_permission("create")` at :714; `__newname` only for Prompt at :977; `validate_higher_perm_levels` at :1263; `get_permlevel_access` at meta.py:731; `validate_set_only_once` parent-only (called from `_validate` on the parent, document.py:1095, not for children :1079-1089); cancelled save "Cannot edit cancelled document" at :1401; `_validate_update_after_submit` quoting stored values at :3311-3317; `delete_doc(ignore_missing=True)` default at delete_doc.py:24-34 and the submitted refusal at :291-305; `LinkExistsError`/`UpdateAfterSubmitError` are `ValidationError` subclasses (exceptions.py:152,176); `sync_database` commits for POST (app.py:438-448); `FrappeAPITestCase` runs requests on a separate thread/connection (tests/test_api.py:41-90). ERPNext facts: SO `naming_series` is `set_only_once`; `delivery_date`, `po_no` are `allow_on_submit`; `items` is not; `ignore_pricing_rule` is permlevel 1 (Sales Manager only).

---

## Spec 3.1: Create mutations with the input contract

**Verdict: needs human decision** (four Open Questions are real and fairly framed; findings 1 and 2 also need fixes or a decision before approval).

Severity counts: High 2, Medium 4, Low 3.

AC coverage: all four epic ACs are covered (input exclusions, insert without ignore flags plus re-read payload, FORBIDDEN for above-permlevel/masked, `doc: null` + NOT_FOUND).

### 3.1-1 [High] Write-permlevel pre-check refuses permlevel-0 fields that Frappe allows, and preempts Open Question 2
- **Section:** Boundaries, Always, bullet 2 (spec-3-1:27); matrix row "No create permission" (spec-3-1:49).
- **Evidence:** The rule refuses any sent field whose permlevel is not in `meta.get_permlevel_access("write", ...)`. That function counts role DocPerms only (meta.py:731-738), so:
  (a) a role with `create` but not `write` (a valid DocPerm combination) gets `write` access at no level and every sent field is FORBIDDEN, though Frappe's `insert` only checks `create` (document.py:714) and only resets fields at permlevel **> 0** (`get_high_permlevel_fields`, document.py:1263-1274, meta.py:680-686);
  (b) a user granted write by DocShare (no role write) is refused every field, although Frappe lets them save permlevel-0 fields;
  (c) a user with no create permission at all gets field-level FORBIDDEN before Frappe raises `PermissionError`, so the matrix row "see Open Question 2" can never happen. Open Question 2 is silently decided as FORBIDDEN.
- **Fix:** Apply the permlevel check only to sent fields with `permlevel > 0` (mirroring `validate_higher_perm_levels`), and leave permlevel-0 authority to Frappe's document-level `create`/`write` check. Add negative tests: create-only role succeeds; no-create user gets the Open Question 2 code; DocShare-write user (3.2) can patch permlevel-0 fields.

### 3.1-2 [High] Link validation and fetch_from leak the existence and values of unreadable records; not raised
- **Section:** Boundaries (no rule); Open Questions (absent).
- **Evidence:** On insert, `_validate_links` (document.py:1452-1469) queries every sent Link and Dynamic Link value without a permission check. It raises `LinkValidationError("Could not find X")` or `CancelledLinkError`, so a create succeeds or fails depending on whether a record the user can't read exists, or is cancelled. A Dynamic Link lets a client probe any DocType. The same pass copies `fetch_from` values from the linked record with `frappe.db.get_value` and no permission check (document.py:3036-3055). The payload `doc` re-read then returns those values to a user who can't read the target. AD-15 says "unreadable is NOT_FOUND whether or not it exists" and AD-7 says Links are authorized on their own. The spec does not mention either path. Duplicate Prompt names and `unique` fields are a similar oracle (see 3.1-4).
- **Fix:** Add an Open Question. Options: (a) accept as Frappe REST parity and record it as a documented residual next to AD-15's `scanLimitReached` residual; (b) pre-check each sent Link/Dynamic Link target through AD-2/AD-4 and return NOT_FOUND on the field before insert. This costs one check per link and is stricter than desk. Either way, add a test that pins the chosen behaviour.

### 3.1-3 [Medium] No negative test for an above-permlevel child column, which only DocWeave guards on create
- **Section:** I/O matrix (spec-3-1:41-49).
- **Evidence:** Frappe does not reset high-permlevel child values on new documents ("If new record then don't reset the values for child table", document.py:1277-1279). DocWeave's pre-check is therefore the only guard, but the matrix tests only a *masked* child column.
- **Fix:** Add a row: a Property Setter raises a Sales Order Item column to permlevel 1; Sales User sends it in `items` → `FORBIDDEN`, `insert` not called.

### 3.1-4 [Medium] `DuplicateEntryError` maps to INTERNAL
- **Section:** Boundaries bullet 5 (spec-3-1:30); matrix "Prompt autoname" (spec-3-1:42).
- **Evidence:** `DuplicateEntryError` subclasses `NameError(Exception)`, not `ValidationError` (exceptions.py:57,108). A duplicate Prompt name, or a duplicate `field:`/`format:` autoname, therefore becomes `INTERNAL` with an Error Log entry under the 1.5/4.2 map. No matrix row covers it.
- **Fix:** Map `DuplicateEntryError` to `VALIDATION` in `adapter/errors.py` (and note it for Story 4.2's map), and add a "duplicate Prompt name" row. Record the existence-oracle aspect under 3.1-2's question.

### 3.1-5 [Medium] "Sanitized message" is undefined for write errors, and write errors can quote stored hidden values
- **Section:** Boundaries bullet 5 (spec-3-1:30).
- **Evidence:** Read-path validation messages mostly echo the caller's input. Write-path validators (Frappe and ERPNext controllers, plus `UpdateAfterSubmitError` at document.py:3311-3317) can format stored values of masked or above-permlevel fields into the message. Spec 4.2 leaves the sanitizer as an Open Question (spec-4-2:55) and only considers values "the caller sent or can see".
- **Fix:** State that Epic 3 depends on 4.2's sanitizer decision. Add to 4.2's question the option of a fixed per-class message for mutations. Add a test: a validator that raises a message containing a masked stored value, and assert the value is absent from the body.

### 3.1-6 [Medium] Nothing bounds the volume of writes
- **Section:** Boundaries bullet 6 (spec-3-1:31).
- **Evidence:** Only the payload selection is cost-checked. The number of mutation fields per request and the length of input Table lists are unbounded, though AD-10 exists to prevent unbounded requests. Frappe raises `TooManyWritesError` only at a very high write count.
- **Fix:** Add an Open Question or a rule: for example, a Settings `max_mutations` per request, and input child rows capped by `max_child_rows` (VALIDATION over the cap, before any write).

### 3.1-7 [Low] Input exclusions are incomplete
- **Section:** Boundaries bullet 1 (spec-3-1:26).
- **Evidence:** The `Read Only` *fieldtype* maps to `String` in the output map (spine:284) and is not a `read_only` property, so it would appear in input. Table MultiSelect is not mentioned; only "Table fields" are.
- **Fix:** Exclude the `Read Only` fieldtype, and state how Table MultiSelect is handled (same as Table, or excluded).

### 3.1-8 [Low] Stale continuity references
- **Section:** Code Map (spec-3-1:63,66).
- **Evidence:** It says input coercion is "from Story 2.1, spec not yet written", but spec-2-1:27,76 now defines input coercion. Spec 2.4 defines `estimate_cost(plan, settings)` (spec-2-4:77), not `estimate_cost(plan)`.
- **Fix:** Update both references.

### 3.1-9 [Low] Payload timing differs from GraphQL serial semantics without saying so
- **Section:** Tasks, planner bullet (spec-3-1:76).
- **Evidence:** "cost-check, write, then load payloads" loads every payload after every write. With `a: updateX(...) b: updateX(same doc)`, `a.doc` shows `b`'s state. The GraphQL spec resolves each serial mutation field fully before the next one starts.
- **Fix:** State the chosen semantics explicitly ("payloads reflect the state after all writes"), or interleave write and load per field.

---

## Spec 3.2: Sparse update, including child rows

**Verdict: needs human decision** (its own Open Question on lost updates, and the inherited 3.1 code question; finding 1 needs a fix).

Severity counts: High 1, Medium 3, Low 2.

AC coverage: all epic ACs are covered (sparse with masked field preserved; patch/insert/delete rows with hidden columns kept; foreign row FORBIDDEN; `set_only_once` absent).

### 3.2-1 [High] Same permlevel-0 pre-check flaw; contradicts the spec's own Open Question
- **Section:** Boundaries bullet 5 (spec-3-2:30); Open Question 1 (spec-3-2:58).
- **Evidence:** The Open Question says "`.save()` raises `PermissionError` for a user who can read but not write". With 3.1's check reused unchanged, such a user never reaches `.save()`: every sent field is FORBIDDEN first, because permlevel 0 is not in their write access. DocShare-write users are refused outright, though Frappe allows them (see 3.1-1).
- **Fix:** Inherit the fix from 3.1-1 (check only permlevel > 0). Add matrix rows: a read-only user (gets the Open Question code), and a DocShare-write user patching a permlevel-0 field (saved).

### 3.2-2 [Medium] Explicit `null` on a Table field is unspecified
- **Section:** Boundaries bullets 2-3 (spec-3-2:27-28).
- **Evidence:** `[XItemUpdateInput!]` is nullable, so `items: null` is valid GraphQL. "Explicit null sets the field to empty" combined with "a present Table field is the complete new list" could mean "delete all rows", but the spec doesn't say.
- **Fix:** Decide `null` on a Table field: same as `[]` (delete all rows, subject to Frappe's `reqd`), or `VALIDATION`. Add a matrix row.

### 3.2-3 [Medium] Shipping 3.2 before 3.3 leaks stored values through `UpdateAfterSubmitError`
- **Section:** Never bullet 1 (spec-3-2:35).
- **Evidence:** Without 3.3's pre-check, an update to a submitted document reaches `_validate_update_after_submit`, whose message includes the stored value (document.py:3311-3317), possibly masked.
- **Fix:** Either move the `docstatus` pre-check into 3.2, or state that 3.2 must not be released (or its mutations enabled) until 3.3 lands.

### 3.2-4 [Medium] Missing negative tests
- **Section:** I/O matrix (spec-3-2:41-52); Tasks (spec-3-2:75).
- **Evidence:** No row covers an above-permlevel *child* column on a patched or appended row, explicit `null` on a mandatory field (`VALIDATION`), or a `set_only_once` column in a child row (kept by design, spec-3-2:83, but untested).
- **Fix:** Add those three rows.

### 3.2-5 [Low] FORBIDDEN for row names conflicts with AD-15's wording
- **Section:** Boundaries bullet 4 (spec-3-2:29).
- **Evidence:** AD-15 (spine:250) reserves FORBIDDEN "for fields and filters". The epic AC requires FORBIDDEN for foreign rows, and unknown rows giving the same code avoids an oracle, but the spine conflict isn't raised.
- **Fix:** Add it to Design Notes as a required AD-13/AD-15 amendment.

### 3.2-6 [Low] The "only `delivery_date` changes" oracle is untestable as worded
- **Section:** matrix "Sparse" (spec-3-2:42).
- **Evidence:** ERPNext `SalesOrder.validate` recomputes totals, `modified` and so on during every save.
- **Fix:** Assert specific things instead: the masked and above-permlevel stored values are unchanged, and no other client-sendable field differs except `delivery_date`.

---

## Spec 3.3: Delete and submitted documents

**Verdict: needs human decision** (three Open Questions, all real; findings 1 and 2 need decisions too).

Severity counts: High 1, Medium 3, Low 2.

AC coverage: all epic ACs are covered. Cancelled delete is correctly raised as an Open Question, since the epic and Frappe disagree.

### 3.3-1 [High] `LinkExistsError` discloses the name of an unreadable referencing document
- **Section:** Boundaries bullet 2 (spec-3-3:27); matrix "Linked draft" (spec-3-3:44).
- **Evidence:** `raise_link_exists_exception` formats the *referencing* document's DocType and name into the message: "Cannot delete or cancel because Sales Order X is linked with Sales Invoice SINV-0001" (delete_doc.py:487-500, called from :387-394). The user may not be able to read SINV-0001. The spec maps it to `VALIDATION` with Frappe's "sanitized" message, and the sanitizer is still undecided (spec-4-2:55). This is an existence disclosure on a refusal.
- **Fix:** For `LinkExistsError`, have DocWeave return its own message that names neither the referencing document nor its DocType (for example "linked records exist"), or name only DocTypes the user can read. Add a test asserting the referencing name is absent from the body.

### 3.3-2 [Medium] "Sending a Table field that isn't `allow_on_submit` is VALIDATION" is stricter than Frappe and the AC; decided silently
- **Section:** Boundaries bullet 4 (spec-3-3:29).
- **Evidence:** For a non-`allow_on_submit` table, Frappe only checks that the row count is unchanged, then checks each column's own `allow_on_submit` (document.py:3293-3299, :1420-1425). Sales Order Item has `allow_on_submit` columns (`delivery_date`, `cost_center`, `project`, `supplier`, `reserve_stock`) inside the non-`allow_on_submit` `items` table. The epic AC says "only `allow_on_submit` fields may change", which these columns are. The spec blocks them without raising it.
- **Fix:** Add an Open Question. Options: (a) follow Frappe: allow patching `allow_on_submit` child columns by row `name` with no rows added or removed; (b) keep the stricter rule and amend the AC. Removing rows from an `allow_on_submit` table (Frappe allows it) is also unspecified; state it.

### 3.3-3 [Medium] Update-after-submit needs `submit` permission; not covered
- **Section:** matrix (spec-3-3:46); Open Questions.
- **Evidence:** A save on a submitted document runs `check_permission("submit")` (document.py:1388-1390), on top of `write`. A user with write but not submit gets `PermissionError`, which becomes `NOT_FOUND` under AD-15 although the document is readable.
- **Fix:** Add a matrix row and tie it to 3.1's "Code for a refused write" question.

### 3.3-4 [Medium] Delete has side effects that rollback can't undo
- **Section:** Boundaries (none); relevant to 3.4.
- **Evidence:** `delete_doc` → `remove_all` → `File.on_trash` → `_delete_file_on_disk` removes attachment files from disk immediately (file_manager.py:248-254, file.py:255-261, :627-640). If the transaction then rolls back (a later mutation fails in 3.4, or a test rolls back), the File rows come back but their files are gone. Under tests, `delete_dynamic_links` also runs immediately (`now=frappe.in_test`, delete_doc.py:204-210).
- **Fix:** Raise as an Open Question. Options: refuse deleting documents with attachments in multi-mutation requests; accept and document the residual next to AD-12's "hooks that commit"; or require delete to be the only mutation in a request.

### 3.3-5 [Low] The "sent field" rule refuses unchanged values that Frappe accepts
- **Section:** Boundaries bullet 4 (spec-3-3:29).
- **Evidence:** Frappe compares values (document.py:3293-3310). A client that round-trips a read document unchanged gets `VALIDATION` from DocWeave.
- **Fix:** State this explicitly as intended behaviour. Comparing against the stored value is only safe for readable, unmasked fields, and masked ones are already FORBIDDEN earlier.

### 3.3-6 [Low] No Acceptance Criterion covers the core submitted-document rule
- **Section:** Acceptance Criteria 1 (spec-3-3:79).
- **Evidence:** The AC is consistent with the check order (FORBIDDEN before `docstatus`), but no AC covers the core rule: a non-masked, non-`allow_on_submit` field on a submitted document gives `VALIDATION` and the message lacks the stored value. Only the matrix covers it.
- **Fix:** Add that Given/When/Then, with a spy proving `save` isn't called.

---

## Spec 3.4: All-or-nothing mutation requests

**Verdict: needs human decision** (Open Questions 1 and 2 are real and fair; findings 1 and 2 need fixes).

Severity counts: Medium 2, Low 2.

AC coverage: both epic ACs are covered. "Frappe commits once" versus "transport owns the transaction" is correctly raised as Open Question 1. "Null with their errors" for rolled-back mutations is correctly raised as Open Question 2.

### 3.4-1 [Medium] The all-or-nothing guarantee is overstated; non-transactional effects aren't documented
- **Section:** Never bullet 2 (spec-3-4:35).
- **Evidence:** Only explicitly committing hooks are listed. Other effects also survive a rollback:
  - attachment files deleted from disk by a delete (3.3-4);
  - MariaDB implicit commits from DDL, if a DocType whose insert runs DDL (DocType, Custom Field, Property Setter) is exposed;
  - Redis cache clears.
- **Fix:** List these residuals in the spec and the admin docs. Consider whether DocWeave Settings validation should refuse exposing DDL-triggering DocTypes for writes (relates to 3.1's "Which DocTypes get mutations" question).

### 3.4-2 [Medium] Payload-load failures after successful writes can wipe the committed names
- **Section:** Boundaries bullet 3 (spec-3-4:28).
- **Evidence:** Spec 1.5 makes a `DocWeaveError` during load return `{"data": null, "errors": [...]}` for the whole response (spec-1-5, Tasks, executor bullet). 3.4 handles only a `NOT_FOUND` payload. A payload load can also fail with `INTERNAL`, or with runtime `COST_LIMIT` from `max_child_rows` (AD-7, enforced at load, not by `estimate_cost`). The writes are then committed but the client gets `data: null` and loses every `name`. Whether such a request commits is also unspecified.
- **Fix:** State that payload load errors are confined to `doc` (`null` + code) per mutation field, never null `data`, and never affect the commit decision. Add matrix rows for an `INTERNAL` and a `COST_LIMIT` payload.

### 3.4-3 [Low] Transaction-test mechanics are underspecified
- **Section:** Tasks bullet 4 (spec-3-4:72); Code Map (spec-3-4:63).
- **Evidence:** The HTTP request runs on another connection, so fixtures (users, customers) must be committed first, or the request won't see them. The test's own connection runs under MariaDB's default REPEATABLE READ, so it must end its transaction before reading. Otherwise it keeps its old snapshot and misses the request's commit. The matrix says "fresh connection" but the task says "querying as Administrator after the response".
- **Fix:** Spell out: commit fixtures in `setUp`, `frappe.db.rollback()` (or use a new connection) before verifying, and delete committed rows in `tearDown`.

### 3.4-4 [Low] The "Second fails" scenario depends on 3.1's Required-fields Open Question
- **Section:** matrix row 1 (spec-3-4:41).
- **Evidence:** If 3.1 makes `reqd` fields non-null in the input, a missing `customer` becomes a GraphQL validation error and no write runs at all.
- **Fix:** Use a failure that is a Frappe `ValidationError` under either option, such as a negative `qty` or an invalid Link.

---

## Cross-cutting summary

1. **The write-permlevel pre-check (3.1, reused by 3.2/3.3) treats permlevel 0 like a high permlevel.** It refuses create-only and DocShare-write users and silently decides the "Code for a refused write" question. Restrict it to permlevel > 0, as Frappe does.
2. **Write-path errors leak data about unreadable records:** `LinkExistsError` names referencing documents, Link validation and `fetch_from` are existence and value oracles, and validators can quote stored values. AD-15 forbids this and no spec raises it. This needs a human decision and a defined sanitizer (shared with 4.2).
3. **All-or-nothing has holes:** delete removes attachment files immediately, DDL commits implicitly, and payload-load errors can null the whole response after a commit.
