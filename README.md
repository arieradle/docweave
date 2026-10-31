# docweave
GraphQL extension for Frappe framework

## Development environment

The devcontainer runs Docker Compose with four services:

| Service | Image | Purpose |
|---------|-------|---------|
| `app` | `mcr.microsoft.com/devcontainers/base:ubuntu26.04` (pinned by digest) with Python 3.14, Node 24 and Claude Code | Your shell, the bench |
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
`docweave_redis-queue-data` volumes with `docker volume rm`. The next build installs
everything again.

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
folder to `~/frappe-bench/orphaned-sites/` (nothing is deleted) and creates the site again.
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
and built assets. It holds no site and no database. When `docker-compose.yml` uses it,
a new `frappe-bench` volume is seeded from the image, so setup skips `bench init` and
`get-app` and only creates the site.

One-time settings (repository owner):

1. After the first workflow run, open the package (**your profile > Packages >
   docweave-dev > Package settings**) and set **Change visibility** to **Public**.
   GHCR makes a new package private, even from a public repository. Public lets
   Codespaces (and forks) pull it without access settings. If you keep it private,
   add this repository under **Manage Codespaces access** in the same settings page.
2. Enable prebuilds: **repository Settings > Codespaces > Set up prebuild**, branch
   `main`, the default devcontainer, trigger **On configuration change**, and your region.
   A prebuild runs `onCreateCommand` (the same `post-create.sh`), so `dev.localhost`
   is created inside the prebuild. If a prebuild ever comes up without the database,
   setup recreates the site automatically (see "If setup fails").

**Bumping Frappe or ERPNext** takes two pushes, because the devcontainer must not point
at an image that does not exist yet:

1. Change the pinned constants in `.devcontainer/post-create.sh` and push to `main`.
   The workflow publishes the image with the new tag. Wait for it to finish.
2. Change `app.image` in `.devcontainer/docker-compose.yml` to the new tag and push.
   That is a devcontainer configuration change, so prebuilds refresh.

Existing codespaces keep their volumes. They still need a reset after a bump (see
"Version mismatch").

### Version mismatch

If the pinned Frappe or ERPNext tag changes, an existing bench is not upgraded
in place. Setup stops with `Version drift: apps/<app> is at <tag>, but <tag> is pinned.`
Reset the volumes (see above) and rebuild to get a bench at the pinned versions.
Check the installed versions with:

```bash
bench --version
cd ~/frappe-bench && bench --site dev.localhost list-apps
```
