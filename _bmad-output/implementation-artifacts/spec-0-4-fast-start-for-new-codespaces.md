---
title: 'Fast start for new codespaces'
type: 'chore'
created: '2026-10-31'
status: 'in-progress'
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
  - a `DOCWEAVE_STAGE=image` mode that stops after `get-app` and skips the rtk, service-wait and `set-config` steps (no services at build time)
  - the orphaned-site handling: `site_config.json` exists but its `db_name` is absent from MariaDB
- `.devcontainer/Dockerfile` -- new.
  - `FROM` the same pinned base digest as `docker-compose.yml`.
  - Install Node 24.22.1 and Yarn 1.22.22, the versions in use today. The Node feature isn't applied during `docker build`, but `bench init` needs Node.
  - Run `post-create.sh` in image stage as `vscode`.
  - The bench venv binds to `/usr/bin/python3.14`, as today.
- `.devcontainer/docker-compose.yml` -- `app.image` switches to `ghcr.io/arieradle/docweave-dev:frappe-v16.53.0-erpnext-v16.52.1` (rollout step 2). Docker seeds an empty named volume (`frappe-bench`) from the image's `/home/vscode/frappe-bench`.
- `.devcontainer/devcontainer.json` -- `onCreateCommand` runs `post-create.sh`. `postCreateCommand` reruns it: it's idempotent (about 8 s) and covers a prebuild snapshot without the database. The Node and Python features stay.
- `.github/workflows/dev-image.yml` -- new.
  - Triggers: `push` to `main` on `.devcontainer/Dockerfile` or `.devcontainer/post-create.sh`, plus `workflow_dispatch`.
  - Reads the tags from `post-create.sh`.
  - Builds with Buildx and pushes to GHCR with `GITHUB_TOKEN` (`packages: write`), tagged with both versions.
- `README.md` -- sections on enabling prebuilds, image access, and the two-step version bump: bump the pins, the workflow publishes, then update the compose tag, which makes prebuilds refresh.
- Not available here: Docker and the `gh` CLI. The image build can't run in this container; it is verified by the workflow run on GitHub.

## Tasks & Acceptance

**Execution:**
- [ ] `.devcontainer/post-create.sh` -- add `DOCWEAVE_STAGE=image`; add orphaned-site handling (move aside, recreate) -- image build and snapshot recovery
- [ ] `.devcontainer/Dockerfile` -- base digest, Node and Yarn, the image stage as `vscode` -- the prebuilt bench
- [ ] `.github/workflows/dev-image.yml` -- build and publish on version changes -- rebuilds on bumps
- [ ] `.devcontainer/devcontainer.json`, `.devcontainer/docker-compose.yml` -- `onCreateCommand`; image switch per the rollout decision -- fast start
- [ ] `README.md` -- prebuilds, image access, version bump procedure -- the human's settings steps

**Acceptance Criteria:**
- Given the image is published, when a new codespace starts, then setup does not clone or install Frappe or ERPNext.
- Given prebuilds on `main`, when a codespace is created from a prebuild, then `dev.localhost` is ready without a site install, or is recreated automatically when the snapshot lacks the database.
- Given a version bump pushed to `main`, then the workflow publishes an image tagged with both versions.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `bash -n .devcontainer/post-create.sh` -- expected: no syntax errors
- `bash .devcontainer/post-create.sh` (in this container) -- expected: exit 0 in seconds, every step skipped, as in Story 0.0
- The orphaned-site path, simulated on a throwaway site: create `orphan.localhost`, drop its database, rerun the site logic -- expected: the folder is moved aside and the site is recreated
- The workflow run on GitHub (after the rollout push) -- expected: success, and the tagged image in GHCR

**Manual checks (if no CLI):**
- A new codespace from the image (human): the setup log shows no `bench init` and no `get-app`.
