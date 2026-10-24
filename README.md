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

Pinned versions: Frappe `v16.53.0`, ERPNext `v16.52.1`, frappe-bench `5.31.0`, uv `0.13.5`.
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
If the site exists but cannot be read, it stops and tells you; drop the site
(`bench drop-site dev.localhost --db-root-password 123 --force`) or reset the volumes,
then rerun. If the bench's Python environment is broken (for example after a base
image change), setup recreates it with `bench setup env`.

### Version mismatch

If the pinned Frappe or ERPNext tag changes, an existing bench is not upgraded
in place. Setup stops with `Version drift: apps/<app> is at <tag>, but <tag> is pinned.`
Reset the volumes (see above) and rebuild to get a bench at the pinned versions.
Check the installed versions with:

```bash
bench --version
cd ~/frappe-bench && bench --site dev.localhost list-apps
```
