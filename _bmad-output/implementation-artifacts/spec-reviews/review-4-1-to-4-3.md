# Spec review: Stories 4.1, 4.2, 4.3

**Reviewer:** independent adversarial review · **Date:** 2026-11-01 · **Baseline:** `cd5c126`
**Inputs:** the three specs, `epic-4-context.md`, specs 1.1–1.7 for continuity (no Epic 2 specs exist yet), `epics.md` §2.3, §2.4, §4.1–4.3, `ARCHITECTURE-SPINE.md`, Frappe v16.53.0 source under `~/frappe-bench/apps/frappe`.
**graphql-core:** not installed in `~/frappe-bench/env`. I checked graphql-core claims against an extracted 3.3.1 copy (`/tmp/gqx/graphql`, `version.py:11`). Treat them as verified against 3.3.1 source, not against the bench env.

Severity scale: **High** = a leak of data, masked values or existence, a binding spine contradiction that nobody raised, or a defect that blocks a correct implementation. **Medium** = a wrong or missing contract that an implementer would otherwise decide silently, a test that cannot fail, or a wrong verification step. **Low** = a clarification or a small test gap.

## Summary

| Spec | Verdict | High | Medium | Low |
|---|---|---|---|---|
| 4.1 SDL export | **needs human decision** (its two Open Questions), then small fixes | 0 | 2 | 3 |
| 4.2 Error contract and request logging | **needs human decision** (its four Open Questions plus F4 and F6), then fixes | 4 | 6 | 3 |
| 4.3 Upgrade and uninstall lifecycle | **needs human decision** (its two Open Questions), then fixes | 0 | 3 | 5 |

Top three findings overall:
1. **4.2 F1 (High):** exceptions raised during graphql-core execution (in resolvers or scalar coercion) never reach the mapper. graphql-core sends `str(exc)` to the client, with no `INTERNAL` code and no Error Log entry.
2. **4.2 F2 (High):** an exception raised inside the `finally` (rollback, deferred flush) replaces DocWeave's `Response` with Frappe's error envelope. With System Settings at their defaults, a desk user then gets a traceback.
3. **4.2 F3 (High):** the spec has `schema/cache.py` call `adapter.errors.map_exception`, which breaks the spine's import directions (`schema` never imports `adapter`). Nobody raised this.

---

## Spec 4.1: SDL export

**Verdict: needs human decision.** The two Open Questions are real intent gaps with fair options. "Who may export" is the epics-versus-AD-12 conflict that `epic-4-context.md:39` already names. "Success body format" is a gap: AD-12 says "only the GraphQL JSON" and never considers a text body. AC coverage: epics AC1 (System Manager gets the SDL with descriptions and custom scalars) is covered by the matrix and AC 1. AC2 (non-System Manager or GET refused) is covered by the "GET" and "Not allowed" rows and the per-rule refusal task. Verified: `print_schema(schema) -> str` exists, prints descriptions, and skips built-in scalars and introspection types (`graphql/utilities/print_schema.py:42-111,211-213`). A GET gets Frappe's 403 through `throw_permission_error` (as cited in 1.2).

### F1. Medium: nobody clearly owns the `Query` cost-formula description
- **Section:** Boundaries "Never" (`spec-4-1:32`: "Only scalar and `Query` descriptions are added") versus Code Map (`spec-4-1:60`: the description "is promised to Story 2.4 … Check it is present; don't duplicate it"). AC 1 (`spec-4-1:73`) requires it.
- **Evidence:** Story 2.4's ACs (`epics.md:508-526`) never mention the SDL description. Only AD-10 does (`ARCHITECTURE-SPINE.md:183`). No 2.4 spec exists yet. If 2.4 is written straight from its ACs, 4.1's AC 1 fails, and 4.1's Code Map tells the implementer not to add the description.
- **Fix:** Pick one owner. Either 4.1 adds the `Query` description in `schema/builder.py`, built from the same constants `execution/rules.estimate_cost` uses, with a test that the text matches the formula. Or 2.4's spec gets an explicit task and AC, and 4.1 lists 2.4 as a hard dependency. Remove the contradiction between lines 32 and 60.

### F2. Medium: the "Who may export" options leave Administrator undefined
- **Section:** Open Questions, first bullet (`spec-4-1:49`).
- **Evidence:** `frappe.get_roles("Administrator")` returns every role (`permissions.py`, cited in `spec-1-2:60`). Under option 2 ("System Manager only, ignoring `enabled` and `allowed_roles`"), Administrator always passes, and `allow_administrator` is silently ignored. Under option 3 the combined order isn't stated. The human needs this to choose fairly.
- **Fix:** For each option, state how Administrator and `allow_administrator` are treated, and the check order. The task "one refused caller for each rule" should then include Administrator with `allow_administrator` off.

### F3. Low: the shared request helper has no defined shape
- **Section:** Code Map `docweave/api.py` (`spec-4-1:57`), Tasks (`spec-4-1:69`).
- **Evidence:** In 1.2, `graphql()` parses the body into a `GraphQLRequest` and returns 400 when the body is malformed (`spec-1-2:73`). `sdl` has no body, and 4.2 later needs the endpoint name in the log line (`spec-4-2:27`). The spec doesn't say which steps the helper runs for `sdl`.
- **Fix:** Name the helper and its signature, for example `_handle(endpoint: str, work: Callable[[SettingsView], tuple[body, status, mimetype]], parse_body: bool)`. Say that `sdl` ignores any body and never returns 400.

### F4. Low: the `JSON` scalar has no format text
- **Section:** Tasks, `scalars.py` (`spec-4-1:68`). The other five scalars get a format. `JSON` just says "`JSON`".
- **Fix:** Give the text, for example "Any JSON value, as stored in a Frappe JSON or Geolocation field", and assert it in the test.

### F5. Low: AC 2 can't be checked as written for a text body
- **Section:** AC 2 (`spec-4-1:74`): "no `_server_messages`, `exc` or `message` keys". A `text/plain` SDL body has no keys.
- **Fix:** After OQ 2 is decided, reword it. For text: the success body starts with a GraphQL definition, and the `Content-Type` is `text/plain; charset=utf-8`. For both formats: every error body is coded JSON with only `errors`.

---

## Spec 4.2: Error contract and request logging

**Verdict: needs human decision.** The four Open Questions are real. The "Log level" and "Query count" facts check out: `default_log_level = WARNING if _dev_server else ERROR` (`utils/logger.py:12`), the logger name is `"{module}-{site}"` with `propagate=False` (`utils/logger.py:68-81`), and Frappe has no production query counter (only the test-time `assertQueryCount` patch, `tests/classes/integration_test_case.py:122-138`). The class hierarchy is right: `DoesNotExistError(ValidationError)` (`exceptions.py:45`), `PermissionError(Exception)` (`:41`), `QueryTimeoutError(Exception)` (`:256`), `LinkValidationError` and `MandatoryError` are `ValidationError` subclasses. `log_error(title, message, ..., defer_insert=)` matches `utils/error.py:37-44`. AC coverage: epics AC1 (one log line) is covered, subject to F7 and F9. AC2 (no traceback, no locals) is covered, but the locals test is ineffective (F5). AC3 (a test per class) is covered. The leaks below are what keep this spec from being ready.

### F1. High: exceptions during graphql-core execution bypass the mapper and leak `str(exc)`
- **Section:** Boundaries, bullet 2 (`spec-4-2:25`: "Every path that can fail goes through the mapper: the adapter load, the schema build, and the transport's catch-all").
- **Evidence:** graphql-core catches exceptions from resolvers and leaf coercion and wraps them with `located_error`, whose message is `str(original_error)` (`graphql/error/located_error.py:57-59`, `graphql/execution/execute.py:1062-1069`, 3.3.1). The error goes into `ExecutionResult.errors` as a normal GraphQL error. The transport's catch-all never sees it, so there is no `INTERNAL` code, no generic message and no Error Log entry. The 1.5 resolver (sentinel → error) and the 1.3 `Decimal`/`Datetime` coercion both run in this phase. A `KeyError('<value>')` or a coercion error that quotes a value goes straight to the client. The log line's `codes=` would also miss these errors, or show them as uncoded.
- **Fix:** In `api.py` (not `execution/`, which can't import `adapter`), post-process `ExecutionResult.errors`. Any error whose `original_error` is set and is not a `DocWeaveError` goes through `map_exception`, and its message and extensions are replaced. Add matrix rows: a scalar whose `coerce_output` raises `KeyError("S3NT1NEL")`, and a resolver that raises. Expected: `INTERNAL`, generic message, sentinel absent from the body, one deferred Error Log entry.

### F2. High: an exception in the `finally` replaces the `Response` and can return a traceback
- **Section:** Boundaries, bullets 3–5 (`spec-4-2:26-28`). Only the logger is guarded ("A failure while logging never changes the response").
- **Evidence:** If `frappe.db.rollback()`, `frappe.log_error(...)` or `deferred_insert` raises inside `finally`, that exception replaces the function's return value. `deferred_insert` catches only `redis.exceptions.ConnectionError` (`deferred_insert.py:21-25`), so a `TimeoutError` or any other `RedisError` propagates. Frappe then calls `handle_exception` → `report_error`, which puts the traceback in `exc` when `is_traceback_allowed()` (`app.py:360-375`, `utils/response.py:39-58,68-78`). `allow_error_traceback` defaults to 1 (`system_settings.json:287-291`), so any System User gets the traceback, plus `_server_messages`. That breaks AD-12 (body is GraphQL JSON only) and AD-15 (no traceback reaches the client).
- **Fix:** Every step in the `finally` (rollback, `message_log` clear, deferred flush, log line) gets its own `try/except Exception`. A failure is reported only as a fixed `docweave` logger line with no exception text. Add tests that patch `frappe.db.rollback` and `frappe.log_error` to raise, and assert that the status and body are unchanged and the body has no `exc` key. This also hardens 1.2/1.5's `finally`; name that as a change to those stories.

### F3. High: `schema/cache.py` calling `map_exception` breaks the spine's import direction (not raised)
- **Section:** Code Map (`spec-4-2:66`: "`schema/cache.py` … on a failed build, `map_exception` records the deferred entry"), Tasks (`spec-4-2:75`: "route the build failure through the mapper").
- **Evidence:** `ARCHITECTURE-SPINE.md:47`: "Arrows are the only allowed import directions. `execution` and `schema` never import `adapter`." `map_exception` lives in `adapter/errors.py`.
- **Fix:** `schema/cache.py` raises (or re-raises `SchemaBuildError` from the cause). `api.py` catches the error around `get_schema` and calls `map_exception`. Add a boundary assertion, or a test, that `docweave/schema/**` has no `docweave.adapter` import.

### F4. High (needs human decision): the "Sanitized `VALIDATION` message" options misstate the risk, and `VALIDATION` is an existence oracle
- **Section:** Open Questions, third bullet (`spec-4-2:55`: option 1 "may echo a value the caller sent or can see").
- **Evidence:** `has_permission` hooks are called with no exception handling (`permissions.py:491-498`), and `frappe.throw` raises `ValidationError` by default. Stage 2 runs only for names Stage 1 found, which means only for documents that exist. A hook's `frappe.throw(f"... {doc.customer}")` therefore (a) puts a value from a document the caller can't read into the message, and (b) returns `VALIDATION` where a missing name returns `NOT_FOUND`. That breaks AD-15's "NOT_FOUND whether or not it exists" (`ARCHITECTURE-SPINE.md:250`). The same issue is raised for 1.5 as F1 in `review-1-5-to-1-7.md`. 4.2 is the story that hardens the map, and it doesn't address it.
- **Fix:** Rewrite the option text: Frappe messages can echo values the caller cannot see. Add the containment question explicitly: any exception from AD-4 Stage 2 (`adapter/permission.py`) is treated as "not readable", giving `NOT_FOUND`, and is logged as a deferred entry. This narrows AD-15 for one phase, so the human must approve it. Add a matrix row: a `has_permission` hook that does `frappe.throw` with a sentinel. Expected: `NOT_FOUND`, the same body as a missing name, and the sentinel absent from the body and the log line.

### F5. Medium: the locals test can't fail, because Frappe redacts a local named `secret`
- **Section:** I/O matrix row "Locals" (`spec-4-2:42`).
- **Evidence:** Frappe's traceback sanitizer blocks locals whose names contain `secret`, `key`, `token` and similar (`utils/__init__.py:340-357`). Even with `with_context=True` in developer mode, `secret="S3CR3T"` is printed as `********`. The test would pass even if locals were being recorded.
- **Fix:** Use a neutral name and value, for example `probe_value = "Z9-PROBE-7731"`. Assert that the value is absent from the Error Log `error` field and that no `Locals` section appears.

### F6. Medium (needs human decision): Error Log metadata stores the whole request body
- **Section:** Boundaries, bullet 3 (`spec-4-2:26`). Only "no locals" is required.
- **Evidence:** `log_error` always stores `metadata.form_dict = sanitized_dict(frappe.form_dict)` for HTTP requests (`utils/error.py:129-157`). For a JSON POST, `form_dict` is the parsed body (`app.py:338-351`): the GraphQL query text, `variables` (filter values, document names) and `after` cursors. `sanitized_dict` only blanks keys that contain `password`/`secret`/`token`/`key`/`pwd` (`utils/logger.py:115-134`). Error Log is readable only by System Manager, but this goes against the epic's "no … cursor ever reaches … the log", and against the purpose of diagnosing without leaking data.
- **Options for the human:** accept and document it (Error Log is admin-only; the query is the caller's own input) / blank `frappe.local.form_dict` before calling `log_error` in the `finally`. The second option needs AD-1 to allow `frappe.local.form_dict` in `api.py`, through correct-course.

### F7. Medium: "exactly one line" conflicts with other lines on the same logger
- **Section:** Boundaries, bullet 4, and AC 1 (`spec-4-2:27,80`). Code Map (`spec-4-2:66`: "in addition to 1.4's logger line").
- **Evidence:** 1.3 logs unknown fieldtypes once per build through `frappe.logger("docweave")` (`spec-1-3:28`), and 1.4 logs a failed build there (`spec-1-4:28`). A request that rebuilds the schema writes two or more lines, so the AC fails on the build-failure row of 4.2's own matrix.
- **Fix:** Define the invariant as "exactly one request line (the line that starts with `endpoint=`)". Alternatively, send build diagnostics to a different logger name (for example `frappe.logger("docweave_schema")`, which writes its own file). Have the test count request lines specifically.

### F8. Medium: the `log_error` call contract is underspecified, which can let locals in
- **Section:** Boundaries, bullet 3 (`spec-4-2:26`), and the deferred entry tuple `take_deferred() -> list[tuple[str, str]]` from 1.5.
- **Evidence:** `log_error` swaps title and message when the title contains `\n` (`utils/error.py:52-56`). If `message` is empty, it calls `frappe.get_traceback(with_context=True)` (`:58`). In developer mode, while an exception is propagating through the `finally`, that includes locals (`utils/__init__.py:317-331`).
- **Fix:** Require a fixed single-line title with no exception text (for example `"DocWeave INTERNAL"`) and a non-empty message (the `traceback.format_exception` text captured at mapping time). Add a test that the stored `error` has no `Locals`/`│` context block when developer mode is on.

### F9. Medium: the "malformed body → 400 plus one line" row can't happen for invalid JSON
- **Section:** I/O matrix row "Gate failure / malformed body" (`spec-4-2:46`), Boundaries, bullet 6 (`spec-4-2:29`).
- **Evidence:** For a request with `Content-Type: application/json` and an unparseable body, Frappe's `make_form_dict` throws `DataError` ("Invalid request body", HTTP 417) before DocWeave runs (`app.py:338-344`). The response is Frappe's envelope, and no DocWeave line is written. Only well-formed JSON with the wrong shape (for example `query` as an int), or a non-JSON content type, reaches DocWeave's 400. This is inherited from 1.2's "400 for a malformed body (not JSON …)" (`spec-1-2:27`).
- **Fix:** In both 4.2 and 1.2, state which malformed inputs reach DocWeave, and use one of them in the test. Add "invalid JSON with a JSON content type" to the "Guest and GET refusals" dependency: Frappe refuses it, and DocWeave writes no line.

### F10. Medium: the logging tests don't prove that the line appears in production, or that no request data is attached
- **Section:** Code Map (`spec-4-2:68`: "Tests capture with `assertLogs`"), OQ "Log level".
- **Evidence:** `assertLogs(name, level="INFO")` lowers the logger's level for the duration of the test. The test therefore passes under every "Log level" option, including the one where production writes nothing. Separately, `frappe.logger(module, with_more_info=True)` adds `SiteContextFilter`, which appends the sanitized `form_dict` (query, variables, cursors) to every record (`utils/logger.py:87-106`). The spec doesn't forbid it.
- **Fix:** Add a test, with `frappe.log_level` at `None` and `_dev_server` false, that asserts `frappe.logger("docweave").isEnabledFor(<chosen level>)` matches the chosen option. Require `frappe.logger("docweave")` with default arguments (no `with_more_info`), and add a negative test that the formatted record has no `Form Dict`.

### F11. Low: signature changes to earlier stories are implied but not named
- **Section:** Code Map (`spec-4-2:64-65`), Tasks (`spec-4-2:75`).
- **Evidence:** 1.5 fixes `execute(schema, request, adapter)` and `FrappeV16Adapter(user, settings)` (`spec-1-5:59,75`). 4.2 gives both a `stats` object but doesn't give the new signatures.
- **Fix:** State `execute(schema, request, adapter, stats: RequestStats | None = None)` and `FrappeV16Adapter(user, settings, stats: RequestStats | None = None)`, and list them as changes to 1.5.

### F12. Low: the "Query count" options miss an option
- **Section:** OQ, first bullet (`spec-4-2:53`).
- **Fix:** Add a third option: drop the query count from the production line (the epics' AC is amended) and keep exact counts test-only, through `IntegrationTestCase.assertQueryCount`-style patching, which AD-3's test already needs.

### F13. Low: the deferred Error Log entry is lost when Redis is down
- **Section:** Boundaries, bullet 3.
- **Evidence:** On `ConnectionError`, `deferred_insert` iterates the record dict's keys as if they were records (`deferred_insert.py:21-25`). `insert_record` then fails and writes the failure through `frappe.logger()`, the root `frappe` logger with `with_more_info=True`, which appends `form_dict` (`deferred_insert.py:51-56`).
- **Fix:** Document this Frappe limitation in the README, or check `frappe.cache.connected()` and, if Redis is down, write a fixed `docweave` line with no message instead.

---

## Spec 4.3: Upgrade and uninstall lifecycle

**Verdict: needs human decision.** Both Open Questions are real and fairly put: v1 has no earlier Settings shape to patch, and AD-1 forbids writes in `docweave/patches/`. These Frappe claims check out:
- `remove_app` order: `in_uninstall` (`installer.py:457`), drop DocTypes, `remove_from_installed_apps`, commit, `clear_cache()` (`:472-476`), then `after_uninstall` (`:478-479`).
- `get_attr` refuses calls for apps that aren't installed (`__init__.py:1132-1136`).
- Single DocTypes are deleted with `ignore_on_trash=True`, so no DocWeave `on_trash` bump fires (`installer.py:509-511`, `model/delete_doc.py:175`). Their `Has Role` child rows are deleted too (`delete_doc.py:258-278`).
- `make_key` returns `<db_name>|key` and `delete_keys(prefix)` deletes `<db_name>|prefix*` (`redis_wrapper.py:53-63,152-158`).
- `migrate` runs pre patches, model sync, post patches, then `after_migrate` (`migrate.py:145-210`).
- The pinned tags are at `post-create.sh:24-25`.

AC coverage: epics AC1 (patches, then a revision bump) is covered for the mechanism, subject to OQ 1. AC2 (every `docweave:*` key deleted) is covered. AC3 (README tags) is covered with a drift test.

### F1. Medium: the migrate verification step is wrong. The revision is not "higher after than before"
- **Section:** Verification (`spec-4-3:84`).
- **Evidence:** `SiteMigration.setUp` calls a full `frappe.clear_cache()` (`migrate.py:84-88`). That deletes every key for the site except `persistent_cache_keys` (`cache_manager.py:310-315`), including `docweave:schema_revision`. Afterwards the revision is either `INCR` on a missing key, which gives `1`, or a fresh `SET NX` random value. Neither is reliably higher than the old random 63-bit value.
- **Fix:** Expect the revision to **differ** from the value before the migrate. Add a test row: "full `frappe.clear_cache()` then `bump_now()` → revision differs and is not a small counter" (see F2).

### F2. Medium: "a reinstall starts from a new random revision" depends on 1.4 behaviour that 1.4 doesn't specify
- **Section:** Boundaries, bullet 4 (`spec-4-3:27`). Continuity with `spec-1-4:24,67`.
- **Evidence:** 1.4 creates the key with `SET NX` only on read (`current_revision()`), and bumps with a raw `INCR` (`_incr`, `bump_now`). After an uninstall, a migrate (F1) or any full `clear_cache`, the next bump runs `INCR` on a missing key and starts at `1, 2, …`. The same small values then repeat across cache clears and reinstalls. That isn't the random start AD-11 relies on so that a worker's LRU entry from before can't match.
- **Fix:** Have 4.3 (or 1.4) require that `_incr` and `bump_now` call `SET NX <random>` before `INCR`, and list this as a behaviour change to 1.4. Test: delete the key, call `bump_now()`, and assert the value is greater than 2^32.

### F3. Medium: the manual uninstall check passes without the hook, and the Code Map leaves out why
- **Section:** Code Map, `installer.py` (`spec-4-3:62`). Manual checks (`spec-4-3:87`).
- **Evidence:** `remove_app` runs a full `frappe.clear_cache()` before `after_uninstall` (`installer.py:476`), and that already deletes every `<db_name>|*` key. An empty `redis-cli --scan` after uninstall is therefore no evidence that `delete_all_keys` works.
- **Fix:** State this in the Code Map. Keep the hook, because the spine requires it and it protects keys that might later be added to `persistent_cache_keys`. Rely on the unit tests that call `delete_all_keys()` directly as the proof. Reword the manual check so it doesn't claim to verify the hook.

### F4. Low: the "never fails the uninstall" error handling is narrower than the rule
- **Section:** Boundaries, bullet 2, Tasks (`spec-4-3:25,70`), matrix row "Redis down".
- **Evidence:** `get_keys` and `delete_value` already swallow `ConnectionError` (`redis_wrapper.py:152-172`), so `delete_keys` never raises it. The matrix row can only be reached by mocking. `TimeoutError` and other `RedisError`s are not caught, so they would fail `bench uninstall-app` after the DocTypes are already dropped.
- **Fix:** Catch `redis.exceptions.RedisError` (or `Exception`) and write a fixed logger line. Make the test patch `delete_keys` to raise `TimeoutError`.

### F5. Low: retained records aren't listed
- **Section:** Boundaries "Never" (`spec-4-3:32`).
- **Evidence:** DocWeave Settings has `track_changes` (`spec-1-2:25`), so `Version` rows with `ref_doctype="DocWeave Settings"` survive the uninstall, as do the `Patch Log` rows. The epic's "never leaves stale state" goal makes these worth a decision.
- **Fix:** List them next to Error Log as intentionally kept, and mention them in the README's uninstall steps. Or have the human decide whether to delete them.

### F6. Low: a release policy is decided silently, and the supported range is missing
- **Section:** Tasks, README (`spec-4-3:73`).
- **Evidence:** The rule "a patch that changes Settings is at least a minor release" appears in neither the spine nor the epics (`ARCHITECTURE-SPINE.md:371`: "semantic versioning" only). The spine's supported range `>=16.53.0,<17` (`ARCHITECTURE-SPINE.md:299`) isn't in the README task.
- **Fix:** Mark the semver detail as a proposal for the human to confirm, or drop it. Have the README state the supported range alongside the tested tags. The upgrade steps should include fetching the new code and `bench restart`, not only `bench migrate`.

### F7. Low: the patch-list test and patch placement need more detail
- **Section:** I/O row "Patch list" (`spec-4-3:40`), Tasks (`spec-4-3:72`).
- **Evidence:** `patches.txt` lines may be `execute:<code>` or carry a `finally:` prefix (`patch_handler.py`, `run_all`). These aren't importable modules. A Settings patch that writes a newly added field has to sit in `[post_model_sync]`, because `[pre_model_sync]` runs before the DocType JSON is synced (`migrate.py:145-153`).
- **Fix:** Have the test either forbid `execute:` and `finally:` entries or handle them. State that Settings patches go in `[post_model_sync]`.

### F8. Low: the README drift test doesn't say how it finds the repo root
- **Section:** I/O row "README drift" (`spec-4-3:46`).
- **Fix:** Resolve `README.md` and `.devcontainer/post-create.sh` from `frappe.get_app_path("docweave", "..")` (the repo root, symlinked by `install-app.sh`). Skip the test with a clear reason if either file is missing, which happens in a wheel install.
