---
name: 'DocWeave architecture spine: security review, round 2'
type: architecture-review
lens: security (read-side authorization and data leaks)
target: '../../ARCHITECTURE-SPINE.md'
previous: '../review-security.md'
created: '2026-10-24'
reviewer: ad-hoc security reviewer (round 2)
scope: 'v1 read path only. AD-9 and AD-13 are [v2] and are reviewed only where v1 text is inconsistent.'
---

# Security Review, Round 2: DocWeave Architecture Spine

## Verdict

**Close, but not ready to bind.** The rewrite fixes the round-1 read-side headline issues. The cursor is now opaque (H1). Child loads are bound to `parentfield` and to table permlevel (H2). POST-only closes the GET/CSRF hole (H4). Field-level `FORBIDDEN` and all-nullable output fix M1. AD-15 removes the `NOT_FOUND`/`FORBIDDEN` oracle (M2).

The new AD-4 "permission projection" is the right idea, but as specified it does **not** reproduce what Frappe v16's `has_permission(doc=...)` actually evaluates:

- It leaves out child tables. Frappe checks User Permissions on child-row Link fields.
- It is fetched through a query that silently drops permlevel-restricted fields.
- It assumes `has_permission` does no I/O. In fact it queries DocShare per document, and stock hooks load documents by name.

Separately, the AD-12 "rollback before return" deletes DocWeave's own `INTERNAL` Error Log rows and does not deliver the stated guarantee.

Severity counts for new findings: **0 critical, 1 high, 5 medium, 6 low.**

Source basis: Frappe `version-16` branch, fetched from `raw.githubusercontent.com/frappe/frappe/version-16/`:

- `frappe/permissions.py`
- `frappe/database/query.py`
- `frappe/model/document.py`
- `frappe/model/meta.py`
- `frappe/model/__init__.py`
- `frappe/query_builder/utils.py`
- `frappe/share.py`
- `frappe/app.py`
- `frappe/database/database.py`
- `frappe/utils/error.py`
- `frappe/utils/password.py`
- `frappe/utils/response.py`
- `frappe/cache_manager.py`
- `frappe/hooks.py`
- `frappe/desk/doctype/event/event.py`
- `frappe/contacts/address_and_contact.py`
- `frappe/core/doctype/communication/communication.py`

ERPNext `version-16` `erpnext/hooks.py` was also checked.

---

## Part 1: Status of round-1 findings

| ID | Round-1 finding | Status | Notes against the rewritten text |
| --- | --- | --- | --- |
| H1 | Cursor leaks name and sort value of AD-4-rejected rows | **Resolved** | AD-8: Fernet (AEAD) with an HKDF-derived key; `user` is inside the ciphertext. Residual: the *presence* of a cursor on an empty page is still a signal (see N5). |
| H2 | Child rows not bound to `parentfield` | **Resolved** | AD-7: `parent_doctype` + `parentfield` + `parent IN (authorized)`, and the Table field must be readable at its permlevel. AD-2 has the `parentfield` parameter. All fields except `name` are nullable (AD-5). |
| H3 | Mutation input surface undefined | N/A (v2) | AD-13 now covers it for v2. |
| H4 | GET accepted, CSRF bypass | **Resolved** | AD-12 uses `methods=["POST"]`, and `sdl` is POST-only. For a read-only v1 a JSON Content-Type requirement is optional. |
| H5 | Partial commits on field errors | N/A (v2) | AD-9 is all-or-nothing. v1's rollback is reviewed in N4. |
| M1 | No field-level `FORBIDDEN`; non-null permlevel fields | **Resolved** | AD-5 adds the `FORBIDDEN` sentinel, and every field except `name` is nullable. |
| M2 | `NOT_FOUND` vs `FORBIDDEN` existence oracle | **Resolved** (design) | AD-15. The remaining timing and pagination signals are covered in N5 and L4. |
| M3 | Frappe envelope leaks messages | **Partial** | AD-12 clears `message_log` and writes the body. It does not clear `error_log`/`debug_log`, and it does not cover the uncaught-exception path, where Frappe's `report_error` builds the envelope (N8). |
| M4 | Cost and scan limits fail under aliases, children, fan-out | **Partial** | Added: `max_total_candidates`, `child_fanout_estimate`, rejection of `first` above the maximum. Missing: a hard per-parent child-row cap (the estimate is only an estimate), a token or body-size cap, an alias or root-field cap, JSON-array batch handling, and a wall-clock limit. Per-candidate cost is not constant either (N3). |
| M5 | `has_permission` evaluated on partial rows | **Partial** | AD-4 now fetches a projection. But the projection omits child tables (N1), loses permlevel-restricted fields (N2), and omits optional columns (`_assign`, `_user_tags`, ...). |
| M6 | Filter/sort grammar not pinned | **Mostly resolved** | Closed `FilterIR`/`OrderSpec`, own fields only, typed `after`, AD-6 pre-rejection. Open: AD-5/AD-6 do not say which `permission_type` "readable" means. Frappe returns only search fields for select-only users (`get_permitted_fields`), while `get_query` lets select-only users filter on all permlevel-0 fields. Pin it to DocWeave's own computation (the stricter one) and test select-only. |
| M7 | Exposure policy (Dynamic Link, non-exposed targets, child/Single roots, core DocTypes, Password) | **Partial** | Resolved: Dynamic Link has no resolver in v1, `xDoc` exists only for exposed targets, child and Single roots are rejected (AD-14), and Password is excluded. **Open:** there is no hard denylist of core and security DocTypes. `get_permitted_fields` returns *all* columns for `CORE_DOCTYPES` other than User (`frappe/model/__init__.py`), ignoring permlevel. Exposing Role, DocType, DocPerm, User Permission, DocShare, Has Role, OAuth*, Access Log or Error Log would bypass permlevel. |
| M8 | Portal users and introspection | **Partial** | The `allowed_roles` gate excludes Website Users by default. Introspection is still available to every allowed user, while `sdl` is limited to System Manager. That is inconsistent, because `__schema` returns the same information (N7). |
| L1 | Raw Link names leak | **Resolved by decision** | AD-7 states parity, and `redact_unreadable_link_names` is deferred. |
| L2 | Schema-cache user dependence and races | **Partial** | The stale-meta race is fixed by the `(revision, fingerprint)` key, and migrate bumps the revision. Still unaddressed: language and translation of descriptions, and a fixed build context. A collision still fails the whole build, which is a site-wide denial of service by any Customize Form user (now a deliberate choice; document it). Also see N11 (multi-site LRU). |
| L3 | Cursor key management | **Mostly resolved** | HKDF purpose label, `kid`, 24 h TTL. The source of the "previous" key is undefined (N9). |
| L4 | Count and timing oracles | **Open** | The spine neither records the residual risk nor bans `totalCount`/aggregates without AD-4 semantics. `hasNextPage` semantics add an oracle (N5). |
| L5 | Administrator and privileged keys | **Resolved** | `allow_administrator` defaults to off, and Settings has change tracking. |
| L6 | Create-but-not-read re-read | N/A (v2) | AD-9: a `null` `doc` with `NOT_FOUND`. |
| L7 | Resolver I/O vs mutations | N/A (v2) | AD-3 v2 carve-out. |

---

## Part 2: New findings

### High

#### N1. The permission projection has no child rows, so Frappe's User Permission check on child-table Link fields is skipped, and DocWeave serves documents that Frappe's own `GET /api/resource/<dt>/<name>` denies

- **Affected:** AD-4, AD-14, AD-7
- **Facts (v16):**
  - `has_permission(doc=...)` calls `get_doc_permissions`, which calls `has_user_permission(doc, ...)`. Step 2 of that check runs `check_user_permission_on_link_fields(d)` on the parent **and on every `doc.get_all_children(include_computed=True)` row** (`permissions.py` around L473-478).
  - AD-4 builds the document from "every non-table field". `Document.__init__(dict)` calls `init_child_tables()`, so every table is `[]` and `get_all_children` returns nothing. The child-link check therefore passes vacuously.
  - `get_query` only turns User Permissions into SQL for the *parent's* Link fields (`get_user_permission_conditions` over `meta.get_link_fields()` of `permission_doctype`). Neither stage checks child-table links.
  - Frappe's document read paths (desk `getdoc` and REST by-name, both via `doc.check_permission("read")` on a fully loaded document) **do** check them.
  - AD-14 then makes the child rows inherit this incomplete parent check ("the AD-4 check is the parent's check").
- **Attack:** A sales user has a User Permission restricting them to Warehouse "Stores - A". Sales Order SO-0042 has an item row with `warehouse = "Stores - B"`. Frappe's `GET /api/resource/Sales Order/SO-0042` returns 403 ("You are not allowed to access this Sales Order record because it is linked to Warehouse 'Stores - B' in row 1 ..."). DocWeave's `salesOrder(name: "SO-0042") { items { warehouse rate } }` returns the full document and its rows. The same applies to Company, Cost Center, Project and Territory restrictions on child rows, which are common ERPNext multi-company setups.
- **Secondary effect:** Hooks that read child tables see empty lists. Stock Frappe's `Event.has_permission` loops `doc.event_participants`, so participants are wrongly denied (fail-closed). Custom hooks written as "deny if any row matches X" fail **open**.
- **Fix:** Amend AD-4:
  - The projection includes the child rows of every Table field whose child DocType has a Link field without `ignore_user_permissions` that targets a DocType in the user's User Permissions. Also include any table a hook declares it needs (a `docweave_permission_tables` hook or Settings list).
  - Load them batched per page, with one query per such table field over `parent IN (candidate names)`. This keeps the query count constant per page.
  - Attach them to the unsaved document before calling `has_permission`.
  - These rows are permission inputs only. They never cross the port, and the user-visible child load still goes through AD-7.
  - Fix AD-14's wording: "the parent's check, evaluated with its children attached".
  - Add a negative test with a child-row Warehouse restriction, and the Event-participant positive test.

### Medium

#### N2. The projection is fetched with `ignore_permissions=False`, so permlevel-restricted fields are silently missing and hooks fail open

- **Affected:** AD-4, AD-2
- **Facts:**
  - `get_query` runs `apply_field_permissions`, which keeps a plain field only if `field.name in OPTIONAL_FIELDS or field.name in permitted_fields_set` (`query.py`, `apply_field_permissions`).
  - Fields above the user's permlevel are **dropped without error**, and masked fields come back as placeholders (`query_builder/utils.py` `mask_fields`). For select-only users, only `default_fields` plus search fields survive (`get_permitted_fields`, `permission_type == "select"`).
  - AD-4 documents only the mask placeholders.
  - Stock hooks fail open on missing values. `address_and_contact.has_permission` (Contact, Address) returns `True` when `not any(names)` across its Customer/Supplier/Company/Sales Partner links. If those fields are at a permlevel the user cannot read, the hook allows access. `has_user_permission` also skips empty links unless `apply_strict_user_permissions` is on. SQL already covers parent links, so the main risk is hooks and custom code.
  - "Every non-table field" also omits `_assign`, `_user_tags`, `_liked_by` and `_seen`. `get_permitted_fields` returns these, and assignment-based custom hooks read them.
- **Fix:**
  - Define the projection by `meta.get_valid_columns()`, not by "fields".
  - Fetch it through a second, named adapter function, `_permission_projection(doctype, names)`. It is restricted to `name IN (names already returned by _authorized_query)`, may bypass field permissions and masking, and its output is consumed only by `has_permission` and never placed in a `Row`.
  - Add `_permission_projection` to the AD-1 allowlist explicitly, with a boundary test that its return value has no path to `core.Row`.
  - Either way, change the AD-4 limitation text to cover both masked and permlevel-dropped fields. Add a test with a hook that reads a permlevel-1 field.

#### N3. "Constant queries per page" is false: `has_permission` does DocShare I/O per document, and stock hooks load documents by name, so low-privilege users get a 10,000-query amplifier

- **Affected:** AD-4 (query-count test), AD-8 (budgets), AD-10
- **Facts:**
  - In `permissions.has_permission`, when the role check fails, `false_if_not_shared()` runs `frappe.share.get_shared(doctype, user, filters=[["share_name","=",name]], limit=1)`. That is an uncached `frappe.get_all("DocShare", ...)` **per candidate**. This is hit for:
    - **select-only users.** `get_query` admits them (`check_select_permission` checks `select`), and every candidate fails `read` and triggers a share query.
    - **`if_owner` roles.** `get_role_permissions` sets `if_owner.read = is_owner`, `get_doc_permissions` applies it, and every shared, not-owned candidate costs a query.
    - **controller-hook denials.** Shares override hooks, because the share fallback runs after `get_doc_permissions` returns `{read: 0}`.
  - Stock hooks query per document. `Communication.has_permission` calls `frappe.has_permission(reference_doctype, doc=reference_name)`, and `get_lazy_doc` loads it. The Contact/Address hook does the same for each of its link fields.
- **Attack:** A user with only `select` on Customer (granted widely for Link pickers) sends `customers(first: 100)` under aliases. Every candidate is rejected after one DocShare query, so the request burns the whole `max_total_candidates` (10,000), roughly 10,000 queries per request, and returns nothing.
- **Fix:**
  - Short-circuit before scanning. If `get_role_permissions(meta, user)["read"]` is false and `frappe.share.get_shared(doctype, user)` (one query) is empty, return an empty page with `hasNextPage: false`. Doing that for every select-only user is safe, since they never pass AD-4.
  - Otherwise call `frappe.permissions.has_permission(..., ignore_share_permissions=True, print_logs=False)` and OR the result with a share set prefetched once per request. That matches Frappe's ordering exactly: share overrides role, `if_owner` and hook denials.
  - Charge hook cost: apply a per-request wall-clock limit on the AD-4 stage, and lower the default `max_total_candidates` for DocTypes with registered `has_permission` hooks.
  - Change the query-count test to "constant per page, *excluding queries issued by third-party `has_permission` hooks*", with fixtures for select-only users, `if_owner` users and shared documents.

#### N4. AD-12's "rollback before return" erases DocWeave's own Error Log entries and does not enforce read-only

- **Affected:** AD-12, AD-15, AD-1 (allowlist), Operations (observability)
- **Facts:**
  - `frappe.log_error` calls `error_log.insert(ignore_permissions=True)` **in the current transaction**, unless `frappe.flags.read_only` or `defer_insert` is set (`utils/error.py`). AD-15 logs `INTERNAL` with `frappe.log_error`, and AD-12 then rolls back. **Every `INTERNAL` Error Log row is deleted.**
  - `log_error`'s default traceback is `frappe.get_traceback(with_context=True)`, which includes local variables. That contradicts AD-15's "without local variables" unless the message is passed explicitly.
  - `Database.rollback()` resets `after_commit`/`before_commit` callbacks and runs `after_rollback`. That is harmless for reads, but it does not stop:
    - explicit `frappe.db.commit()` calls inside hooks during the request
    - MariaDB implicit commits on DDL
    - Redis writes, `enqueue` without `enqueue_after_commit`, and outbound HTTP
    - writes made by `after_request` hooks (`app.py` runs them after the endpoint returns)
  - "No v1 request can persist a write, even from a hook" is therefore overstated.
  - Under `IntegrationTestCase`, `_disable_transaction_control` turns `rollback()` into a warning no-op. A naive test would "pass" without exercising the rollback.
  - The rollback itself does not break Frappe's lifecycle. `sync_database` commits an empty transaction for POST, and `session.update` runs in `after_response` in a new transaction.
- **Fix:**
  - Log with `frappe.log_error(title, message=frappe.get_traceback(with_context=False), defer_insert=True)`. Deferred inserts go through Redis and survive the rollback.
  - Enforce read-only at the database. After the access gate, run `frappe.db.rollback()` then `frappe.db.begin(read_only=True)`, which is Frappe's own `setup_read_only_mode` pattern, so engine-level writes fail with an error instead of being silently undone.
  - Roll back and restore a normal transaction before returning, so `after_response` session updates still work. Do not set the global `frappe.flags.read_only`, which would leak into `after_response`.
  - Reword AD-12 to "no database write made through the request transaction persists". List what is out of scope: explicit commits, DDL, and non-DB side effects of third-party hooks.
  - Test with a hook that writes, and assert the row is absent, using a test class that keeps transaction control enabled.

#### N5. `hasNextPage` and cursor presence are oracles for hook-hidden or select-only rows

- **Affected:** AD-8, AD-15
- **Facts:** AD-8 says "`hasNextPage: false` only when the candidates are known to be exhausted". An implementation that fills the page and then peeks at one more *candidate* (LIMIT `first+1`) without checking it through AD-4 returns `hasNextPage: true` whenever any SQL-visible but AD-4-denied row matches the filter after the last visible row. AD-8 issues a cursor on an empty page only when a budget is exhausted, but it does not say that `endCursor` must be `null` on an empty, exhausted page. If `position` advanced over rejected rows, a non-null `endCursor` reveals that hidden matches exist, even though the ciphertext is opaque.
- **Attack:** Customer documents hidden by a `has_permission` hook (or shared-only access patterns) are still candidates. The attacker queries `customers(filter: {territory: {eq: "X"}, customerName: {like: "Acme%"}}, first: <visible count>)`, and `hasNextPage` answers "does a hidden Acme in territory X exist?" Bisecting on readable-field filters extracts attribute values of hidden documents one bit per request.
- **Fix:**
  - Define `hasNextPage: true` only if (a) another candidate *passed AD-4* (a look-ahead check that counts against the scan budget), or (b) a budget was exhausted, which is then also flagged by `scanLimitReached`.
  - Define `endCursor = null` whenever the page is empty and `scanLimitReached` is false.
  - Record the remaining `scanLimitReached` count signal (it reveals at least 2,000 hidden candidates) and the per-candidate timing as accepted residual risk. Add "no `totalCount` or aggregate without AD-4 semantics" to AD-8. This closes L4.
  - Add a negative test: a hook-denied row after a full page yields `hasNextPage: false` and the same response bytes as when the row is absent.

#### N6. The masked-field list is cached per user in Redis and (to verify) not invalidated on role changes

- **Affected:** AD-5, AD-11 (bump triggers)
- **Facts:**
  - `Meta.get_masked_fields(parenttype)` caches under `masked_fields::{doctype}::{parenttype}::{frappe.session.user}` in `frappe.cache` with no expiry, and it always uses `frappe.session.user`.
  - `cache_manager.clear_user_cache(user)`, which runs on role and user changes, deletes `user:<user>` keys and the user hash names. That pattern does not match `masked_fields::`.
  - DocType cache clears (`clear_doctype_cache`) wipe `*{dt}*` through `client_cache.delete_keys`, which probably covers it.
  - Frappe's own query masking (`query_builder/utils.py`) uses the same cached list.
  - If verified, a user who loses a role carrying the `mask` (unmask) right keeps receiving unmasked values until a DocType cache clear. AD-11's triggers (DocPerm, Custom DocPerm, ...) do not include Has Role or User role edits.
- **Fix:**
  - In the adapter, compute masked fields fresh from `meta.get_permlevel_access("mask", parenttype, user=user)` (roles come from `frappe.get_roles`, which *is* invalidated on role change). Then **replace the value with the `MASKED` sentinel regardless of what Frappe returned**, so a stale Frappe cache cannot unmask.
  - Assert in a test that removing the unmask role takes effect on the next request.
  - Report the cache-key issue upstream if it is confirmed.

### Low

#### N7. The access gate depends on role configuration only; introspection is open while SDL is restricted

- **Affected:** AD-12, AD-11
- **Facts and fix:**
  - "Never includes Website Users" depends on which roles an admin adds. A role such as "Customer" or "Supplier" can be held by Website Users. Add a hard check, `frappe.get_cached_value("User", user, "user_type") == "System User"` (or `is_system_user`), independent of `allowed_roles`. Settings validation should also reject `All` and `Guest`. The default `Desk User` (v16 `SYSTEM_USER_ROLE`, automatic for system users) is good.
  - `api.sdl` is limited to System Manager, but every allowed user gets the same schema through `__schema`. That includes DocTypes and fields they cannot read (names such as `marginRate` or `creditLimit`, and help text). Either drop the SDL restriction as theater, or add `introspection_roles` and disable `__schema`/`__type` for users outside it. MCP agents can be given the SDL out of band.

#### N8. The uncaught-exception path falls back to Frappe's envelope

- **Affected:** AD-12, Conventions (no tracebacks)
- **Facts:**
  - If anything raises outside the transport's own handling (schema build, the access gate raising a Frappe exception, response serialization), `app.handle_exception` runs, then `report_error`. That copies `message_log` and `exc_type` into the response (v1) or `errors` (v2), and a traceback for system users with tracebacks allowed.
  - `message_log` can contain `get_query` texts such as "You do not have permission to access field: {doctype}.{field}" and User Permission messages that name the restricted value.
  - The `frappe.has_permission` wrapper passes `print_logs=throw` (`False`), so AD-4 itself adds nothing. Hooks and `get_query` can.
- **Fix:**
  - Wrap the whole endpoint body in `try/except BaseException`. Write 400 and 403 responses directly rather than raising.
  - Clear `message_log`, `error_log`, `debug_log` and `frappe.local.response` keys in a `finally`.
  - Never call `frappe.has_permission(..., throw=True)`.
  - Test that a forced exception in the schema builder yields `{errors:[{code: INTERNAL}]}` and nothing else.

#### N9. Cursor key derivation details

- **Affected:** AD-8
- **Facts and fix:**
  - Frappe keeps a single `encryption_key`. `get_encryption_key()` generates it lazily and writes `site_config` on first use (a race across workers on a fresh site). There is no "previous" key, and the Config convention bans DocWeave from using site_config. So "current and previous `kid` accepted" has no source. Either define `kid` as a hash of the derived key and drop "previous" (key change means all cursors become `BAD_CURSOR`, acceptable with a 24 h TTL), or state where the previous key lives.
  - Put the site name in the HKDF `info`. Restored or cloned sites share `encryption_key`, and the user is identified by email, so a cursor issued on staging would otherwise decrypt on production.
  - Use Fernet's own timestamp with `decrypt(ttl=86400)` rather than a second `iat`, or document why both exist.
  - Call `get_encryption_key()` at install (`after_install`) so the key exists before concurrent requests.

#### N10. Dynamic Link companion field readability and naming

- **Affected:** Conventions (Link variants), AD-5, AD-7
- **Fix:**
  - The synthetic `xDoctype` must take its readability and mask state from the **companion** Link-to-DocType field, not from `x`. The two can sit at different permlevels.
  - The companion field is also emitted as its own real field (for example `referenceDoctype`), so `xDoctype` is redundant and a collision risk under the "any collision fails the build" rule. Either drop the synthetic field or define it as an alias with the companion's permissions.
  - Note in AD-7 that the raw Dynamic Link name can name documents of **non-exposed** DocTypes (User, Employee). That is at parity with desk, and the deferred `redact_unreadable_link_names` should cover it.

#### N11. Schema cache: multi-site workers and agent-facing descriptions

- **Affected:** AD-11
- **Fix:**
  - A bench gunicorn worker serves several sites. Key the per-process LRU by `(frappe.local.site, revision, fingerprint)`. The random 64-bit revision makes a collision unlikely, but the site must be explicit, and `docweave:schema_revision` must go through `frappe.cache` (which namespaces by site), never a raw Redis client.
  - Build descriptions in a fixed language (site default), without calling `_()` under the requesting user's language (open from round-1 L2).
  - Labels and help text become descriptions for MCP agents (FR-13). Anyone with Customize Form can inject instructions there. Strip HTML, cap the length, and document this as a prompt-injection surface.

#### N12. Shared documents for users with only select permission on the DocType are misclassified

- **Affected:** AD-5, AD-7, AD-15
- **Facts:**
  - For a DocType where the user's role grants only `select`, a document shared with `read` passes AD-4.
  - `get_query`'s `get_permission_type` is doctype-level (`only_has_select_perm`). It returns `select`, so only search fields are selectable, and child loads throw `PermissionError` ("You do not have permission to access child table field").
  - AD-15 maps that to `NOT_FOUND` on a child list of a parent the user is authorized to read.
- **Fix:** Map `PermissionError` from a child load of an AD-4-authorized parent to `FORBIDDEN` on the Table field, and test shared-doc access for a user with only `select`. This is functional, not a leak, but it makes the error codes misleading.

---

## Recommended spine edits (summary)

1. **AD-4:**
   - Projection = `get_valid_columns()` plus the user-permission-relevant child rows (batched).
   - Fetched through a named `_permission_projection` restricted to authorized names, and never surfaced.
   - `has_permission(..., ignore_share_permissions=True)` OR a share set prefetched once per request.
   - A short-circuit for users with only select permission.
   - Query-count test wording that excludes third-party hook I/O.
2. **AD-14:** "the parent's check, evaluated with its children attached".
3. **AD-8:** `hasNextPage` uses a look-ahead through AD-4, `endCursor` is `null` on an empty page unless a budget was exhausted, an accepted-residual-risk note, no `totalCount`, the site name in the HKDF info, and the `kid`/previous-key source stated.
4. **AD-12:**
   - A `READ ONLY` transaction plus the rollback, with the guarantee reworded.
   - A hard System User check.
   - Introspection gated consistently with `sdl`.
   - An outermost catch-all with the logs cleared in `finally`.
5. **AD-15:** `log_error(..., message=get_traceback(with_context=False), defer_insert=True)`.
6. **AD-5:** compute masks fresh from `get_permlevel_access("mask")` and always overwrite with the sentinel.
7. **AD-11 / AD-14:** a hard denylist of core and security DocTypes (`CORE_DOCTYPES`, log types, DocShare, User Permission, OAuth*, ...), and the site in the LRU key.

## Additional negative tests required

1. A child-row Warehouse User Permission denies the parent, matching REST by-name (N1).
2. A hook that reads a permlevel-1 field the user cannot read does not fail open (N2).
3. Query count with users who have only select permission, `if_owner` users and shared fixtures, and a select-only scan that short-circuits (N3).
4. An `INTERNAL` error leaves an Error Log row after the request, with no locals in it (N4).
5. A hook that writes leaves no row, with transaction control enabled in the test (N4).
6. A hidden row after a full page gives identical `pageInfo` to an absent row (N5).
7. Removing the unmask role takes effect on the next request (N6).
8. A Website User holding an allowed role is still refused (N7).
9. A forced builder exception yields only `{errors}` (N8).
