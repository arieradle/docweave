# docweave
GraphQL extension for Frappe framework

## Development environment

The devcontainer runs Docker Compose with four services:

| Service | Image | Purpose |
|---------|-------|---------|
| `app` | `ghcr.io/arieradle/docweave-dev` (the pinned devcontainer base with the bench prebuilt, see "Fast start") with Python 3.14, Node 24 and Claude Code | Your shell, the bench |
| `mariadb` | `mariadb:11.8` (utf8mb4) | Database |
| `redis-cache` | `redis:7-alpine` | Frappe cache |
| `redis-queue` | `redis:7-alpine` | Background jobs and realtime |

Pinned versions: Frappe `v16.53.0`, ERPNext `v16.52.1`, frappe-bench `5.31.0`, uv `0.13.5`,
and Python `3.14.9` for the bench (installed by uv, so the bench does not depend on the
image's or the Python feature's interpreter).
They are constants at the top of `.devcontainer/post-create.sh`.

### Open the container

Open the repository in VS Code and choose **Reopen in Container** (or create a Codespace).
On first build `.devcontainer/post-create.sh` installs the system packages, uv,
frappe-bench, a bench at `~/frappe-bench` with ERPNext, and the site `dev.localhost`.
This takes a while the first time. The bench lives in the `frappe-bench` volume and
the database in `mariadb-data`, so nothing of it is committed to the repository.

### Run the site

```bash
cd ~/frappe-bench
bench start
```

Open <http://localhost:8000> (port 8000 is forwarded; socketio uses 9000).
`dev.localhost` is the default site, so `localhost:8000` serves it.
Developer mode is on. Setup also completes ERPNext's setup wizard with fixed dev
values, so the desk opens directly: company `DocWeave Dev` (abbreviation `DWD`),
country United States, currency USD, time zone America/New_York, language English,
standard chart of accounts and the current calendar year as fiscal year.

Development logins (dev-only values, never use them anywhere else):

| What | User | Password |
|------|------|----------|
| Desk | `Administrator` | `admin` |
| MariaDB (`mariadb` host) | `root` | `123` |

### Rebuild

**Rebuild Container** keeps the volumes. Setup detects the existing bench and site,
skips the reinstall and only reapplies configuration.

### Reset

To start from scratch, remove the volumes and rebuild. From the host
(outside the container), with the devcontainer stopped:

```bash
docker compose -p docweave -f .devcontainer/docker-compose.yml down -v
```

Or remove the `docweave_frappe-bench`, `docweave_mariadb-data` and
`docweave_redis-queue-data` volumes with `docker volume rm`. The next build seeds a new
bench volume from the prebuilt image (see "Fast start") and only creates the site again.

### If setup fails

The setup log names the failing step (`post-create.sh FAILED ... during step: ...`).
Fix the cause (network, a service not starting, and so on), then rerun it inside
the container:

```bash
bash .devcontainer/post-create.sh
```

Reruns are safe: finished steps are skipped. Setup never recreates an existing site.
The one exception is a site whose database is certainly gone, for example a Codespaces
prebuild snapshot that kept the bench but not MariaDB's data. Setup moves that site
folder to `~/frappe-bench/orphaned-sites/` (nothing is deleted), logs
`==> Recover site dev.localhost without a database`, and creates the site again.
Folders in `orphaned-sites/` are never cleaned up automatically; they may hold the old
site's private files. Delete them yourself once you don't need them.
If setup can't tell whether the database exists (MariaDB unreachable, unreadable
`site_config.json`), it stops and changes nothing.
If the site exists but cannot be read, it stops and tells you; drop the site
(`bench drop-site dev.localhost --db-root-password 123 --force`) or reset the volumes,
then rerun. If the bench's Python environment is broken (for example after a base
image change), setup recreates it with `bench setup env`.

### Fast start (prebuilt image and prebuilds)

A new codespace can skip the long install in two ways.

**Prebuilt image.** `.github/workflows/dev-image.yml` builds `.devcontainer/Dockerfile`
and publishes `ghcr.io/arieradle/docweave-dev:frappe-<tag>-erpnext-<tag>` (for example
`frappe-v16.53.0-erpnext-v16.52.1`). It runs on every push to `main` that changes the
Dockerfile, `post-create.sh` or the workflow, and from **Actions > dev-image > Run workflow**.
The image holds the bench with Frappe and ERPNext, their Python and Node dependencies
and built assets. It holds no site and no database. Before pushing, the workflow
smoke-tests the image (bench version, `import frappe, erpnext`, no site inside). Only
runs on `main` publish. `docker-compose.yml` uses the image **by digest**, and a new
`frappe-bench` volume is seeded from it, so setup skips `bench init` and `get-app` and
only creates the site. The image is `linux/amd64` only (what Codespaces runs); on an
arm64 machine, local Docker runs it under emulation.

One-time settings (repository owner):

1. The package is public (it inherited this public repository's visibility on the
   first publish, 2026-10-31), so Codespaces and forks pull it without settings. If it
   is ever made private, add this repository under **Manage Codespaces access** in
   **your profile > Packages > docweave-dev > Package settings**.
2. Enable prebuilds: **repository Settings > Codespaces > Set up prebuild**, branch
   `main`, the default devcontainer, trigger **On configuration change**, and your region.
   A prebuild runs `onCreateCommand` (the same `post-create.sh`), so `dev.localhost`
   is created inside the prebuild. If a prebuild ever comes up without the database,
   setup recreates the site automatically (see "If setup fails"). To check that a
   codespace really used the prebuilt site, look in its creation log: a
   `==> Create site` or `==> Recover site` step means the site was built again.
   `postCreateCommand` reruns the same script after creation (about 10 s; every step
   is skipped). It is what recovers a prebuild that lacks the database.

**Changing the image** (bumping Frappe, ERPNext, Python, frappe-bench, uv or Node, or
any change to `post-create.sh`) takes two pushes, because the devcontainer must not
point at an image that does not exist yet:

1. Make the change and push to `main`. The workflow builds, smoke-tests and publishes
   the image. Wait for it to finish, then copy the digest from the run's Push step (or
   from the package page).
2. Change `app.image` in `.devcontainer/docker-compose.yml` to the new tag **and**
   digest, and push. That is a devcontainer configuration change, so prebuilds refresh.

Between the two pushes, a codespace created from `main` gets the old image but the new
pins. For a Frappe or ERPNext bump, setup then stops with "Version drift". Do the two
pushes back to back, or create codespaces from the commit before step 1 meanwhile.

Existing codespaces keep their volumes. They still need a reset after a bump (see
"Version mismatch").

### Branches and pull requests

`main` is protected. Work happens on a branch, one per story or fix (for example
`story/1-1-installable-app` or `chore/...`), and reaches `main` through a pull request.

- Push the branch and open the pull request with `gh pr create` (or from the link
  `git push` prints). The devcontainer installs the GitHub CLI (`gh` 2.102.0). In
  Codespaces it is signed in automatically through the codespace's `GITHUB_TOKEN`;
  in a local devcontainer, run `gh auth login` once.
- The `dev-image / devcontainer` check runs on every pull request. If the PR touches
  `.devcontainer/` or `.github/workflows/dev-image.yml`, it builds the image and
  smoke-tests the bench, but never publishes. It also checks that the image
  `docker-compose.yml` names, including its digest, exists in GHCR. Other PRs pass it
  in seconds.
- Merge when the check is green. Merging to `main` publishes the image if the
  devcontainer changed (see "Fast start"), and prebuilds refresh on devcontainer changes.
- An image change is two pull requests: the first changes the Dockerfile or
  `post-create.sh` and publishes on merge; the second updates the tag and digest in
  `docker-compose.yml`. The second can't merge before the image exists, because of
  the compose-image check.

`.github/CODEOWNERS` names the owner for `.devcontainer/` and `.github/`.

**Ruleset for `main`** (repository owner, once): **Settings > Rules > Rulesets > New
ruleset > New branch ruleset**:

- Name `main`, enforcement **Active**, target **Include default branch**.
- **Bypass list:** empty (or add yourself only for emergencies; a bypass also skips the check).
- Turn on:
  - **Restrict deletions**
  - **Block force pushes**
  - **Require a pull request before merging**, with **Required approvals: 0**.
    GitHub doesn't count your own approval, so 1 would lock a solo owner out. Leave
    **Require review from Code Owners** off until there is a second maintainer.
  - **Require status checks to pass**, add **`devcontainer`** (it appears in the list
    after the check has run once on a pull request), and turn on **Require branches
    to be up to date before merging**.
- **Create**.

### Version mismatch

If the pinned Frappe or ERPNext tag changes, an existing bench is not upgraded
in place. Setup stops with `Version drift: apps/<app> is at <tag>, but <tag> is pinned.`
Reset the volumes (see above) and rebuild to get a bench at the pinned versions.
Check the installed versions with:

```bash
bench --version
cd ~/frappe-bench && bench --site dev.localhost list-apps
```
