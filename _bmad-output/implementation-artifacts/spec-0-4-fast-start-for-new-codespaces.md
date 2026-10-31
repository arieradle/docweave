---
title: 'Fast start for new codespaces'
type: 'chore'
created: '2026-10-31'
status: 'in-review'
baseline_commit: '73462cd3ef922ce93beacc35a39916e80a327961'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-0-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A new codespace runs the full install: `bench init`, getting ERPNext, building assets and creating the site. That takes many minutes, so recreating a codespace is slow.

**Approach:**
- Publish a prebuilt dev image to GitHub Container Registry with the bench (Frappe v16.53.0, ERPNext v16.52.1, Python and Node dependencies) already in it, and use it in the devcontainer.
- Create the site in `onCreateCommand`, so Codespaces prebuilds capture it.
- Add a GitHub Actions workflow that rebuilds the image when the pinned versions change.

## Boundaries & Constraints

**Always:**
- One source of truth for pinned versions: the constants at the top of `.devcontainer/post-create.sh`. The image build and the workflow read them from there.
- Setup stays idempotent and never destroys on doubt (Story 0.0's safety rules). A codespace without the image, or with an existing bench volume, still works.
- The image holds no site and no database. Dev credentials stay as documented dev-only values.
- Image tags name both versions: `frappe-v16.53.0-erpnext-v16.52.1`.
- Pin every action and base image to an exact version or digest.

**Decision (visibility):** the image is public. GHCR makes a new package private on first publish, so the README tells the human to set the package to public once, in its settings.

**Decision (rollout):** two steps. First, push the Dockerfile, the workflow, the script changes and the README, keeping the devcontainer on the base image, so GitHub builds and publishes. Second, after the human confirms that the image exists and is public, switch `docker-compose.yml` to the image.

**Never:**
- Install DocWeave, or change Frappe or ERPNext source.
- Change repository settings or package settings from here. The README tells the human what to enable.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| New codespace, image available | Empty volumes | Bench volume is seeded from the image; setup skips `bench init` and `get-app`; creates the site | N/A |
| Prebuild | Prebuild runs `onCreateCommand` | Site created during the prebuild; a codespace from it starts with `dev.localhost` ready | N/A |
| Snapshot without database | Bench volume has `sites/dev.localhost`, its database is missing in MariaDB | The orphaned site folder is moved aside (kept, not deleted) and the site is created again | Logs what was moved and why |
| Existing volumes from before the image | Bench built by Story 0.0's script | Adopted as today; no rebuild | Version drift still stops with a message |
| Version bump | Pinned constants changed and pushed to `main` | Workflow builds and publishes the image tagged with both versions | Build failure fails the workflow |

</frozen-after-approval>

## Code Map

- `.devcontainer/post-create.sh` -- the setup script. Its constants (`FRAPPE_TAG`, `ERPNEXT_TAG`, `BENCH_VERSION`, `UV_VERSION`) are the version pins. It already adopts an existing bench (sentinel `~/frappe-bench/.docweave-bench-ready`, or `apps/frappe` plus `sites/apps.txt`), so a volume seeded from the image skips `bench init` and `get-app`. It needs:
  - a `DOCWEAVE_STAGE=image` mode that stops after `get-app` and skips the rtk and service-wait steps (no services at build time). `set-config -g` still runs: it only writes `common_site_config.json`.
  - the orphaned-site handling: `site_config.json` exists but its `db_name` is absent from MariaDB
- `.devcontainer/Dockerfile` -- new.
  - `FROM` the same pinned base digest as `docker-compose.yml`.
  - Install Node 24.22.1 and Yarn 1.22.22, the versions in use today. The Node feature isn't applied during `docker build`, but `bench init` needs Node.
  - Run `post-create.sh` in image stage as `vscode`.
  - The bench venv binds to a uv-managed Python 3.14.9 in `~/.local/share/uv`, so it exists inside the image (changed during implementation; see Implementation Notes).
- `.devcontainer/docker-compose.yml` -- `app.image` switches to `ghcr.io/arieradle/docweave-dev:frappe-v16.53.0-erpnext-v16.52.1`, pinned by digest (rollout step 2). Docker seeds an empty named volume (`frappe-bench`) from the image's `/home/vscode/frappe-bench`.
- `.devcontainer/devcontainer.json` -- `onCreateCommand` runs `post-create.sh`. `postCreateCommand` reruns it: it's idempotent (about 8 s) and covers a prebuild snapshot without the database. The Node and Python features stay.
- `.github/workflows/dev-image.yml` -- new.
  - Triggers: `push` to `main` on `.devcontainer/Dockerfile` or `.devcontainer/post-create.sh`, plus `workflow_dispatch`.
  - Reads the tags from `post-create.sh`.
  - Builds with Buildx and pushes to GHCR with `GITHUB_TOKEN` (`packages: write`), tagged with both versions.
- `README.md` -- sections on enabling prebuilds, image access, and the two-step version bump: bump the pins, the workflow publishes, then update the compose tag, which makes prebuilds refresh.
- Not available here: Docker and the `gh` CLI. The image build can't run in this container; it is verified by the workflow run on GitHub.

## Tasks & Acceptance

**Execution:**
- [x] `.devcontainer/post-create.sh` -- add `DOCWEAVE_STAGE=image`; add orphaned-site handling (move aside, recreate) -- image build and snapshot recovery
- [x] `.devcontainer/Dockerfile` -- base digest, Node and Yarn, the image stage as `vscode` -- the prebuilt bench
- [x] `.github/workflows/dev-image.yml` -- build and publish on version changes -- rebuilds on bumps
- [x] `.devcontainer/devcontainer.json`, `.devcontainer/docker-compose.yml` -- `onCreateCommand`; image switch per the rollout decision -- fast start
- [x] `README.md` -- prebuilds, image access, version bump procedure -- the human's settings steps

**Acceptance Criteria:**
- Given the image is published, when a new codespace starts, then setup does not clone or install Frappe or ERPNext.
- Given prebuilds on `main`, when a codespace is created from a prebuild, then `dev.localhost` is ready without a site install, or is recreated automatically when the snapshot lacks the database.
- Given a version bump pushed to `main`, then the workflow publishes an image tagged with both versions.

## Implementation Notes

- Implemented directly in this session (no implementation subagent).
- **Python.** The existing venv was bound to the Python feature's interpreter, which a `docker build` doesn't have (features apply after the Dockerfile). The bench Python is now uv-managed, pinned to 3.14.9, the newest CPython uv 0.13.5 can download (3.14.10 isn't available to it). `--no-bin` keeps uv from putting a `python3.14` shim ahead of the feature on PATH. This codespace's venv was healthy and untouched.
- **Orphaned sites** go to `~/frappe-bench/orphaned-sites/`, not inside `sites/`, so bench never treats them as sites.
- **Local tests (this container, no Docker):**
  - full rerun: exit 0 in 9–12 s
  - image stage: stops before services and the site, 2 s
  - an unknown stage value: exit 1
  - orphaned site on a throwaway `orphan.localhost`: created, database dropped, rerun moved the folder aside and recreated the site with ERPNext on a new database; the test site was removed afterwards and `dev.localhost` restored as the default
- **Workflow run `41247348743`** (`eecaa98`): success in about 4.5 minutes. The image `ghcr.io/arieradle/docweave-dev:frappe-v16.53.0-erpnext-v16.52.1` is linux/amd64, 0.97 GB compressed, with a 572 MB layer from the image-stage setup.
- **Visibility.** Contrary to the spec's assumption, the package was readable anonymously right after the first publish (pull token plus manifest returned 200). It took the public repository's visibility, so no manual step was needed. The README says so.
- **Rollout step 2:** `docker-compose.yml` now uses the image.
- **Not verified here:** a new codespace from the image, and prebuilds. Both need the human: enabling prebuilds in repository settings, and creating a codespace.

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Evidence | Route |
|---|---------|---------|----------|-------|
| 1 | Image tag mutable; republished on every script change; compose not pinned by digest | medium | The workflow pushes the same tag on any trigger path | patch (compose pinned by digest; README: update tag and digest together) |
| 2 | Tag omits other image inputs (Python, bench, uv, Node, base) | medium | Those inputs change the image under one tag | patch (covered by the digest pin; README covers every image change) |
| 3 | Manual run on another branch overwrites main's tag | medium | `workflow_dispatch` had no branch guard | patch (`if: github.ref == 'refs/heads/main'`) |
| 4 | Image pushed without a smoke test | medium | Build then push | patch (load, check bench, imports and no site, then push) |
| 5 | Actions pinned to tags, not SHAs | low | Job has `packages: write` | patch (SHA pins with version comments) |
| 6 | Recovery block: no step name, unclear failures, `db_name` unescaped in SQL | medium | KeyError or mariadb failure fell to the ERR trap | patch (own step, `die` with messages, `db_name` validated; tested) |
| 7 | Two recoveries in one second nest folders | low | `mv` into an existing directory | patch (`.$$` suffix, `mv -T`) |
| 8 | `DOCWEAVE_SITE` undocumented and unvalidated | low | New variable | patch (header comment, regex; tested with `../evil`) |
| 9 | Node feature floating `24` vs image Node 24.22.1 | low | Two Nodes could differ | patch (feature pinned to 24.22.1) |
| 10 | onCreate plus postCreate run setup twice; rtk downloaded twice | low | Both hooks run on a normal create | patch (rtk skipped when already at the pin; README explains the rerun) |
| 11 | README Reset outdated; no prebuild check; no orphan cleanup advice; amd64 only undocumented | low | README text | patch |
| 12 | Gap between bump push 1 and 2 breaks new codespaces | medium | Old image, new pins means version drift | patch (README warns, with a workaround) |
| 13 | Spec Code Map out of date (Python binding, `set-config`, digest) | low | Implementation diverged | patch (Code Map updated) |
| 14 | Recovery path has no automated test | medium | No shell or CI test harness | defer |
| 15 | Nothing checks the compose tag against the pins | medium | Two-push design makes a mismatch intended between pushes | defer |
| 16 | Multiple `FRAPPE_TAG=` lines would break tag extraction | low | Needs a malformed script | rejected |
| 17 | arm64 / multi-arch build | low | Codespaces is amd64; documented | rejected (documented) |

## Verification

**Commands:**
- `bash -n .devcontainer/post-create.sh` -- expected: no syntax errors
- `bash .devcontainer/post-create.sh` (in this container) -- expected: exit 0 in seconds, every step skipped, as in Story 0.0
- The orphaned-site path, simulated on a throwaway site: create `orphan.localhost`, drop its database, rerun the site logic -- expected: the folder is moved aside and the site is recreated
- The workflow run on GitHub (after the rollout push) -- expected: success, and the tagged image in GHCR

**Manual checks (if no CLI):**
- A new codespace from the image (human): the setup log shows no `bench init` and no `get-app`.
