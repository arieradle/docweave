# Currency / Reality-Check Review, Round 2: DocWeave Architecture Spine

- Reviewer lens: is every committed decision, especially the ones new or changed in the rewrite, checked against live sources?
- Date: 2026-10-24
- Spine: `../../ARCHITECTURE-SPINE.md` (not edited)
- Round 1: `../review-currency.md`
- Sources checked live today: `raw.githubusercontent.com/frappe/frappe/version-16/...` (`__version__ = "16.53.0"`), the GitHub refs API, the PyPI JSON API, the graphql-core 3.3.0 wheel from PyPI (source read directly), and `pyca/cryptography@50.0.2`.

## Verdict

**Mostly verified. Round-1 fixes landed correctly, but there are 2 Medium correctness gaps and several Low precision fixes.** Every pin and the main Frappe API names check out. The gaps are:

1. **Fieldtype map (Medium).** It mistypes Rating and Duration, and it leaves out three real v16 fieldtypes: Long Int, HTML Editor and Attachment Gallery.
2. **Masking cache (Medium).** Frappe caches `get_masked_fields` per user and does not clear that cache when the user's roles change. AD-5 relies on it, so DocWeave inherits a stale-unmask window.

Smaller issues:

- The AD-1 allowlist leaves out two Frappe names that the spine's own rules need (`client_cache`, `local.message_log`).
- Two of the AD-11 bump triggers (`Customize Form` and `DocPerm`) can never fire as doc_events.
- Frappe has no `frappe.get_encryption_key` and no previous-key concept, so the source of AD-8's `kid` rotation is unspecified.

## Summary table

| # | Claim (spine location) | Status | Severity |
|---|---|---|---|
| 1 | Frappe `>=16.53.0,<17`, CI tag v16.53.0 (Stack) | Verified | - |
| 2 | ERPNext v16.52.1 (Stack) | Verified | - |
| 3 | graphql-core `~=3.3.0`, `Executor`, frozen AST (Stack, AD-3, AD-10) | Verified | - |
| 4 | `info.path.key` is the response key, so aliases work (AD-3) | Verified | - |
| 5 | Depth limit as a graphql-core validation rule, with introspection exempt (AD-10) | Verified API; a gap left open | Low |
| 6 | Custom scalars `Decimal`, `Date`, `Datetime`, `JSON` (Scalars) | Verified; 3.3 adds `coerce_*` names | Low |
| 7 | cryptography Fernet + HKDF at "the version Frappe v16 pins" (Stack, AD-8) | Verified (`cryptography~=50.0.0`) | - |
| 8 | Fernet described as "AEAD" (AD-8) | Wording inaccurate | Low |
| 9 | Key derived with HKDF from the "site encryption key"; current and previous `kid` (AD-8) | Key source verified; previous key **has no Frappe source** | Medium-Low |
| 10 | ruff 0.14.10 matches Frappe v16 (Stack) | Verified | - |
| 11 | frappe-bench 5.31.0 (Stack) | Verified (5.31.1 is newer) | - |
| 12 | MariaDB 11.8 (Stack) | Verified (the top of the tested range) | - |
| 13 | `@frappe.whitelist(methods=["POST"])` (AD-12) | Verified | - |
| 14 | `frappe.db.after_commit` (AD-11) | Verified | - |
| 15 | `frappe.clear_cache(doctype=...)` (AD-11) | Verified; redundant with Frappe's own handlers | - |
| 16 | "Frappe's metadata version" in the fingerprint (AD-11) | Exists; name and location not stated; internal API | Low |
| 17 | `meta.get_masked_fields(parenttype=)` already applies the DocPerm unmask setting (AD-5) | Verified; **cache is stale on role change** | **Medium** |
| 18 | DocPerm unmask field name | Verified: `mask` (label "Mask") on DocPerm and Custom DocPerm; DocField flag also `mask` | - |
| 19 | Bump triggers include `Customize Form` and `DocPerm` (AD-11) | **These two doc_events never fire** | Low |
| 20 | Clear `message_log` so the Frappe envelope never appears (AD-12) | Verified; there is a better mechanism | Low |
| 21 | AD-1 allowlist covers what the non-adapter layers need | **Incomplete** | Medium-Low |
| 22 | Fieldtype map (Conventions) | **Wrong in 2 types, 3 types missing** | **Medium** |
| 23 | Table MultiSelect (Link variants, AD-14) | Verified | - |
| 24 | `after_uninstall` deletes the `docweave:*` keys (Operations) | Verified; mostly redundant | Low |
| 25 | `schema_revision` initialized to a random 64-bit value (AD-11) | Plausible; init race not covered | Low |
| 26 | `IntegrationTestCase` (Tests) | Verified | - |
| 27 | CI `bench run-tests --app docweave` (Stack) | Verified; missing `--site` and the `allow_tests` precondition | Low |

## Detailed findings

### 1. Frappe `>=16.53.0,<17`, CI pinned to tag v16.53.0
- **Status:** Verified. The tag `v16.53.0` exists (GitHub refs API returns 200), and `frappe/__init__.py` on `version-16` has `__version__ = "16.53.0"`.
- **Evidence:** https://api.github.com/repos/frappe/frappe/git/ref/tags/v16.53.0 ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/__init__.py (line 58)
- **Fix:** None.
- **Severity:** -

### 2. ERPNext v16.52.1 (test-only)
- **Status:** Verified. The tag `v16.52.1` exists (200). Round 1 confirmed that ERPNext v16 declares `frappe = ">=16.50.0,<17.0.0"`, which is compatible with 16.53.0.
- **Evidence:** https://api.github.com/repos/frappe/erpnext/git/ref/tags/v16.52.1 ; https://raw.githubusercontent.com/frappe/erpnext/version-16/pyproject.toml
- **Fix:** None.
- **Severity:** -

### 3. graphql-core `~=3.3.0`: `Executor` and frozen AST
- **Status:** Verified from the 3.3.0 wheel source. 3.3.0 was released 2026-09-27 and is the latest. Confirmed:
  - The top-level export is `Executor`. `ExecutionContext` no longer appears anywhere in the package.
  - `execute(...)` takes `executor_class: type[Executor] | None`, plus `abort_signal` and `hooks`.
  - AST nodes are built with `dataclass(frozen=True, kw_only=True)` (`language/ast.py`, line 450).
  - Validation: `validate(schema, document_ast, rules: Collection[type[ASTValidationRule]] | None, max_errors, hide_suggestions)`. `ValidationRule`, `ASTValidationRule` and `specified_rules` are all exported.
- **Evidence:** https://pypi.org/pypi/graphql-core/json ; https://files.pythonhosted.org/packages/0c/13/03fb01b3581134cc30d7dd3fb8a9c429267574ace881a9e72c2f57896ee9/graphql_core-3.3.0-py3-none-any.whl (`graphql/__init__.py`, `execution/execute.py`, `validation/validate.py`, `language/ast.py`)
- **Fix:** None. The depth rule should be passed as `rules=[*specified_rules, DepthRule]`, since passing `rules` replaces the default set.
- **Severity:** -

### 4. `info.path.key` is the response key
- **Status:** Verified. The executor builds `field_path = Path(path, response_name, parent_type.name)` (`execution/executor.py`, lines 825 and 873), so `info.path.key` is the alias if one is present. `Path` is a `NamedTuple(prev, key, typename)`. List items get integer keys (`path.add_key(index, None)`), so the resolver only sees integers on list-item paths, never on field resolution.
- **Evidence:** graphql-core 3.3.0 wheel: `graphql/execution/executor.py`, `graphql/pyutils/path.py`
- **Fix:** None.
- **Severity:** -

### 5. Depth limit with `__schema` and `__type` exempt
- **Status:** The API is verified, but the exemption leaves introspection depth unbounded. graphql-core 3.3 ships `MaxIntrospectionDepthRule` and lists it as the only entry in `recommended_rules`. It is not in `specified_rules`, so it is not applied by default.
- **Evidence:** graphql-core 3.3.0 wheel: `graphql/validation/specified_rules.py` (line 130), `graphql/validation/rules/max_introspection_depth_rule.py`
- **Fix:** AD-10: "Validation uses `specified_rules + recommended_rules + DepthRule`, so `MaxIntrospectionDepthRule` bounds the introspection subtrees that the depth rule exempts."
- **Severity:** Low

### 6. Custom scalars
- **Status:** Verified, with a new API. `GraphQLScalarType.__init__` still accepts `serialize`, `parse_value` and `parse_literal`. 3.3 adds `coerce_output_value`, `coerce_input_value`, `coerce_input_literal` and `value_to_literal`, which are the GraphQL.js 17 names. If both are given, the legacy argument wins.
- **Evidence:** graphql-core 3.3.0 wheel: `graphql/type/definition.py` (lines 658-690)
- **Fix:** Add a Conventions/Scalars note: "Implement scalars with the 3.3 `coerce_*` and `value_to_literal` hooks. Do not mix them with the legacy names."
- **Severity:** Low

### 7. cryptography Fernet + HKDF at "the version Frappe v16 pins"
- **Status:** Verified. Frappe v16 pins `cryptography~=50.0.0`; the latest is 50.0.2, released 2026-09-30. In 50.0.2, `cryptography.hazmat.primitives.kdf.hkdf.HKDF` exists (Rust-backed), and `cryptography.fernet` has `Fernet.decrypt(token, ttl=None)` and `MultiFernet`. Frappe already imports `Fernet` in `frappe/utils/password.py`.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/pyproject.toml (line 40) ; https://pypi.org/pypi/cryptography/json ; https://raw.githubusercontent.com/pyca/cryptography/50.0.2/src/cryptography/hazmat/primitives/kdf/hkdf.py ; https://raw.githubusercontent.com/pyca/cryptography/50.0.2/src/cryptography/fernet.py
- **Fix:** Stack: write "`cryptography~=50.0` (inherited from Frappe v16; do not declare a separate pin)".
- **Severity:** -

### 8. "Fernet (AEAD)"
- **Status:** The wording is inaccurate. Fernet is AES-128-CBC with HMAC-SHA256 (encrypt-then-MAC). It is authenticated encryption, but it has no associated-data input, so it is not an AEAD in the strict sense. The spine's binding of user, filter and order therefore has to live inside the payload, which is what AD-8 already does.
- **Evidence:** https://raw.githubusercontent.com/pyca/cryptography/50.0.2/src/cryptography/fernet.py
- **Fix:** Reword to "Fernet (authenticated encryption)". Optionally enforce the 24-hour TTL with Fernet's native `decrypt(token, ttl=86400)` instead of a hand-written `iat` check. Keep `iat` only if it is needed for logging.
- **Severity:** Low

### 9. HKDF from the "site encryption key", with current and previous `kid`
- **Status:** The key source is verified. There is **no** `frappe.get_encryption_key`. The function is `frappe.utils.password.get_encryption_key()`. It returns `frappe.local.conf.encryption_key` from `site_config.json`, and **if the key is missing it generates one and writes it to site_config** (a side effect). Frappe keeps exactly one key, with no previous-key or rotation concept: `decrypt()` simply throws on `InvalidToken`. So the previous `kid` in AD-8 has nothing in Frappe to derive from.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/utils/password.py (lines 189-231)
- **Fix:** In AD-8, name the call `frappe.utils.password.get_encryption_key()` (adapter only). Define `kid` as a DocWeave-managed epoch: HKDF `info = f"docweave-cursor-v1:{kid}"`, where `kid` is an integer stored in DocWeave Settings and rotated by an admin action. The current and previous epoch then map to `MultiFernet([k_cur, k_prev])`. State that a change to the site `encryption_key` invalidates all cursors, which returns `BAD_CURSOR` and is acceptable.
- **Severity:** Medium-Low

### 10. ruff 0.14.10 matches Frappe v16
- **Status:** Verified. Frappe v16's `.pre-commit-config.yaml` pins `astral-sh/ruff-pre-commit` at `rev: v0.14.10`, and ruff 0.14.10 is on PyPI (released 2025-12-18). The latest is 0.17.2.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/.pre-commit-config.yaml (line 25) ; https://pypi.org/pypi/ruff/json
- **Fix:** None.
- **Severity:** -

### 11. frappe-bench 5.31.0
- **Status:** Verified. It was released 2026-06-16 and requires Python >=3.10. 5.31.1 (2026-10-23) is the latest. Choosing the soaked 5.31.0 is reasonable.
- **Evidence:** https://pypi.org/pypi/frappe-bench/json
- **Fix:** None. Optionally allow `>=5.31.0,<6`.
- **Severity:** -

### 12. MariaDB 11.8
- **Status:** Verified. `check_compatible_versions()` warns below 10.6 and above 11.8 ("not yet tested"). Frappe's own server-test workflow uses the `mariadb:11.8` image.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/database/mariadb/setup_db.py (lines 102-117) ; https://raw.githubusercontent.com/frappe/frappe/version-16/.github/workflows/_base-server-tests.yml (line 84)
- **Fix:** None. Optionally note "Frappe v16 supports 10.6 to 11.8; CI uses 11.8".
- **Severity:** -

### 13. `@frappe.whitelist(methods=["POST"])`
- **Status:** Verified. The signature is `whitelist(allow_guest=False, xss_safe=False, methods=None)`, and the default is `["GET","POST","PUT","DELETE"]`. The methods are stored in `allowed_http_methods_for_whitelisted_func` and enforced by `handler.is_valid_http_method`. Frappe itself uses `@whitelist(methods=["POST", "PUT"])`.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/__init__.py (lines 439-470, 806) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/handler.py (line 99)
- **Fix:** None.
- **Severity:** -

### 14. `frappe.db.after_commit`
- **Status:** Verified. `Database.after_commit` is a `CallbackManager` (a deque with `add(func)`; `run()` pops until empty, so callbacks added during `run` also execute). `rollback()` calls `after_commit.reset()`. That is correct for AD-11, because a rolled-back Settings or DocType save does not bump. It also means DocWeave's own v1 transport rollback discards any after-commit callbacks a hook registered, which is the intended behaviour.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/database/database.py (lines 129-132, 1183-1215) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/utils/__init__.py (`CallbackManager`, line 1124)
- **Fix:** None. In AD-11, write the call as `frappe.db.after_commit.add(fn)` (a zero-argument callable).
- **Severity:** -

### 15. `frappe.clear_cache(doctype=...)`
- **Status:** Verified. The signature is `clear_cache(user=None, doctype=None)`. With `doctype`, it calls `clear_doctype_cache(doctype)` and `reset_metadata_version()`. That in turn clears the parent DocTypes of child tables and deletes Redis keys matching the wildcard `*{doctype}*`. Frappe's own handlers already call it: Property Setter `on_update`/`on_trash`, Custom Field `on_update`/`on_trash`, Custom DocPerm `on_update`, and Customize Form `save_customization`/`reset_layout`/`reset_customization`. DocWeave's extra call is redundant but harmless.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/cache_manager.py (lines 132-200, 297-346) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/custom/doctype/property_setter/property_setter.py ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/core/doctype/custom_docperm/custom_docperm.py
- **Fix:** None. Optionally drop DocWeave's own call to avoid a second wildcard key scan per bump.
- **Severity:** -

### 16. "Frappe's metadata version" in the fingerprint
- **Status:** It exists, but the spine does not give its exact name or location. Here they are:
  - Key `"metadata_version"` in **`frappe.client_cache`**.
  - Written by `frappe.cache_manager.reset_metadata_version()` (also re-exported as `frappe.reset_metadata_version`), which stores `frappe.generate_hash()`.
  - Reset on every `clear_cache(doctype=...)` and on every full clear. It therefore does catch the hook-less paths: `delete_property_setter(bypass_hooks=True)`, Customize Form "reset order", and `clear_removed_items`, which all call `clear_cache(doctype=)`.
  
  Caveats from `ClientCache`'s own docstring: it is "internal to Frappe Framework and is subjected to change without any notice", and you should not "expect sub-second invalidation guarantees across processes". The same Redis key can be read with `frappe.cache.get_value("metadata_version")`, with no local-copy staleness.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/cache_manager.py (lines 342-346) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/utils/redis_wrapper.py (`class ClientCache`, lines 472-500, 596-643)
- **Fix:** In AD-11, write: "the fingerprint includes `frappe.cache.get_value("metadata_version")` (Frappe's internal metadata hash, reset on every DocType cache clear); it is read through `frappe.cache` so there is no per-process lag". Keep the `schema_revision` counter as the primary signal, and add a test that would catch a rename in a future v16 minor.
- **Severity:** Low

### 17. `meta.get_masked_fields(parenttype=)` applies the DocPerm unmask setting
- **Status:** Verified, with a staleness hazard.
  - The signature is `get_masked_fields(self, parenttype=None)`. It returns `[]` for Administrator.
  - It computes `get_permlevel_access("mask", parenttype)` from `frappe.get_roles(session user)`, then returns deep copies of DocFields where `df.mask` is set and the permlevel is not unmasked.
  - It caches the result in `frappe.cache` under `masked_fields::{doctype}::{parenttype}::{user}`.
  - That key is cleared only by the DocType cache clear (the wildcard `*{doctype}*` delete). It is **not** cleared by `clear_user_cache(user)`, which runs when a user's roles change: `masked_fields` is not in `user_cache_keys`, and nothing in `user.py`, `role.py` or `permissions.py` touches it.
  - Consequence: if an admin removes a role that held the DocPerm `mask` (unmask) right, the user keeps seeing unmasked values, through Frappe qb and therefore through DocWeave, until some cache clear for that DocType. The reverse also happens: a newly granted unmask keeps returning placeholders.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/model/meta.py (lines 195-214, 731-739) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/cache_manager.py (lines 58-90, `clear_user_cache`) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/core/doctype/user/user.py
- **Fix:** In AD-5:
  - Compute the masked set fresh as `{df for df in meta.fields if df.mask and df.permlevel not in meta.get_permlevel_access("mask", parenttype, user=user)}`. `get_roles` is invalidated on role change.
  - Treat a field as `MASKED` if it is in **either** the fresh set or `get_masked_fields(...)`. The union is needed because qb masks with the cached set.
  - Add a negative test: "revoke unmask role → next request returns MASKED".
  - Document the upstream behaviour as a known Frappe limitation, and consider reporting it upstream.
- **Severity:** Medium

### 18. DocPerm unmask field name
- **Status:** Verified. The DocPerm (and Custom DocPerm) Check field is `mask`, labelled "Mask", under "Additional Permissions". The DocField-level flag that marks a field as maskable is also `mask`. `mask` is not in `std_rights` (round 1).
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/core/doctype/docperm/docperm.json ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/core/doctype/docfield/docfield.json
- **Fix:** None. If the spine ever names the field, call it "DocPerm `mask` (unmask)".
- **Severity:** -

### 19. Bump triggers: `Customize Form` and `DocPerm`
- **Status:** As doc_events, these two are dead.
  - **Customize Form** is `issingle=1` and is never saved. `save_customization`, `reset_to_defaults` and `reset_layout` are whitelisted document methods, called through `handler.run_doc_method`, which calls `doc.run_method(method)`. So `on_update`/`on_change` never fire. Only doc_events keyed by the method name (`"save_customization"`, etc.) fire. The module-level `reset_customization(doctype)` bypasses doc_events entirely.
  - **DocPerm** is `istable=1`. Child rows are written by `Document.update_child_table` through `d.db_update()` and `d.db_insert()`, which run no hooks. Changes arrive as the parent DocType's `on_update`.
  - All these paths call `frappe.clear_cache(doctype=)`, so the `metadata_version` fingerprint (finding 16) still catches them. No staleness results, only dead configuration.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/custom/doctype/customize_form/customize_form.py (lines 228-259, 630-712) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/custom/doctype/customize_form/customize_form.json ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/handler.py (line 331) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/model/document.py (lines 894-926, 1489-1511) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/core/doctype/docperm/docperm.json
- **Fix:** AD-11 triggers:
  - "DocWeave Settings, DocType, Custom Field, Property Setter, Custom DocPerm (`on_update`/`on_trash`); Customize Form via `save_customization`/`reset_to_defaults`/`reset_layout` method events. DocPerm is covered by DocType."
  - "Paths with no hook are covered by the `metadata_version` fingerprint."
  - Add the test from round 1 ("reset field order invalidates schema") and one for `reset_customization`.
- **Severity:** Low

### 20. Clearing `message_log` to suppress the envelope
- **Status:** Verified, and a better mechanism exists. `frappe.local.message_log` is a list that is reset per request. `utils/response.py` turns it into `_server_messages` (v1) or `messages` (v2) only inside `build_response`. **If a whitelisted method returns a werkzeug `Response`, `handler.handle` passes it through unchanged** (`if isinstance(data, Response): return data`), so none of `message`, `_server_messages` or `exc` is added. Exceptions that escape to `app.handle_exception` still produce Frappe's error envelope. v16 has no `frappe.clear_messages` in `__init__.py`.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/handler.py (lines 50-62) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/utils/response.py (lines 91-106, 190-220) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/__init__.py (lines 119, 167)
- **Fix:** AD-12: "The transport returns a `werkzeug.wrappers.Response` with the GraphQL JSON body and status. It catches every exception, so nothing reaches Frappe's handler. It also sets `frappe.local.message_log = []` defensively." That gives 400 and 403 without relying on `frappe.local.response["http_status_code"]`.
- **Severity:** Low

### 21. AD-1 allowlist completeness
- **Status:** Incomplete compared with the spine's own rules. Code outside `adapter/` must use names that are not on the allowlist:
  - `frappe.local.message_log` in `api.py` (AD-12). The allowlist has `local.request` and `local.response` only.
  - `frappe.client_cache` or `frappe.cache.get_value("metadata_version")` in `schema/cache.py` (AD-11). `cache` is listed, so the `frappe.cache` route is fine. `client_cache` is not.
  - `frappe.db.after_commit.add` is in a doc_events handler. If that handler lives in `schema/cache.py` it is allowed. `frappe.get_doc` and `frappe.get_single`, needed to read DocWeave Settings in `schema/` and `api.py`, are **not** listed.
- **Evidence:** spine AD-1 ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/__init__.py
- **Fix:** Add `local.message_log` (api.py only) and `get_single` or `get_cached_doc("DocWeave Settings")`. Note that `get_cached_doc` is banned outright, so pick `get_single` or carve out an exception. Use `frappe.cache` for `metadata_version`. Alternatively, route Settings reads through a small `config` port.
- **Severity:** Medium-Low (the boundary test, which is the NFR-1 gate, would fail on day one or force ad-hoc exceptions)

### 22. Fieldtype map
- **Status:** Partly wrong. The v16 `DocField.fieldtype` options are: Autocomplete, Attach, Attach Image, **Attachment Gallery**, Barcode, Button, Check, Code, Color, Column Break, Currency, Data, Date, Datetime, Duration, Dynamic Link, Float, Fold, Geolocation, Heading, HTML, **HTML Editor**, Icon, Image, Int, JSON, Link, Long Text, Markdown Editor, Password, Percent, Phone, Read Only, Rating, Section Break, Select, Signature, Small Text, Tab Break, Table, Table MultiSelect, Text, Text Editor, Time. `model/__init__.py` and the MariaDB `type_map` also define **`Long Int`** (`bigint(20)`). Every type the spine names exists. The problems:
  - **Rating → String is wrong.** It is stored as `decimal(3,2)`, a 0 to 1 fraction, and listed in `data_fieldtypes`. Map it to `Float`.
  - **Duration → Int (seconds) loses data.** It is stored as `decimal(21,9)` seconds. Map it to `Float` or `Decimal`.
  - **Long Int is missing.** A bigint overflows GraphQL `Int` (32-bit). Map it to `String` or a `BigInt` scalar. It can appear in app or core DocType JSON even though the Customize Form picker does not offer it.
  - **HTML Editor is missing.** It is a data fieldtype (`longtext`). Map it to `String`.
  - **Attachment Gallery is missing from the exclusions.** It is in `no_value_fields` and `display_fieldtypes`. Exclude it.
  - Minor: "Section" means `Section Break`. `Int` is `int(11)` signed and fits GraphQL `Int`, which is fine. `Float`/`Currency`/`Percent` are all `decimal(21,9)`: mapping `Float` to GraphQL `Float` while mapping Currency to `Decimal` is a deliberate choice, so state it.
  - Add a builder rule: an unknown fieldtype fails the build (or is excluded and logged), so a future v16 fieldtype cannot crash the build or silently become `String`.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/core/doctype/docfield/docfield.json ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/model/__init__.py (lines 8-80) ; https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/database/mariadb/database.py (lines 175-210)
- **Fix:** Replace the row with: "Data, Select, Small Text, Text, Long Text, Text Editor, Markdown Editor, HTML Editor, Code, Read Only, Attach, Attach Image, Color, Barcode, Phone, Autocomplete, Icon → String. Int → Int. Long Int → String (BigInt-safe). Check → Boolean. Float, Rating (0 to 1), Duration (seconds) → Float. Currency, Percent → Decimal. Date, Datetime, Time as is. JSON, Geolocation → JSON. Excluded: Password, Button, HTML, Heading, Image, Section Break, Column Break, Tab Break, Fold, Signature, Attachment Gallery. Unknown fieldtype → excluded and logged."
- **Severity:** Medium

### 23. Table MultiSelect
- **Status:** Verified. It is in `table_fields = ("Table", "Table MultiSelect")` and `no_value_fields`.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/model/__init__.py
- **Fix:** None.
- **Severity:** -

### 24. `after_uninstall` deletes `docweave:*` Redis keys
- **Status:** Verified. `installer.remove_app` runs `app_hooks.after_uninstall` after `frappe.db.commit()` and a **full `frappe.clear_cache()`**. The full clear already deletes every site key not covered by `persistent_cache_keys`, so the hook is belt-and-braces. It also runs `client_cache.erase_persistent_caches()` afterwards.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/installer.py (lines 455-485)
- **Fix:** Keep the hook, which costs nothing. Note in Operations that `bench clear-cache` and `migrate` (full clear) also wipe `docweave:schema_revision`. That is safe only because of finding 25.
- **Severity:** Low

### 25. `schema_revision` random initialization
- **Status:** Plausible, but the initialization race is not covered. After a full `clear_cache()` wipes the key, several workers can each initialize a different random value. Then two LRU generations and a lost bump become possible.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/cache_manager.py (lines 310-316)
- **Fix:** AD-11: "Initialize with Redis `SET NX` (`frappe.cache.set(..., nx=True)` or equivalent), then `INCR`." Alternatively, register `docweave:*` under the `persistent_cache_keys` hook so a full clear does not wipe it.
- **Severity:** Low

### 26. `IntegrationTestCase`
- **Status:** Verified. `frappe/tests/__init__.py` does `from .classes import *`, and the class is in `frappe/tests/classes/integration_test_case.py`.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/tests/__init__.py
- **Fix:** None. As round 1 noted, schema-revision tests must commit or call `frappe.db.after_commit.run()` explicitly.
- **Severity:** -

### 27. CI `bench run-tests --app docweave`
- **Status:** Verified with caveats. `run-tests` has `--app`, `--doctype`, `--module-def`, `--case`, `--test`, `--module`, `--profile`, `--coverage`, `--skip-before-tests`, `--junit-xml-output` and `--lightmode`, and `--skip-test-records` is deprecated. It needs a site (`get_site(context)`), and it refuses to run unless `allow_tests` is set in site config or the `CI` environment variable is set. GitHub Actions sets `CI=true`. `run-parallel-tests --app` also exists.
- **Evidence:** https://raw.githubusercontent.com/frappe/frappe/version-16/frappe/commands/testing.py (lines 287-360, 385-397)
- **Fix:** Stack/CI: `bench --site test_site run-tests --app docweave --junit-xml-output ...`. Note that local devcontainer runs need `bench --site <site> set-config allow_tests true`.
- **Severity:** Low

## Round-1 follow-up

- POST-only endpoint, the frappe floor, the graphql-core 3.3 note, the ruff/Frappe parity, the MariaDB version, the MCP note and the `metadata_version` fingerprint have all been taken up in the rewrite. Their remaining precision issues are findings 13, 1, 3, 10, 12 and 16 above.
- Round-1 item 11 (a full `clear_cache` wipes the Redis revision) is now handled implicitly by random initialization. Finding 25 covers the remaining race.

## Not independently verifiable

- How quickly `metadata_version` invalidation reaches other workers at runtime (finding 16). Reading through `frappe.cache` avoids the question.
- Frappe Cloud behaviour.
- Runtime masking on the exact release. This remains gated by `test_masking.py`.
