---
title: 'Schema cache and invalidation'
type: 'feature'
created: '2026-11-01'
status: 'draft'
baseline_commit: 'cd5c12665210c90e70229a728c76326a8c6e0bfe'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 1.3 rebuilds the schema on every request. Nothing yet decides when a cached schema has gone stale after Settings, DocType, customization or permission changes (FR-1, FR-2, AD-11).

**Approach:** Cache the built schema in a per-process LRU keyed by `(revision, fingerprint)`. The revision is the Redis integer `docweave:schema_revision`, bumped after commit by `doc_events` and by `after_migrate`. The fingerprint catches the metadata changes that fire no hooks.

## Boundaries & Constraints

**Always:**
- The revision is created with `SET NX` as a random 63-bit integer and bumped with `INCR`. Bumps from `doc_events` run only through `frappe.db.after_commit`, so a rolled-back change never bumps. At most one bump is queued per transaction.
- Triggers are `on_update` and `on_trash` of DocWeave Settings, DocType (which covers its DocPerm rows), Custom Field, Property Setter and Custom DocPerm, plus `after_migrate`.
- The fingerprint hashes Settings `modified`, the meta `modified` of each exposed DocType and of each child DocType it reaches, and Frappe's `metadata_version`. A test pins that `metadata_version` key.
- Once the revision has changed, the previous schema is never served. The schema is per site, never per user.
- A failed build is logged through `frappe.logger("docweave")` and returns `INTERNAL`. A failed build is never cached.
- `frappe.db.after_commit` and `frappe.clear_cache` appear only in `hooks.py` and `schema/cache.py` (AD-1).

**Never:**
- No per-user or per-language cache keys. Don't read Settings or meta outside `adapter/settings.py` and `frappe.get_meta`.
- Don't clear Frappe's caches from DocWeave. No `after_uninstall` cleanup (Story 4.3).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Warm | two requests, no change | one build | N/A |
| Hooked change | save Settings, a DocType, a Custom Field, a Property Setter or a Custom DocPerm, then commit | revision +1; next request rebuilds | N/A |
| Rolled back | the same saves, then `frappe.db.rollback()` | revision unchanged; no rebuild | N/A |
| Hook-less change | Customize Form deletes a Property Setter, which resets `metadata_version` | fingerprint differs; rebuild | N/A |
| Migrate | `after_migrate` runs | revision +1 | N/A |
| Redis flushed | revision key missing | re-created with `SET NX` at a fresh random value; next request rebuilds | N/A |
| Two users | Administrator, then a Sales User | the same cached schema object | N/A |
| Build fails | `build_schema` raises | 200 with `INTERNAL`; the next request retries the build | logged |

</frozen-after-approval>

## Open Questions

- **Concurrent build lock.** The epics (1.4 AC 4) require a Redis lock so that only one worker builds while the others wait or reuse its result. The spine lists "Schema build lock" under v2. Options: build the lock now and move it into v1 through a spine amendment (one build per revision across workers, but adds a lock timeout, waiter behaviour and a failure mode when Redis is slow) / leave the lock in v2 and drop AC 4 from the epics, letting each worker that misses build its own copy (simplest and still correct, but a burst after a change builds N times in parallel).

## Code Map

- `docweave/api.py` (created in 1.2, wired in 1.3) -- `_run` calls `build_schema(settings)`. Here that becomes `get_schema(settings)`.
- `docweave/schema/builder.py` (created in 1.3) -- `build_schema(settings) -> GraphQLSchema` and `SchemaBuildError`. Reuse it; don't change it.
- `docweave/core/types.py` (created in 1.2) -- `SettingsView.modified` and `.exposed_doctypes`.
- `docweave/hooks.py` (created in 1.1, metadata only) -- add `doc_events` and `after_migrate`.
- `~/frappe-bench/apps/frappe/frappe/database/database.py:130-132,1183-1215` -- `after_commit` is a `CallbackManager` with `.add(fn)`. `rollback()` resets it, which gives the rolled-back row of the matrix.
- `~/frappe-bench/apps/frappe/frappe/cache_manager.py:342-345` -- `reset_metadata_version()` writes `metadata_version` through `frappe.client_cache`. The `ClientCache` docstring (`utils/redis_wrapper.py:472`) says the same key can be read through `frappe.cache`. Read it with `frappe.cache.get_value("metadata_version", use_local_cache=False)`, so it stays inside AD-1's `frappe.cache` allowance.
- `~/frappe-bench/apps/frappe/frappe/utils/redis_wrapper.py:39-90` -- `RedisWrapper` subclasses `redis.Redis`. Use `make_key` for the site prefix, then raw `set(..., nx=True)`, `get` and `incr`.

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/schema/cache.py` -- `current_revision()`, `bump_revision(doc=None, method=None)` (queues the module-level `_incr` on `frappe.db.after_commit` unless it is already queued), `bump_now()` for `after_migrate`, `fingerprint(settings)`, and `get_schema(settings)` over a small per-process LRU (for example 4 entries).
- [ ] `docweave/hooks.py` -- `doc_events` for the five DocTypes calling `docweave.schema.cache.bump_revision`; `after_migrate = ["docweave.schema.cache.bump_now"]`.
- [ ] `docweave/api.py` -- `_run` uses `get_schema`.
- [ ] `docweave/tests/test_schema_cache.py` -- the matrix. Count builds by wrapping `build_schema` with `unittest.mock`. Commit with cleanup for the after-commit cases. The `metadata_version` test asserts that `frappe.clear_cache(doctype="Sales Order")` changes the value DocWeave reads.

**Acceptance Criteria:**
- Given a cached schema, when an admin adds Customer to the exposed DocTypes and saves, then the next introspection shows `Customer` without a restart.
- Given the package, when `test_boundaries.py` runs, then `frappe.db.after_commit` passes in `schema/cache.py` and fails if moved to `schema/builder.py`.

## Design Notes

- `after_migrate` bumps immediately, without waiting for a commit, because migrate gives no guarantee about a later commit.
- Per-transaction dedup: `CallbackManager` is a plain deque (`frappe/utils/__init__.py:1146`), so check `_incr in frappe.db.after_commit._functions` before adding. `rollback()` clears the deque. Don't use `frappe.flags` or `frappe.local` state, which AD-1 doesn't list.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.

## Implementation Notes

## Spec Change Log

## Review Triage Log
