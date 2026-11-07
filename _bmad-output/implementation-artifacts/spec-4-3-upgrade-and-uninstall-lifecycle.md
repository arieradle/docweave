---
title: 'Upgrade and uninstall lifecycle'
type: 'feature'
created: '2026-11-01'
status: 'draft'
baseline_commit: 'cd5c12665210c90e70229a728c76326a8c6e0bfe'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing yet ensures that an upgrade applies Settings changes and invalidates the schema, that an uninstall removes DocWeave's Redis state, or that a release says which Frappe and ERPNext tags it was tested on (NFR-2).

**Approach:** Use Frappe's own lifecycle. `patches.txt` (with its `[pre_model_sync]` and `[post_model_sync]` sections) holds Settings patches. 1.4's `after_migrate` bump invalidates the schema. A new `after_uninstall` hook deletes every site-scoped `docweave:*` Redis key. The README gets a compatibility and release section, kept in sync with the pinned tags by a test.

## Boundaries & Constraints

**Always:**
- Uninstall deletes keys only for the current site (`frappe.cache.delete_keys("docweave:")`, which is prefixed with the site's `db_name`). Other sites' keys and non-DocWeave keys survive.
- The cleanup is idempotent and never fails the uninstall: a missing key or an unreachable Redis is ignored.
- `after_migrate` stays `docweave.schema.cache.bump_now` (1.4) and runs after the patches, so the first request after a migrate rebuilds.
- A reinstall starts from a new random revision (`SET NX` in 1.4), so no worker serves a schema cached before the uninstall.
- The README states the tested tags (Frappe v16.53.0, ERPNext v16.52.1), the semantic-versioning rule, upgrade and uninstall steps, and AD-5's admin note: clear the DocType cache after granting or revoking unmask.
- Only `frappe.cache` is used outside `adapter/` (AD-1).

**Never:**
- Don't delete Error Log entries, log files or Frappe's own caches. Frappe drops DocWeave's DocTypes itself during uninstall.
- No version bump or release tag here. No `before_uninstall` hook.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Migrate | `bench migrate` | DocWeave patches run once each (Patch Log), then the revision is bumped | N/A |
| Patch list | every `patches.txt` entry | imports and has a callable `execute` | test fails, naming the entry |
| Uninstall | `docweave:schema_revision` and `docweave:x` set for this site | both deleted | N/A |
| Other keys | `<other_db>|docweave:x` and this site's `docweave_x` | survive | N/A |
| Twice | the cleanup runs again | no error | N/A |
| Redis down | `delete_keys` raises `ConnectionError` | uninstall continues | ignored |
| Reinstall | install again, then a request | new random revision; fresh build | N/A |
| README drift | the README's tags differ from `FRAPPE_TAG` / `ERPNEXT_TAG` in `.devcontainer/post-create.sh` | test fails | N/A |

</frozen-after-approval>

## Open Questions

- **A patch in the first release.** v1 is the first release, so no earlier Settings shape needs migrating. Options: ship `patches.txt` with both sections and no entries, and prove the mechanism with the list test plus a manual migrate (nothing to maintain; the "patches apply" AC is only checked for the mechanism) / ship one idempotent patch that rewrites limits below 1 to their defaults (exercises a real patch now; it is a write to Settings that may never be needed).
- **AD-1 for patches.** A patch must write Settings (for example `frappe.reload_doc`, `frappe.db.set_single_value`), and AD-1 allows neither outside `adapter/`; `docweave/patches/` is inside the checker's scope. Options: amend AD-1 through correct-course to allow named write calls in `docweave/patches/**` only (patches run in migrate, never on a request) / patches call a writer in `adapter/settings.py` (no spine change, but the read-only adapter gains a write path).

## Code Map

- `docweave/hooks.py` (created in 1.1, `doc_events` and `after_migrate` added in 1.4) -- add `after_uninstall`.
- `docweave/patches.txt` (created in 1.1 from the `bench new-app` template) -- keep both section headers.
- `docweave/schema/cache.py` (created in 1.4) -- `current_revision`, `bump_now`, and the `docweave:schema_revision` key through `make_key`. Add the cleanup here so the key prefix lives in one module.
- `README.md` (1.1 added a "DocWeave app" section) -- add the compatibility and release section.
- `.devcontainer/post-create.sh:24-25` -- `FRAPPE_TAG`, `ERPNEXT_TAG`. Read only.
- `~/frappe-bench/apps/frappe/frappe/installer.py:459-485` -- `remove_app` sets `flags.in_uninstall`, drops the app's DocTypes, removes it from installed apps, commits, `clear_cache()`, then runs `after_uninstall`. `frappe.get_attr` (`__init__.py:1132`) then refuses `docweave.*` calls from other workers.
- `~/frappe-bench/apps/frappe/frappe/utils/redis_wrapper.py:53,152-172` -- `make_key` gives `<db_name>|key`; `delete_keys(prefix)` deletes `<db_name>|prefix*`.
- `~/frappe-bench/apps/frappe/frappe/modules/patch_handler.py:101-130` -- `get_patches_from_app("docweave")` parses both sections.
- `~/frappe-bench/apps/frappe/frappe/migrate.py:145-210` -- patches, model sync, then `after_migrate`.

## Tasks & Acceptance

**Execution:**
- [ ] `docweave/schema/cache.py` -- `delete_all_keys()`: `frappe.cache.delete_keys("docweave:")`, ignoring Redis connection errors.
- [ ] `docweave/hooks.py` -- `after_uninstall = ["docweave.schema.cache.delete_all_keys"]`.
- [ ] `docweave/patches.txt` (and `docweave/patches/` if the first question ships a patch) -- per the two questions.
- [ ] `README.md` -- "Compatibility and releases": tested tags, semver (a patch that changes Settings is at least a minor release), upgrade (`bench migrate`), uninstall (`bench --site <site> uninstall-app docweave`), and the unmask cache note.
- [ ] `docweave/tests/test_lifecycle.py` -- the matrix. Hook registration through `frappe.get_hooks(..., app_name="docweave")`. Keys set through the raw `frappe.cache` client and cleaned up in `tearDown`. The reinstall row is the manual check below.

**Acceptance Criteria:**
- Given hooks are loaded, when `after_migrate` and `after_uninstall` are listed for docweave, then they name `bump_now` and `delete_all_keys`.
- Given the package, when `test_boundaries.py` runs, then it passes under whichever rule the AD-1 question chooses.

## Verification

**Commands:**
- `cd ~/frappe-bench && bench --site dev.localhost run-tests --app docweave` -- expected: all pass.
- `bench --site dev.localhost migrate` -- expected: succeeds; the revision read through `current_revision()` is higher after than before (model sync can add `doc_events` bumps).

**Manual checks:**
- On a throwaway site: install, make a request, uninstall with `--yes --no-backup`; `redis-cli -h redis-cache --scan --pattern '<db_name>|docweave:*'` is empty. Reinstall: the first request rebuilds the schema.

## Implementation Notes

## Spec Change Log

## Review Triage Log
