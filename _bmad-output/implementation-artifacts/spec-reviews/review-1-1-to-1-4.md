# Adversarial review: specs 1.1 to 1.4

- Date: 2026-11-01
- Reviewed against: `planning-artifacts/epics.md` (Stories 1.1 to 1.4), `ARCHITECTURE-SPINE.md`, and the source code. Frappe is v16.53.0 (`~/frappe-bench/apps/frappe`, `git describe` = v16.53.0). ERPNext is v16.52.1. graphql-core 3.3.1 isn't installed in the bench, so the wheel was downloaded from PyPI into /tmp and read there (`~=3.3.0` resolves to 3.3.1). GitHub Actions claims could not be checked against source. They are marked where they matter.
- Each spec gets its own verdict. Severity: high = the spec as written produces wrong or failing behaviour, or leaves a binding rule unenforced; medium = a real gap that the implementer would have to decide alone; low = a correctness detail worth fixing before approval.

## Summary

| Spec | Verdict | High | Medium | Low |
| --- | --- | --- | --- | --- |
| 1.1 Installable app, CI, boundary guard | needs human decision | 1 | 3 | 4 |
| 1.2 Settings and access gate | needs human decision | 2 | 1 | 3 |
| 1.3 Schema generation | needs human decision | 1 | 3 | 3 |
| 1.4 Schema cache and invalidation | needs human decision | 1 | 2 | 2 |

All AC from the epics are covered by a task, an AC or an I/O row, or are raised as an Open Question. These are 1.2 OQ1 to OQ3, 1.3 field collision, and 1.4 build lock. The existing Open Questions are real intent gaps, and each offers fair options. Continuity is consistent: `SettingsView`, `GraphQLRequest`, `_run`, `build_schema`, `SchemaBuildError` and `hooks.py` are introduced before they are used, with the same names. Two problems recur across specs and are reported in each spec they affect: rules that the architecture or the source makes mandatory but the spec doesn't state (1.1 F1, 1.3 F1), and test rows that the real Frappe behaviour makes fail (1.2 F2, 1.3 F2, 1.4 F1).

---

## Spec 1.1: Installable app with CI and boundary guard

**Verdict: needs human decision** (F1). The rest are fixes.

Verified as correct: the boilerplate pyproject (flit_core, `requires-python = ">=3.14"`, dynamic version), the pre-commit revs (pre-commit-hooks v6.0.0, ruff v0.14.10), `modules.txt` plus the `.frappe` marker (`frappe/utils/boilerplate.py:160-188,339-363,859-889`), and the test walker, which only collects `test_*.py` (`frappe/testing/discovery.py:45-66`). `allow_tests` or `CI` is required (`frappe/commands/testing.py:350-355`). The image's stage writes `db_host`, `redis_cache` and `redis_queue` before it exits (`.devcontainer/post-create.sh:232-252`). pre-commit 4.3.0 exists on PyPI.

### F1 (high): the checker's policy inside `adapter/` is undefined, and either reading breaks something
- **Section:** Boundaries ("The checker is an allowlist: any `frappe.*` name not listed for a file fails"), I/O row "Adapter rules", Design Notes "Scope".
- **Evidence:** AD-1 lists names for *outside* `adapter/`. Inside it, AD-1 only restricts `get_doc`/`has_permission` (permission.py) and `get_single` (settings.py), and says "Data is read only through `_authorized_query`". The spine's own flowchart (spine l.44) and later stories need many more names in the adapter: `frappe.qb.get_query` (AD-2), `frappe.get_meta`, `frappe.utils.password.get_encryption_key` (AD-8), and Frappe's permitted-fields and mask helpers (AD-5).
- **Problem:** if the allowlist also applies inside `adapter/`, nothing there is listed, so 1.5 can't be written without changing the checker. If the adapter is instead only checked against the banned names (a denylist), then `frappe.db.get_values`, `frappe.db.get_single_value`, `frappe.db.count`, `frappe.qb.from_(...).run()` and `frappe.get_doc` in other adapter files (only partly covered) all pass. AD-1's "data is read only through `_authorized_query`" then goes unenforced, and that is the NFR-1 gate this story exists for. The spec leaves the choice to the implementer.
- **Fix:** add an Open Question. Option A: a per-file allowlist inside `adapter/` too. 1.1 fixes the list for `frappe_v16.py` (`frappe.qb.get_query`, `frappe.get_meta`, ...), and each later story extends it explicitly. This is a spine amendment through correct-course. Option B: inside `adapter/`, use a denylist of the banned names plus every `frappe.db.*` and `frappe.qb.*` name except `frappe.qb.get_query`, which is only allowed in `_authorized_query`'s module. This is weaker, but needs no list maintenance. Either way, add matrix rows for `frappe.db.get_values` and `frappe.qb.from_` inside `adapter/frappe_v16.py`.

### F2 (medium): the spine's import-direction rules have no checker and no negative test
- **Section:** Boundaries ("The boundary rules are AD-1, word for word").
- **Evidence:** spine l.26 says `core/` "imports nothing from DocWeave or Frappe", and spine l.47 says "Arrows are the only allowed import directions. `execution` and `schema` never import `adapter`." AD-1's "everywhere outside `adapter/`" list would let `core/` use `frappe.get_meta`, which contradicts l.26. The Tests convention requires a negative test for every v1 rule.
- **Fix:** add import-direction checks to `test_boundaries.py`: `core/` has no `frappe` or `docweave` imports, `schema/` and `execution/` don't import `docweave.adapter`, and relative imports are resolved. Add matrix rows (`core/x.py: import frappe` fails; `schema/x.py: from ..adapter import settings` fails). If "AD-1 word for word" is meant to exclude this, raise it as an Open Question rather than drop it silently.

### F3 (medium): the dynamic-access rule is too narrow and leaves easy bypasses
- **Section:** I/O row "Dynamic access" ("bare `x = frappe`").
- **Evidence:** an assignment is only one way to let the module object escape. `helper(frappe)`, `return frappe`, `[frappe][0].get_all`, `sys.modules["frappe"].get_all` and `vars(frappe)["get_all"]` all avoid an `Attribute` chain rooted in an alias without assigning it to a name.
- **Fix:** state the rule in AST terms: any `Name` load of a frappe alias that isn't the root (`value`) of an `Attribute` node fails. Also, any access to `sys.modules` and any call to `getattr`, `vars` or `__import__` whose argument is a frappe alias or the string `"frappe"` fails. Say that `import frappe.x.y` counts as using `frappe.x.y` on the import line, the same as `from frappe.x import y`. Add one matrix row per form.

### F4 (medium): the CI site differs from the codespace site (no setup wizard), so later ERPNext-fixture tests can fail only in CI
- **Section:** Tasks, `scripts/ci-test.sh`.
- **Evidence:** `post-create.sh:326-349` completes the ERPNext setup wizard (Company, fiscal year), but `ci-test.sh` only runs `new-site` and `install-app`. `bench run-tests --app docweave` runs only DocWeave's own `before_tests` hooks (`frappe/testing/environment.py:191-195`, `get_hooks("before_tests", app_name=app)`), so ERPNext's setup never runs in CI. Sales Order fixtures (1.5 onwards) need a Company.
- **Fix:** `ci-test.sh` runs the same `setup_complete` call with the same arguments as post-create.sh, or DocWeave's `hooks.py` gets `before_tests = ["erpnext.setup.utils.before_tests"]`. Either way, codespace and CI sites end up equivalent. Add a 1.1 AC: in CI, `frappe.is_setup_complete()` is true on the test site.

### F5 (low): "Frappe's own CI sets `character_set_server`" is wrong
- **Section:** Code Map, last bullet.
- **Evidence:** Frappe's `.github/workflows/_base-server-tests.yml:83-89` sets no charset. ERPNext does it (`erpnext/.github/helper/install.sh:303-304`). Frappe also creates the database with an explicit charset (`frappe/database/db_manager.py:28`), so the step is harmless belt-and-braces.
- **Fix:** attribute it to ERPNext's CI and keep the step.

### F6 (low): `install-app.sh` has no stated default site
- **Section:** Tasks (`scripts/install-app.sh [SITE]`, and `devcontainer.json` calls it with no argument).
- **Fix:** state the default (`${DOCWEAVE_SITE:-dev.localhost}`, matching post-create.sh:33) and the behaviour when the site doesn't exist (stop with a message).

### F7 (low): details of the PR image build and the services
- **Section:** Tasks, `ci.yml`.
- **Evidence and fix:** (a) the PR-built image must be built with `docker/setup-buildx-action` and `build-push-action` with `load: true`, the same as `dev-image.yml:90-102`, or `docker run docweave-dev:pr` won't find it. Say so. (b) This story's own `devcontainer.json` edit matches `^\.devcontainer/`, so this PR builds the image twice (once in `dev-image.yml`, once in `ci.yml`). Accept that, or note it in the README. (c) The Redis services have no healthcheck, and `ci-test.sh` only waits for MariaDB. Wait for both Redis services with `redis-cli ping`, as post-create.sh:148-156 does. (d) Not verified against source: `job.services.mariadb.network`, and the network aliases equal to the service IDs, are from GitHub's documentation. Run `getent hosts mariadb redis-cache redis-queue` as an early step in `ci-test.sh` so a wrong assumption fails clearly.

### F8 (low): the spec doesn't say how type-only imports are treated
- **Section:** Design Notes "Name resolution".
- **Evidence:** `schema/builder.py` will want `from frappe.model.meta import Meta` for type hints. Under the allowlist that fails, even under `if TYPE_CHECKING:`.
- **Fix:** decide it explicitly. Either type hints must be string annotations with no import, or imports under `if TYPE_CHECKING:` are exempt. Add a matrix row either way.

---

## Spec 1.2: DocWeave Settings and the access gate

**Verdict: needs human decision** (the three existing OQs and F2). F1 and F3 are fixes.

Verified as correct: `SYSTEM_USER_ROLE = "Desk User"`, and `get_roles` adds it only for System Users and gives Administrator every role (`frappe/permissions.py:35,542-570`, `is_system_user` at l.914). The Role "Desk User" exists on the site. A returned werkzeug `Response` passes through untouched (`frappe/handler.py:46-63`, `frappe/api/__init__.py:64`), and a wrong method gets `throw_permission_error` (`handler.py:99-110`). Guests are refused by `is_whitelisted` (`frappe/__init__.py:479-490`). An unsaved Single loads its JSON defaults (`frappe/model/document.py:494-500`). Has Role is `istable` with one `role` Link in list view. `frappe.call` drops form keys that aren't parameters (`frappe/__init__.py:1171-1193`), so `graphql()` with no parameters is safe.

### F1 (high): an unexpected exception is logged inline and then rolled back, with local variables included
- **Section:** Boundaries ("An unexpected exception becomes 200 with `INTERNAL`, logged through `frappe.log_error`"); Tasks `api.py` ("A `finally` block runs `frappe.db.rollback()`").
- **Evidence:** `frappe.utils.error.log_error` inserts the Error Log in the current transaction unless `defer_insert=True` (`frappe/utils/error.py:85-88`). The `finally` rollback then discards it. By default it also records `frappe.get_traceback(with_context=True)` (`error.py:61`), which includes local variables. AD-12 (spine l.219) requires `frappe.log_error(..., defer_insert=True)` written after the rollback. AD-15 (l.255) requires `with_context=False`.
- **Fix:** collect the error during execution. In `finally`, roll back first, then call `frappe.log_error(title, frappe.get_traceback(with_context=False), defer_insert=True)`. Add a test: after an `INTERNAL`, a deferred Error Log exists (flush the deferred insert queue in the test) and holds no local variables.

### F2 (high): the "Malformed body: not JSON → 400" row can't happen for JSON requests
- **Section:** Boundaries (400 for "not JSON, ..."), I/O row "Malformed body".
- **Evidence:** Frappe parses every `application/json` body in `init_request` → `make_form_dict` (`frappe/app.py:214,338-356`), before DocWeave runs. Invalid JSON raises `frappe.DataError` ("Invalid request body"), a `ValidationError` that returns Frappe's own error envelope (`exc_type`, `_server_messages`), not 400 GraphQL JSON. A top-level JSON scalar raises "Invalid request arguments", and a top-level JSON list is moved to `form_dict["data"]`. Only bodies whose Content-Type isn't JSON reach `graphql()` unparsed. The row as written becomes a failing test, and AD-12's "malformed requests get 400" doesn't hold for the commonest client mistake.
- **Fix:** extend OQ3, the same class of problem as Guest and GET. Option A: accept Frappe's envelope when a JSON body fails to parse, and document it. 400 GraphQL JSON then applies only to a body that parses but has the wrong shape, or to a non-JSON Content-Type. Option B: require clients to send `Content-Type: application/graphql+json` or `text/plain`, which Frappe doesn't parse, and parse it in DocWeave. This is uniform, but non-standard for clients. Then split the I/O row into "JSON with a non-string `query`" (400, ours) and "invalid JSON with application/json" (Frappe's envelope, or whatever the OQ decides).

### F3 (medium): the AD-12 read-only guarantee has no negative test
- **Section:** I/O matrix and `test_access.py`.
- **Evidence:** AD-12 (l.218-220) says "discards uncommitted writes made by hooks". The Tests convention requires a negative test for every v1 AD. No row checks that a write inside `_run` is discarded.
- **Fix:** add a row: `_run` (patched) inserts a ToDo, and after the HTTP request the ToDo doesn't exist. Add a second row for the exception path: the insert happens, then `_run` raises, and the ToDo still doesn't exist.

### F4 (low): `frappe.throw` → `INTERNAL` disagrees with AD-15's map
- **Section:** I/O row "Queued messages" (throw → `INTERNAL`).
- **Evidence:** AD-15 (l.252-255) maps `ValidationError` (which `frappe.throw` raises) to `VALIDATION`, with a sanitized message.
- **Fix:** say that the 1.2 catch-all is temporary and that 1.5's `adapter/errors.py` replaces it, so this test's expected code changes then. Alternatively, raise a non-`ValidationError` exception in this test.

### F5 (low): virtual DocTypes aren't rejected as exposed rows
- **Section:** Boundaries (exposed-DocType validation).
- **Evidence:** a DocType with `is_virtual=1` has no table, so `frappe.qb.get_query` (AD-2) can't read it. Frappe itself filters these out (`frappe/model/meta.py:978`, `{"issingle": 0, "is_virtual": 0}`). AD-14 doesn't mention them.
- **Fix:** an Open Question (reject at save, or allow and accept failure later). Rejecting is the obvious choice, but it extends AD-14, so it is the human's call.

### F6 (low): error body shapes aren't pinned
- **Section:** Boundaries / I/O.
- **Fix:** state the exact body for 403 and 400, `{"errors":[{"message": "...", "extensions":{"code":"NOT_EXPOSED"}}]}`, with no `data` key on a 403. 1.3 already relies on `extensions.code`.

---

## Spec 1.3: Schema generation from Exposed DocTypes

**Verdict: needs human decision** (the three existing OQs). F1 to F4 are fixes.

Verified as correct: graphql-core 3.3.1 has `extensions` on types and fields, `coerce_output_value` with `serialize` as the deprecated alias (`graphql/type/definition.py:481-502,655-690`), `execute_sync` (`graphql/execution/execute.py:468`), and `print_schema`. A Query type with no fields is rejected ("must define one or more fields", `graphql/type/validate.py:355-358`), so OQ3 is real. `str(Decimal(100).normalize())` gives `'1E+2'`, so OQ2 is real. `Meta.get_table_fields` is at `frappe/model/meta.py:244`, and `get_system_timezone` is at `frappe/utils/data.py:389`, re-exported by `frappe.utils`. Sales Order has `customer` (Link Customer), `company` (Link Company), `items` (Table Sales Order Item) and `grand_total` (Currency).

### F1 (high): introspection is opened without `MaxIntrospectionDepthRule`
- **Section:** Tasks `execution/executor.py` ("run graphql-core's standard validation").
- **Evidence:** in graphql-core 3.3.1, `MaxIntrospectionDepthRule` is only in `recommended_rules` (`graphql/validation/specified_rules.py:130`). `validate()` defaults to `specified_rules` (`graphql/validation/validate.py:66-67`). AD-10 (l.178) says `__schema`/`__type` are "bounded instead by graphql-core's `MaxIntrospectionDepthRule`". 1.3 opens introspection to every allowed user, and the depth rules don't arrive until 2.4.
- **Fix:** validate with `(*specified_rules, *recommended_rules)`. Add a negative test: a deeply nested `__type { fields { type { ofType { ... } } } }` query returns `VALIDATION`.

### F2 (medium): the name-clash fixture "Foo Bar" plus "Foo-Bar" can't be created in Frappe
- **Section:** I/O row "Exposed name clash".
- **Evidence:** `validate_route_conflict` (`frappe/desk/utils.py:9-33`) slugs DocType names with `name.lower().replace(" ", "-")`. Both names become `foo-bar`, so the second DocType raises `NameError` on insert. Creating a DocType also commits mid-test, because of DDL through `frappe.db.sql_ddl` (`frappe/database/database.py:451-457`).
- **Fix:** use "Foo Bar" and "Foo_Bar". Their slugs differ (`foo-bar`, `foo_bar`), and both become `FooBar`. State that the fixture DocTypes are committed by DDL and must be deleted in `tearDownClass`.

### F3 (medium): the naming rule leaves out the spine's "lowercase the parts" step
- **Section:** Boundaries, first bullet.
- **Evidence:** the spine Names convention (l.281) says "lowercase the parts, then capitalize them". The spec only says PascalCase/camelCase after splitting. "BOM Item" becomes `BomItem` under the spine and probably `BOMItem` under a plain PascalCase reading. The snapshot tests would then lock in whichever one the implementer chose.
- **Fix:** copy the spine algorithm word for word, and add matrix rows: `BOM` → `Bom`, `UOM Conversion Detail` → `UomConversionDetail`, fieldname `po_no` → `poNo`.

### F4 (medium): generated names can collide with names that the Settings check doesn't cover
- **Section:** Boundaries (the collision check covers only exposed-vs-exposed DocTypes) and Design Notes.
- **Evidence:** (a) A DocType named "Query", "String", "Int", "Float", "Boolean", "ID", or a DocType whose name matches one of the spec's scalars (`Decimal`, `Long`, `Date`, `Datetime`, `Time`, `JSON`), produces a type that clashes with the root type or a scalar. graphql-core would reject the schema or silently use the wrong type. (b) Child types are generated from Table fields and aren't in the Settings check, so a child "Foo_Bar" next to an exposed "Foo Bar" collides. (c) A Link `x` produces `xDoc`, which collides with a real field `x_doc`.
- **Fix:** the builder raises `SchemaBuildError` naming both sources when any generated type name collides with another generated name or a reserved name. Settings validation rejects exposed DocTypes whose type name is reserved. Add matrix rows for (a), (b) and (c). For (c), defer to OQ1's decision, but see F6.

### F5 (low): the GraphQL types of the standard fields aren't stated
- **Section:** Boundaries, "Standard fields".
- **Fix:** state them: `owner: String`, `creation: Datetime`, `modified: Datetime`, `modifiedBy: String`, `docstatus: Int`, `idx: Int`. They feed the `print_schema` snapshots.

### F6 (low): OQ1's options don't cover collisions that involve no custom field
- **Section:** Open Questions, "Field-name collision".
- **Evidence:** the spine's alternative is to drop the custom field, but it says nothing about two standard fields colliding (`foo_bar` and `foo__bar` in a custom DocType), or a Link-derived `xDoc` colliding with a standard field `x_doc`.
- **Fix:** add to the second option what happens when neither side is custom, for example "fail the build in that case too", so the human decides the whole rule at once.

### F7 (low): the logging channel for build failures isn't named
- **Section:** Boundaries ("the failure is logged").
- **Fix:** say `frappe.logger("docweave")`, as 1.4 does, or the deferred `log_error` from 1.2 F1. An inline `frappe.log_error` would be lost to the rollback.

---

## Spec 1.4: Schema cache and invalidation

**Verdict: needs human decision** (the existing build-lock OQ). F1 to F3 are fixes.

Verified as correct: `after_commit` is a `CallbackManager` over a deque in `_functions` (`frappe/utils/__init__.py:1144-1170`). `commit()` runs it after the SQL commit, and `rollback()` resets it (`frappe/database/database.py:130,1176-1205`). `reset_metadata_version` writes through `frappe.client_cache` (`frappe/cache_manager.py:342-345`). The client cache stores under `RedisWrapper.make_key("metadata_version")` and pickles the value, so `frappe.cache.get_value("metadata_version", use_local_cache=False)` reads the same key (`frappe/utils/redis_wrapper.py:53-63,553-610`). `clear_cache(doctype=...)` resets it (`cache_manager.py:306-308`). Customize Form deletes Property Setters with `frappe.db.delete` and then calls `clear_cache(doctype=...)` (`frappe/custom/doctype/customize_form/customize_form.py:652-653`). `CustomDocPerm.on_update` exists (`frappe/core/doctype/custom_docperm/custom_docperm.py:37`), so its `doc_events` fire.

### F1 (high): the "Rolled back" row is wrong for DocType and Custom Field saves
- **Section:** I/O row "Rolled back" ("the same saves, then `frappe.db.rollback()` → revision unchanged; no rebuild").
- **Evidence:** `CustomField.on_update` calls `frappe.clear_cache(doctype=...)` and `frappe.db.updatedb(...)` (`custom_field.py:212-222`). `updatedb` runs DDL through `frappe.db.sql_ddl`, which **commits** first (`database.py:451-457`; also `frappe/database/schema.py:468`). DocType saves do the same. The `doc_events` hook runs after the controller's `on_update`, so the bump is queued after that commit and is then dropped by the test's rollback. The Custom Field nevertheless persists, and `clear_cache` has already reset `metadata_version`. The fingerprint therefore changes and the next request **does** rebuild. The row's "no rebuild" assertion fails, and the row implies a guarantee that doesn't hold.
- **Fix:** limit the rolled-back row to changes without DDL: Settings, a Property Setter on a non-schema property such as `label`, and Custom DocPerm. Add a separate row: "DocType or Custom Field save, then rollback: the change is committed by DDL; the revision may be unchanged, but the fingerprint differs and the next request rebuilds." This documents that the fingerprint, not the revision, covers changes that commit through DDL.

### F2 (medium): after `frappe.clear_cache()`, `INCR` creates revision 1, which breaks the random-start invariant and the "Migrate +1" row
- **Section:** Boundaries (SET NX random, then INCR), I/O rows "Migrate" and "Redis flushed", Design Notes on `after_migrate`.
- **Evidence:** a full `frappe.clear_cache()` deletes every site key except `persistent_cache_keys` (`cache_manager.py:309-316`, `frappe/hooks.py:555-560`), so `docweave:schema_revision` is deleted too. `bench migrate` calls `frappe.clear_cache()` in `setUp` (`frappe/migrate.py:88`), before the `after_migrate` hooks run (`migrate.py:208-211`). `bump_now`'s `INCR` on the now-missing key creates it as 1. Every migrate therefore resets the revision to 1. The randomness that makes old `(revision, fingerprint)` entries unreachable is lost, and "revision +1" isn't what happens after a real migrate.
- **Fix:** `_incr` and `bump_now` first make sure the key exists (`SET NX` with a random value), then `INCR`. Alternatively, use one Lua script or pipeline. Add a test: delete the key, call `bump_now`, and check that the value isn't 1 and differs from the value before the delete. As an alternative, add `docweave:*` to `persistent_cache_keys` and rely on `metadata_version` for clear-cache. This changes the Redis-flushed semantics, so it would be an OQ.

### F3 (medium): the per-process LRU key doesn't include the site
- **Section:** Approach and Tasks (`get_schema` over a 4-entry per-process LRU keyed by `(revision, fingerprint)`).
- **Evidence:** a single gunicorn worker serves every site on a multi-tenant bench. The spine's deployment map includes Frappe Cloud. Keys from different sites are distinct only because the revisions are random, which F2 shows isn't reliable, and a 4-entry LRU shared by N sites rebuilds constantly.
- **Fix:** add the site prefix `frappe.cache.make_key("")` (`db_name|`, inside AD-1's `frappe.cache` allowance) to the key. Bound the LRU per site, or size it as "a few entries per site". Add a test that two site keys don't evict each other, or at least that the key contains the site prefix.

### F4 (low): the dedup relies on the private `_functions`
- **Section:** Design Notes, "Per-transaction dedup".
- **Evidence:** `CallbackManager.__slots__ = ("_functions",)` is internal (`utils/__init__.py:1144`).
- **Fix:** keep it, but pin it with a test, the same way as `metadata_version`: assert that `hasattr(frappe.db.after_commit, "_functions")`, and that two saves in one transaction give +1.

### F5 (low): the behaviour when Redis is unavailable isn't specified
- **Section:** Tasks, `schema/cache.py`.
- **Evidence:** raw `set`, `get` and `incr` on `RedisWrapper` raise `redis.exceptions.ConnectionError`, while Frappe's own `get_value` and `set_value` suppress it (`redis_wrapper.py:76-77,113-116`).
- **Fix:** state the behaviour. Either build without caching and log a warning, or return `INTERNAL`. Add a matrix row.
