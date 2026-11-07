# Spec review: Stories 1.5, 1.6, 1.7

**Reviewer:** independent adversarial review · **Date:** 2026-11-01 · **Baseline:** `cd5c126`
**Inputs:** the three specs, specs 1.1–1.4 for continuity, `epics.md` §1.5–1.7, `ARCHITECTURE-SPINE.md`, spikes 0.1–0.3, Frappe v16.53.0 and ERPNext v16.52.1 source under `~/frappe-bench/apps`.
**graphql-core:** not installed in `~/frappe-bench/env` (no `graphql*` package in site-packages). Every graphql-core claim below is **unverified** against source.

Severity scale: **High** = permission-safety gap (leak of data, masked values or existence) or a defect that blocks a correct implementation. **Medium** = wrong or missing contract that an implementer would have to decide silently, or a parity bug. **Low** = test gap or clarification.

## Summary

| Spec | Verdict | High | Medium | Low |
|---|---|---|---|---|
| 1.5 Authorized single-document read | **needs human decision** (F1), then fixes | 2 | 3 | 4 |
| 1.6 Masking and field-level readability | **needs human decision** (its Open Question), otherwise near ready | 0 | 1 | 4 |
| 1.7 Links and child tables without N+1 | **needs human decision** (its two Open Questions plus F2), then fixes | 1 | 5 | 3 |

---

## Spec 1.5: Authorized single-document read

**Verdict: needs human decision.** AC coverage against the epics is complete: AC1 (spy on `get_query` flags), AC2 (UP / `permission_query_conditions` / `has_permission` hook rows), AC3 (parity matrix and the "document differs from the row" row), AC4 (select-only row), AC5 (types and `errors.py` tasks). The verified Frappe facts are right: `frappe.has_permission` at `frappe/__init__.py:603`, `Engine.get_query` keywords at `database/query.py:224-248`, `execute_query` masking at `query_builder/utils.py:137-160`, `make_sales_order` at `test_sales_order.py:3473`, `patch_hooks`/`set_user` in `frappe/tests/classes/context_managers.py:49,61`. The problems are in error containment, the boundary guard and a few contradictions.

### F1. High: a Stage 2 exception becomes an existence oracle (needs human decision)

- **Section:** Boundaries (AD-15 mapping bullet), Tasks (`executor.py` "A `DocWeaveError` during the load gives `{"data": null, "errors": [...]}`"), I/O rows "hook denies SO-1" and "Unexpected error".
- **Evidence:** `has_permission` hooks are called with no exception handling (`frappe/permissions.py:491-497`, `frappe.call(method, doc=doc, ...)`). `frappe.throw` raises `ValidationError` by default. Stage 2 only ever runs for a name that Stage 1 found, so it only runs for **existing** documents.
  - A hook that raises `ValidationError` (a common `frappe.throw(...)` pattern) gives `VALIDATION` with a message. A missing name gives `NOT_FOUND`. That distinguishes "exists, denied" from "does not exist".
  - A hook that raises `PermissionError` maps to `NOT_FOUND`, but per the executor task the whole response becomes `{"data": null, "errors": [...]}`. A missing name gives `{"data": {"salesOrder": null}, "errors": [{path: ["salesOrder"], ...}]}`. The two shapes differ, so this is an oracle too. It also wipes the other aliases' data, which contradicts the "Aliases" row.
  - Any other exception (`KeyError` in a hook) gives `INTERNAL`, again only for existing documents.
- **Why a human decision:** AD-15 maps `ValidationError` to `VALIDATION` without saying where. Containing Stage 2 exceptions as `NOT_FOUND` narrows AD-15 for one phase. That is a spine reading the human should approve.
- **Proposed fix:** add an Open Question with two options. (a) Inside `adapter/permission.py`, any exception raised while evaluating one candidate denies that candidate: the client sees the node-level `NOT_FOUND` at the node's path, identical in shape and message to "missing". Non-permission exceptions are still deferred-logged as `INTERNAL` for the admin (amends AD-15 by one sentence). (b) Keep AD-15 literally and accept the oracle as a documented residual next to `scanLimitReached`. Whatever is chosen: replace "a `DocWeaveError` during the load gives `data: null`" with per-node failure, so that a node failure never nulls sibling roots. Add matrix rows: hook raises `PermissionError`, `ValidationError` and `KeyError` for SO-1, and the test compares the **full** error JSON (message, path, code) with the missing-name case, not just the code.

### F2. High: the adapter side of the AD-1 guard is undefined, so `adapter/` can read data unchecked

- **Section:** Tasks (`test_boundaries.py`: "add the rule that `frappe.qb` is allowed only inside `_authorized_query`").
- **Evidence:** Spec 1.1 says "the checker is an allowlist: any `frappe.*` name not listed for a file fails", but its matrix for `adapter/` only lists bans (the six banned names, `get_doc`/`has_permission` outside `permission.py`, `get_single`). AD-1 lists nothing that `adapter/frappe_v16.py` or `adapter/errors.py` may use. Two readings follow, and both are wrong for 1.5:
  - **Literal allowlist:** `frappe.get_meta`, `frappe.session.user`, `frappe.DoesNotExistError`, `frappe.PermissionError`, `frappe.ValidationError` (needed by `errors.py`) and, in 1.6/1.7, `frappe.model.get_permitted_fields` and `frappe.query_builder` terms all fail. The implementer has to widen the allowlist silently.
  - **Open adapter:** `frappe.db.get_values`, `frappe.db.get_all`, `frappe.db.count`, `frappe.get_lazy_doc`, `frappe.get_last_doc` and `frappe.db.get_single_value` all pass. None is on the six-name ban list. That breaks AD-1's "data is read only through `_authorized_query`" and NFR-1.
- **Proposed fix:** in 1.5 (the first data-path story), define a per-file allowlist for `adapter/` in `test_boundaries.py`. For example: `frappe_v16.py`: `frappe.qb` (only inside `_authorized_query`), `frappe.get_meta`, `frappe.session.user`, `frappe.model.get_permitted_fields` (1.6), `frappe.query_builder` terms (1.7). `permission.py`: `frappe.get_doc`, `frappe.has_permission`, `frappe.get_meta`. `errors.py`: the three exception classes. `settings.py`: as in 1.2. Add negative fixtures: `frappe.db.get_values` and `frappe.get_lazy_doc` in `frappe_v16.py` fail, `frappe.qb` in a helper function of `frappe_v16.py` fails, and `from frappe import qb` inside `_authorized_query` passes. If this widens AD-1's text, raise it as a correct-course item, the same way 1.2 does for controllers.

### F3. Medium: the session-user check contradicts the closed signature, and its exception class is unspecified

- **Section:** Boundaries, first bullet. I/O row "Session switched".
- **Evidence:** The closed signature `_authorized_query(doctype, *, fields, filter, ..., keys)` has no `user` parameter, yet "if the user the adapter was built for isn't `frappe.session.user`, it raises". `_authorized_query` is a module function and can't know which user the adapter was built for. AD-2 has it asserting `user == frappe.session.user`. If the implementer raises `frappe.PermissionError`, F1's mapping turns it into a silent `NOT_FOUND` instead of the `INTERNAL` the matrix expects.
- **Proposed fix:** state where the check lives. Either `FrappeV16Adapter.load` compares `self.user` with `frappe.session.user` before every `_authorized_query` call, or `_authorized_query` gains a required keyword `user` that it compares (this keeps AD-2's wording). Name a non-Frappe exception (for example `RuntimeError` or a `SessionMismatch(DocWeaveInternal)`) so that it always maps to `INTERNAL`. Add a negative test that the mismatch is never `NOT_FOUND`.

### F4. Medium: "sanitized message" for `VALIDATION` is undefined, so values can leak

- **Section:** Boundaries (`errors.py` bullet).
- **Evidence:** Frappe `ValidationError` messages routinely embed document names and field values, plus HTML (`frappe.bold(...)`). AD-15 says "sanitized" but nothing defines it.
- **Proposed fix:** define the sanitizer: strip HTML, cap the length, and for exceptions raised inside the data path (Stage 1 or Stage 2) use a fixed per-class message rather than Frappe's text. Add a test where a hook raises `frappe.ValidationError("<b>secret 42</b>")` and the body contains neither `secret` nor `42` (if F1 option (b) is chosen; under option (a) the case becomes `NOT_FOUND`).

### F5. Medium: tests that call `api._run` can't verify the `finally` behaviour, and 1.2's catch-all logs inline before the rollback

- **Section:** Tasks (`tests/utils.py` `run_query` "calls `api._run` in-process"). I/O row "Unexpected error ... one deferred Error Log entry".
- **Evidence:** In 1.2 the rollback and `message_log` cleanup are in `graphql()`'s `finally`, outside `_run`. A `run_query` built on `_run` skips them, so the "deferred Error Log entry, written after the rollback" row can't be observed. Spec 1.2 also says an unexpected exception is "logged through `frappe.log_error`" with no `defer_insert`. `frappe/utils/error.py:88-91` inserts that row into the DB, and the `finally` rollback then discards it. 1.5 changes only `errors.py`'s entries to deferred logging. The ContextVar also isn't reset at request start, so a crash before `take_deferred()` can carry entries into the next request on the same thread.
- **Proposed fix:** route api's own catch-all `INTERNAL` through the same deferred list. Reset the ContextVar at the start of `graphql()`. Test the logging row through `docweave.api.graphql()` in-process (with `frappe.local.request` stubbed) or through a helper that reproduces the `finally`. Assert one Error Log entry after the rollback, with no locals in its traceback.

### F6. Low: the planner must send only `kind: "scalar"` fieldnames as columns

- **Section:** Never ("`xDoc` and Table fields resolve to `null`"), Tasks (`planner.py`).
- **Evidence:** 1.3's tags give `xDoc` the `fieldname` `customer` and `items` the `fieldname` `items` (a Table field, in `no_value_fields`, `frappe/model/__init__.py:53-60`). A planner that copies every tag's `fieldname` into `LoadRequest.fields` would put `items` into `get_query`.
- **Proposed fix:** state that `LoadRequest.fields` takes only `kind == "scalar"` fieldnames plus `name`, and add a test with `items` and `customerDoc` selected that checks the `fields` passed to `get_query`.

### F7. Low: select-only role plus a shared document diverges from REST

- **Section:** Boundaries ("A user without DocType-level `read` (select-only ...)").
- **Evidence:** `has_permission(doctype, "read")` with no doc returns True when at least one document is shared with the user (`frappe/permissions.py:201-205`). `get_query` then uses permission type `select` from roles alone (`database/query.py:1752`), so only the search fields are permitted (`model/meta.py:695-696`). REST `get_doc` on that shared document returns every level-0 field. This is over-restrictive, not a leak.
- **Proposed fix:** add a parity fixture (Projects User, which is select-only on Sales Order in `sales_order.json`, plus one shared SO) and record the expected behaviour, or note it as accepted.

### F8. Low: negative tests are missing for the exception map

- **Section:** I/O matrix.
- **Evidence:** Only `KeyError` (→ `INTERNAL`) and bad variables (→ `VALIDATION`) are tested. Nothing tests `DoesNotExistError` → `NOT_FOUND` (for example a document deleted between Stage 1 and Stage 2), `PermissionError` → `NOT_FOUND`, or `ValidationError` → `VALIDATION` with the class name. The Tests convention requires a negative test for every AD.
- **Proposed fix:** add one row per mapping, each driven by patching the adapter.

### F9. Low: graphql-core API claims are unverified

- **Section:** Code Map (`get_variable_values`, `get_argument_values`, `get_directive_values` as public API; `info.path.key`).
- **Evidence:** graphql-core isn't installed in the bench env, so this couldn't be checked. In 3.2 these functions are exported from `graphql.execution`, and `Path.key` is the response key. The 3.3 surface is unconfirmed.
- **Proposed fix:** make the first implementation step `pip show graphql-core` plus an import smoke test of these names. Have the planner skip `__typename` and introspection fields.

---

## Spec 1.6: Masking and field-level readability

**Verdict: needs human decision** on the Open Question. Otherwise it is close to ready. AC coverage: AC1 (masked Currency, pending the Open Question), AC2 (permlevel 1 → `FORBIDDEN`, parent not nulled) and AC3 (metadata-driven detection, the "value is `XXXXXXXX`" row, and both union negative tests) are all covered.

The verified facts are right:
- `Meta.get_masked_fields(parenttype)` returns `[]` for Administrator and caches under `masked_fields::<dt>::<parent>::<session user>` with no expiry (`frappe/model/meta.py:194-213`).
- `get_permlevel_access(permission_type, parenttype, *, user)` (`meta.py:731-739`) and `get_permitted_fields` (`frappe/model/__init__.py:217`) behave as described.
- `ignore_pricing_rule` is a Check at permlevel 1, and only Sales Manager has level 1 on Sales Order (`sales_order.json`).
- The fresh computation matches Spike 0.3's `fresh_masked` (`spikes/masking_check.py:79-83`).

**The Open Question is real and fair.** ERPNext v16.52.1's Customer has no `credit_limit` field and no Currency field at all; it has only the `credit_limits` Table (Customer Credit Limit). Both options are workable. Option 1 matches Spike 0.3's proven `spike_credit` Custom Field route.

### F1. Medium: names 1.6 needs aren't on the adapter allowlist (continuity with 1.5 F2)

- **Section:** Boundaries (`frappe.model.get_permitted_fields`), Code Map.
- **Evidence:** Under 1.1's "any `frappe.*` name not listed fails" rule, `frappe.model.get_permitted_fields` in `adapter/frappe_v16.py` fails `test_boundaries.py`, and 1.6 has no task to list it.
- **Proposed fix:** if 1.5 F2 is adopted, nothing more is needed. Otherwise add a 1.6 task that extends the adapter allowlist with `frappe.model.get_permitted_fields`, with a test.

### F2. Low: precedence between unreadable and masked is unspecified

- **Section:** Approach and Tasks ("marks unreadable selected fields `FORBIDDEN` and masked ones `MASKED`").
- **Evidence:** A field at a permlevel the user can't read can also carry `mask=1`. `get_masked_fields` includes it whatever its readability (`meta.py:205-210`).
- **Proposed fix:** `FORBIDDEN` wins: a field Frappe would drop is never reported as merely masked. Add a matrix row.

### F3. Low: the Date and Phone fixture is unspecified

- **Section:** I/O row "Masked Date and Phone".
- **Evidence:** The row doesn't name fields. Spike 0.3 used Custom Fields (`spike_since`, `spike_phone`) because the native candidates are awkward.
- **Proposed fix:** name the fixture fields, following the Open Question's choice.

### F4. Low: revocation is tested through one route only

- **Section:** I/O "Revocation". Tasks (`User.remove_roles`).
- **Evidence:** Spike 0.3's Limitations: Role Profile changes, Has Role edits that don't save the User, and Custom DocPerm edits that remove `mask` were not tested. The fresh computation is only as fresh as `frappe.get_roles` and the cached meta.
- **Proposed fix:** add one row where the `mask` right is removed by editing the Custom DocPerm (the most likely admin path), and assert `MASKED` on the next request.

### F5. Low: the per-request cache owner is implicit

- **Section:** Boundaries ("Results per request are cached by `(doctype, parenttype)`").
- **Proposed fix:** say that the cache lives on the per-request `FrappeV16Adapter` instance (1.5 builds one per request), never at module level, so it can't outlive a request or cross users. Add a test: two requests by different users in one process get different readable sets.

---

## Spec 1.7: Links and child tables in one request, without N+1

**Verdict: needs human decision** on its two Open Questions, plus F2, then fixes. Both Open Questions are real and their options are fair:
- **Query count:** AD-3's node identity includes the path, so 50 aliased roots can't be batched.
- **Failing one node:** AD-16's port has no way to fail one request while the others succeed.

AC coverage: AC1 (resolver spy), AC2 (Customer unreadable), AC3 (masked/forbidden source) and AC5 (aliases) are covered, and AC6 waits on the first Open Question. AC4 is **only partly covered**: see F1.

The verified facts are right: `assertQueryCount` is at `frappe/tests/classes/integration_test_case.py:122`, and masking matches by key after `run`, so an extra aliased select term passes through (`query_builder/utils.py:84-120`; `apply_field_permissions` lets any `Term` through, `database/query.py:1525-1527`).

### F1. High: there is no `parenttype` filter on child loads, so rows can leak across parent DocTypes

- **Section:** Boundaries ("Children ... passes `parent_doctype`, `parentfield` and `parent_names`"), Tasks (`frappe_v16.py` CHILDREN).
- **Evidence:** The epics AC says "the query filters on `parenttype`, `parentfield` and authorized parent names". The spec never mentions `parenttype`, and `get_query(parent_doctype=...)` doesn't add it. The permission join is only `tabChild.parent = tabParent.name` (`database/query.py:1618-1627`). Frappe's own `ChildQuery` adds `parenttype` explicitly (`database/query.py:2205-2209`), which shows the engine doesn't.
- **Impact:** child DocTypes such as Sales Taxes and Charges are shared by several parents with the same `parentfield` (`taxes` on Quotation, Sales Order and Sales Invoice). If a Quotation has the same name as an authorized Sales Order (names are user-settable), its tax rows join to that Sales Order and are returned under it. This is exactly the "cross-table child leak" AD-7 prevents.
- **Proposed fix:** whenever `parent_names` is given, `_authorized_query` always adds `parenttype = parent_doctype` alongside `parentfield` and `parent IN (...)`. Add a negative test: a Quotation and a Sales Order with the same name, both with `taxes` rows, and the Sales Order query returns only Sales Order rows.

### F2. Medium (needs decision with Open Question 2): a Link target the user can't select fails the whole response

- **Section:** I/O "Customer unreadable". Boundaries (Links). 1.5's executor rule.
- **Evidence:** `get_query` runs `check_select_permission` and raises `PermissionError` when the user has neither `select` nor `read` on the DocType (`database/query.py:1432-1437`). 1.7 doesn't apply 1.5's `can_read_doctype` short-circuit to Link targets or children, so "can read the SO but not its Customer" (the natural fixture, a user with no Customer role) raises inside the batched load. By 1.5's rule the whole response then becomes `{"data": null}` instead of `customerDoc: null` with `NOT_FOUND`.
- **Proposed fix:** before issuing a LINK request, run `can_read_doctype(target)` (and for CHILDREN, the parent's), and give every key `NOT_FOUND` without a query. Resolve per-node failure together with Open Question 2, so that any adapter exception for one node becomes that node's sentinel and never nulls the response. Add both fixtures: no Customer role at all, and Customer readable but this Customer denied by a User Permission.

### F3. Medium: a single `matched_key` can't represent one row matching several keys

- **Section:** Boundaries (Links: "`matched_key`, the requested key the SQL matched"). I/O row "Case variant". Code Map (`Case` per key).
- **Evidence:** MariaDB's `utf8mb4_unicode_ci` is case-insensitive and PAD SPACE. If two source rows hold `acme` and `ACME `, both keys are sent, SQL returns the one Customer row, and a `CASE WHEN name=%s THEN %s ...` term yields only the first matching key. The other source row finds no join and shows a spurious `NOT_FOUND`. This fails closed, so it isn't a leak, but it is wrong, and the matrix only tests one variant.
- **Proposed fix:** select one boolean term per key (`name = %s AS _k0`, `_k1`, ...), and in the adapter emit one `Row` per true flag with that key as `matched_key`. The SQL still decides matching and the assembler still joins only on the tag. Add a matrix row with two case variants of the same Customer in two orders.

### F4. Medium: the Table readability gate drops Frappe's share rule (parity bug, inconsistent with 1.6)

- **Section:** Boundaries (Children: "only if the Table field's permlevel is in `meta.get_permlevel_access("read", user=...)`").
- **Evidence:** `get_permlevel_access` is role-only (`meta.py:731-739`). For a user who reads the SO only through DocShare it returns `[]`, so `items` (permlevel 0) would be `FORBIDDEN`. Frappe REST returns the document's children for that user: `apply_fieldlevel_read_permissions` strips only `permlevel > 0` fields (`model/document.py:1214-1227`). 1.6's `readable_fields`, via `get_permitted_fieldnames`, adds level 0 for shared documents (`meta.py:705-708`), so the two rules disagree.
- **Proposed fix:** use the same permlevel set as 1.6 (role levels, plus 0 when the parent's access comes from a share; in practice any parent that passed AD-4 can read level 0). Add a parity row for Spike 0.1's share-only user selecting `items`.

### F5. Medium: `max_child_rows` mechanics are underspecified, and the task pre-decides Open Question 2

- **Section:** Boundaries (cap). Tasks (`frappe_v16.py`: "a per-request child-row counter against `max_child_rows`").
- **Evidence:** The spec doesn't say how the count is known without fetching everything (the cap exists to bound memory), and it doesn't say which nodes fail once the cap is crossed. It could be only the node that crosses it, or that node and every later one. With breadth-first loading, the outcome depends on the order of nodes within a level. The task already places the counter in the adapter, which is Open Question 2's option 1, before the human has chosen.
- **Proposed fix:** after Open Question 2 is decided, state the mechanics: query with `limit = remaining + 1`, and when it overflows the node gets `COST_LIMIT` and no rows are kept. Decide whether later child nodes in the request also get `COST_LIMIT`, and make node order within a level deterministic (sorted by path). Add a test with two child nodes whose total crosses the cap.

### F6. Medium: the CHILDREN request contract for parent names is missing

- **Section:** Tasks (`parent_names` limited to authorized parents). AD-16's `LoadRequest` has no `parent_names`.
- **Evidence:** The spec doesn't say which `LoadRequest` field carries the parent names (presumably `keys`), or what the adapter checks them against. "Limited to authorized parents" needs a source of truth inside the adapter, or the adapter is trusting the executor.
- **Proposed fix:** for CHILDREN, `keys` holds the parent names. The adapter intersects them with the names that its `PermissionChecker` passed through Stage 2 for `parent_doctype` in this request, and drops the rest. Add a negative test that calls `adapter.load` directly with an unauthorized parent name and gets no rows and no query containing that name.

### F7. Low: a negative test for "no child load under a denied parent" is missing

- **Section:** Tasks (`test_links_children.py` negatives).
- **Proposed fix:** a test where `salesOrder` is `NOT_FOUND` because of a hook: no `_authorized_query` call for Sales Order Item, and no Link load from its rows.

### F8. Low: `frappe.query_builder` terms in the adapter need an allowlist entry

- **Section:** Code Map (`Case` per key).
- **Proposed fix:** covered if 1.5 F2 is adopted. Otherwise list the term import for `adapter/frappe_v16.py`.

### F9. Low: Open Question 1's proposal should state the query-count numbers precisely

- **Section:** Open Questions, query count.
- **Proposed fix:** if option 1 is chosen, give the exact assertion: `_authorized_query` calls = 1 (root) + 1 (items) + 1 (Item link) for 1 and 50 items, and `has_permission` calls = 1 + the number of distinct Items. Write it with `assertQueryCount` or `_authorized_query` spies, so that the test can't pass vacuously.

---

## Cross-spec notes

- **Continuity is otherwise sound.** The names 1.6 and 1.7 rely on all exist in 1.5 with the same spellings: `FrappeV16Adapter`, `_authorized_query` with `keys`/`parent_doctype`/`parentfield`/`parent_names`, `PermissionChecker.readable`, `Row.matched_key`, `LoadKind`, the `Sentinel` constants and `run_query`. 1.7 adds `COST_LIMIT` itself. 1.3's tags (`root_one`, `link_doc`, `children`, `scalar`) are used consistently.
- **Nothing else was decided silently** beyond the points marked above: 1.5 F1 (whole-response failure) and 1.7 F5 (where the counter lives).
