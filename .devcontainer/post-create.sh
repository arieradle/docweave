#!/usr/bin/env bash
# Runs after the devcontainer is created. Safe to rerun:
#   bash .devcontainer/post-create.sh
#
# DOCWEAVE_STAGE=image (used by .devcontainer/Dockerfile) stops after the bench
# and ERPNext are installed: no rtk, no services, no site. The prebuilt image
# carries that bench, and a new frappe-bench volume is seeded from it, so the
# full run then only checks the bench and creates the site.
#
# DOCWEAVE_SITE overrides the site name (default dev.localhost), for testing
# the setup on a throwaway site.
#
# Sets up rtk, the system packages Frappe needs, uv, frappe-bench, a Frappe
# bench with ERPNext and the site dev.localhost. The bench lives in the
# `frappe-bench` volume and the database in `mariadb-data`, so a rebuild
# reuses them. Reruns never destroy an existing site; when something is off
# they stop with a message instead.
set -Eeuo pipefail

# --- Pinned versions ---------------------------------------------------------
RTK_VERSION="v1.0.1"
UV_VERSION="0.13.5"
BENCH_VERSION="5.31.0"
FRAPPE_TAG="v16.53.0"
ERPNEXT_TAG="v16.52.1"
# The bench venv binds to a uv-managed interpreter in ~/.local/share/uv, not to
# the base image's or the Python feature's, so it survives image and feature
# updates and exists inside the prebuilt image.
PYTHON_VERSION="3.14.9"  # the newest CPython uv 0.13.5 can download

# --- Development settings (dev-only credentials, documented in README) -------
BENCH_DIR="/home/vscode/frappe-bench"
SITE="${DOCWEAVE_SITE:-dev.localhost}"
DB_HOST="mariadb"
DB_ROOT_PASSWORD="123"
ADMIN_PASSWORD="admin"
REDIS_CACHE_URL="redis://redis-cache:6379"
REDIS_QUEUE_URL="redis://redis-queue:6379"
HOST_NAME="http://localhost:8000"
COMPANY_NAME="DocWeave Dev"
COMPANY_ABBR="DWD"
COMPANY_COUNTRY="United States"
COMPANY_CURRENCY="USD"
COMPANY_TIMEZONE="America/New_York"
WAIT_TIMEOUT_SECONDS=180
SENTINEL="${BENCH_DIR}/.docweave-bench-ready"

STAGE="${DOCWEAVE_STAGE:-full}"
[[ "${STAGE}" == "full" || "${STAGE}" == "image" ]] || { echo "Unknown DOCWEAVE_STAGE: ${STAGE}" >&2; exit 1; }
[[ "${SITE}" =~ ^[a-z0-9][a-z0-9.-]*$ ]] || { echo "Invalid DOCWEAVE_SITE: ${SITE}" >&2; exit 1; }

export PATH="${HOME}/.local/bin:${PATH}"

STEP="starting"
step() {
  STEP="$1"
  echo
  echo "==> ${STEP}"
}
on_error() {
  local code=$?
  echo >&2
  echo "post-create.sh FAILED (exit ${code}) during step: ${STEP}" >&2
  echo "Fix the cause, then rerun: bash .devcontainer/post-create.sh" >&2
  exit "${code}"
}
trap on_error ERR

die() {
  echo >&2
  echo "post-create.sh STOPPED during step: ${STEP}" >&2
  echo "$*" >&2
  exit 1
}

# --- rtk ---------------------------------------------------------------------
if [[ "${STAGE}" == "full" ]]; then
step "Install rtk ${RTK_VERSION}"
# rtk compresses shell command output for Claude Code (https://github.com/rtk-ai/rtk).
# The installer verifies the release checksum and installs to ~/.local/bin.
if [[ "$("${HOME}/.local/bin/rtk" --version 2>/dev/null | awk '{print $2}')" == "${RTK_VERSION#v}" ]]; then
  echo "rtk ${RTK_VERSION} already installed."
else
  curl -fsSL "https://raw.githubusercontent.com/rtk-ai/rtk/refs/tags/${RTK_VERSION}/install.sh" \
    | RTK_VERSION="${RTK_VERSION}" sh
fi

step "Register rtk hook for Claude Code"
# stdin from /dev/null: post-create has no one to answer a prompt, and rtk
# blocks on one when its config already exists in ~/.claude.
"${HOME}/.local/bin/rtk" init -g --auto-patch --no-trust-filters </dev/null \
  || echo "WARNING: rtk init failed; rtk hooks not registered. Run 'rtk init -g' by hand." >&2
fi

# --- System packages ---------------------------------------------------------
step "Install system packages"
# mariadb-client: bench console/backup; redis-tools: readiness checks;
# libmariadb-dev, pkg-config, build-essential: mysqlclient==2.2.7 builds from
# source because it has no Python 3.14 wheel.
APT_PACKAGES=(mariadb-client redis-tools libmariadb-dev pkg-config build-essential)
missing=()
for pkg in "${APT_PACKAGES[@]}"; do
  dpkg -s "${pkg}" >/dev/null 2>&1 || missing+=("${pkg}")
done
if ((${#missing[@]})); then
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
else
  echo "All system packages already installed."
fi

# --- uv and bench ------------------------------------------------------------
step "Install uv ${UV_VERSION}"
if [[ "$(uv --version 2>/dev/null | awk '{print $2}')" == "${UV_VERSION}" ]]; then
  echo "uv ${UV_VERSION} already installed."
else
  curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | UV_NO_MODIFY_PATH=1 sh
fi

step "Install Python ${PYTHON_VERSION} (uv-managed)"
uv python install --managed-python --no-bin "${PYTHON_VERSION}"
BENCH_PYTHON="$(uv python find --managed-python "${PYTHON_VERSION}")"
echo "Bench Python: ${BENCH_PYTHON}"

step "Install frappe-bench ${BENCH_VERSION}"
if [[ "$(bench --version 2>/dev/null | tail -n1)" == "${BENCH_VERSION}" ]]; then
  echo "frappe-bench ${BENCH_VERSION} already installed."
else
  uv tool install --force "frappe-bench==${BENCH_VERSION}"
fi

# --- Wait for services -------------------------------------------------------
wait_for_services() {
  local deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))
  local err=""

  # A real query: `mariadb-admin ping` succeeds even with a wrong password.
  until err="$(mariadb -h "${DB_HOST}" -uroot -p"${DB_ROOT_PASSWORD}" \
      --connect-timeout=5 -e 'SELECT 1' 2>&1 >/dev/null)"; do
    if ((SECONDS >= deadline)); then
      die "MariaDB at ${DB_HOST} did not accept the root login within ${WAIT_TIMEOUT_SECONDS}s. Last error: ${err}"
    fi
    sleep 2
  done
  echo "MariaDB is ready."

  local url reply
  for url in "${REDIS_CACHE_URL}" "${REDIS_QUEUE_URL}"; do
    until reply="$(redis-cli -u "${url}" ping 2>&1)" && [[ "${reply}" == "PONG" ]]; do
      if ((SECONDS >= deadline)); then
        die "Redis at ${url} did not answer PING within ${WAIT_TIMEOUT_SECONDS}s. Last reply: ${reply}"
      fi
      sleep 2
    done
    echo "Redis at ${url} is ready."
  done
}

if [[ "${STAGE}" == "full" ]]; then
  step "Wait for MariaDB and Redis"
  wait_for_services
fi

# --- Bench -------------------------------------------------------------------
step "Prepare bench volume"
if [[ ! -d "${BENCH_DIR}" ]]; then
  sudo mkdir -p "${BENCH_DIR}"
fi
# A fresh named volume is owned by root.
if [[ ! -w "${BENCH_DIR}" ]]; then
  sudo chown "$(id -u):$(id -g)" "${BENCH_DIR}"
fi

if [[ -f "${SENTINEL}" ]]; then
  echo "Existing bench found."
elif [[ -d "${BENCH_DIR}/apps/frappe" && -f "${BENCH_DIR}/sites/apps.txt" ]]; then
  # Never destroy on doubt: a bench without the marker is adopted, not wiped.
  echo "Bench without marker found; adopting it."
  touch "${SENTINEL}"
else
  if [[ -n "$(ls -A "${BENCH_DIR}")" ]]; then
    echo "Removing an incomplete bench (no apps/frappe or sites/apps.txt)."
    find "${BENCH_DIR}" -mindepth 1 -delete
  fi

  step "bench init (Frappe ${FRAPPE_TAG})"
  # The volume mount point already exists, hence --ignore-exist.
  (cd "$(dirname "${BENCH_DIR}")" && bench init "$(basename "${BENCH_DIR}")" \
    --ignore-exist \
    --frappe-branch "${FRAPPE_TAG}" \
    --python "${BENCH_PYTHON}" \
    --skip-redis-config-generation \
    --no-backups \
    </dev/null)
  touch "${SENTINEL}"
fi

cd "${BENCH_DIR}"

check_tag() {
  local app="$1" expected="$2" actual
  actual="$(git -C "apps/${app}" describe --tags 2>/dev/null || echo "unknown")"
  if [[ "${actual}" != "${expected}" ]]; then
    die "Version drift: apps/${app} is at ${actual}, but ${expected} is pinned.
The bench in the frappe-bench volume was built for other versions. Reset the
volumes (see README, \"Reset\") and rebuild the container."
  fi
  echo "${app} is at ${expected}."
}

step "Check Frappe version"
check_tag frappe "${FRAPPE_TAG}"

if grep -qx "erpnext" sites/apps.txt; then
  step "Check ERPNext version"
  check_tag erpnext "${ERPNEXT_TAG}"
fi

# Runs before any `bench` command that needs the bench venv (set-config, site
# commands). A venv broken by a base image change is rebuilt, not the bench.
step "Check bench Python environment"
modules="frappe"
grep -qx "erpnext" sites/apps.txt && modules="frappe, erpnext"
if env/bin/python -c "import ${modules}" >/dev/null 2>&1; then
  echo "Bench venv is healthy."
else
  echo "Bench venv cannot import ${modules}; recreating it."
  bench setup env --python "${BENCH_PYTHON}"
  bench setup requirements
fi

step "Configure bench services"
bench set-config -g db_host "${DB_HOST}"
bench set-config -g redis_cache "${REDIS_CACHE_URL}"
bench set-config -g redis_queue "${REDIS_QUEUE_URL}"
# Frappe v16 does not read redis_socketio, but bench fills in a 127.0.0.1
# default when it is absent; point it at a real service to avoid confusion.
bench set-config -g redis_socketio "${REDIS_QUEUE_URL}"

if ! grep -qx "erpnext" sites/apps.txt; then
  step "Get ERPNext ${ERPNEXT_TAG}"
  # An unregistered apps/erpnext is a leftover from an interrupted get-app.
  bench get-app --overwrite --branch "${ERPNEXT_TAG}" erpnext </dev/null
  step "Check ERPNext version"
  check_tag erpnext "${ERPNEXT_TAG}"
fi

if [[ "${STAGE}" == "image" ]]; then
  step "Done (image stage)"
  echo "Bench with Frappe ${FRAPPE_TAG} and ERPNext ${ERPNEXT_TAG} is ready; the site is created at container start."
  exit 0
fi

# --- Site --------------------------------------------------------------------
site_apps() {
  bench --site "${SITE}" list-apps 2>&1
}

# A site folder whose database is gone (for example a prebuild snapshot that
# kept the bench volume but not MariaDB's) is moved aside, never deleted, and
# the site is created again. Only a database that is certainly absent counts.
if [[ -f "sites/${SITE}/site_config.json" ]]; then
  step "Check database of site ${SITE}"
  db_name="$(env/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1])).get("db_name", ""))' \
    "sites/${SITE}/site_config.json" 2>&1)" \
    || die "Cannot read sites/${SITE}/site_config.json: ${db_name}"
  # Frappe's db names are generated hex-like identifiers; anything else is unexpected.
  [[ "${db_name}" =~ ^[A-Za-z0-9_]+$ ]] \
    || die "sites/${SITE}/site_config.json has no usable db_name (got '${db_name}'). Nothing was changed."
  db_found="$(mariadb -h "${DB_HOST}" -uroot -p"${DB_ROOT_PASSWORD}" -N \
    -e "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='${db_name}'" 2>&1)" \
    || die "Cannot ask MariaDB whether database ${db_name} exists: ${db_found}. Nothing was changed."
  if [[ "${db_found}" == "0" ]]; then
    step "Recover site ${SITE} without a database"
    # Outside sites/, so bench does not treat it as a site.
    mkdir -p orphaned-sites
    orphan="orphaned-sites/${SITE}.$(date +%Y%m%d%H%M%S).$$"
    mv -T "sites/${SITE}" "${orphan}"
    echo "Database ${db_name} for ${SITE} does not exist in MariaDB; moved the site folder to ${orphan} and creating the site again."
  fi
fi

if [[ -f "sites/${SITE}/site_config.json" ]]; then
  step "Check existing site ${SITE}"
  # Never run new-site --force on an existing site: retry, then stop.
  apps=""
  ok=0
  for attempt in 1 2 3; do
    if apps="$(site_apps)"; then
      ok=1
      break
    fi
    echo "list-apps failed (attempt ${attempt} of 3)."
    ((attempt < 3)) || break
    wait_for_services
    sleep 5
  done
  if ((!ok)); then
    die "Site ${SITE} exists but 'bench --site ${SITE} list-apps' keeps failing:
${apps}
Nothing was changed. Investigate the error above. To start over, drop the site
(bench drop-site ${SITE} --db-root-password ${DB_ROOT_PASSWORD} --force) or reset
the volumes (see README), then rerun this script."
  fi
  if ! grep -q '^erpnext[[:space:]]' <<<"${apps}"; then
    step "Install ERPNext on ${SITE}"
    bench --site "${SITE}" install-app erpnext
  fi
else
  step "Create site ${SITE}"
  bench new-site "${SITE}" \
    --db-root-username root \
    --db-root-password "${DB_ROOT_PASSWORD}" \
    --admin-password "${ADMIN_PASSWORD}" \
    --mariadb-user-host-login-scope=% \
    --install-app erpnext \
    </dev/null
fi

step "Configure site ${SITE}"
bench use "${SITE}"
bench --site "${SITE}" set-config -p developer_mode 1
bench --site "${SITE}" set-config host_name "${HOST_NAME}"
bench --site "${SITE}" clear-cache

step "Complete ERPNext setup wizard"
# Without it there is no Company and the desk redirects to the wizard.
setup_done() {
  [[ "$(bench --site "${SITE}" execute frappe.is_setup_complete 2>/dev/null | tail -n1)" == "true" ]]
}
if setup_done; then
  echo "Setup wizard already complete."
else
  FY="$(date +%Y)"
  bench --site "${SITE}" execute frappe.desk.page.setup_wizard.setup_wizard.setup_complete \
    --kwargs "{\"args\": {
      \"language\": \"English\",
      \"country\": \"${COMPANY_COUNTRY}\",
      \"timezone\": \"${COMPANY_TIMEZONE}\",
      \"currency\": \"${COMPANY_CURRENCY}\",
      \"company_name\": \"${COMPANY_NAME}\",
      \"company_abbr\": \"${COMPANY_ABBR}\",
      \"chart_of_accounts\": \"Standard\",
      \"fy_start_date\": \"${FY}-01-01\",
      \"fy_end_date\": \"${FY}-12-31\",
      \"enable_telemetry\": 0
    }}"
  setup_done || die "setup_complete ran but ${SITE} still reports setup as incomplete. See the Error Log in the desk or ${BENCH_DIR}/logs."
fi

step "Done"
bench --version
bench --site "${SITE}" list-apps
echo
echo "Setup complete. Start the bench with: cd ${BENCH_DIR} && bench start"
echo "Then open ${HOST_NAME} (Administrator / ${ADMIN_PASSWORD})."
