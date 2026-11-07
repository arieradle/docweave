#!/usr/bin/env bash
# Runs the app's tests inside the dev image (see .github/workflows/ci.yml).
# Expects the repository mounted at /workspaces/docweave and the services
# mariadb, redis-cache and redis-queue reachable by those hostnames (the image's
# common_site_config.json already points at them).
set -Eeuo pipefail

SITE="${DOCWEAVE_CI_SITE:-test}"
DB_ROOT_PASSWORD="123"
BENCH_DIR="${HOME}/frappe-bench"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
export PATH="${HOME}/.local/bin:${PATH}"

echo "==> Wait for MariaDB"
for _ in $(seq 1 60); do
  mariadb -h mariadb -uroot -p"${DB_ROOT_PASSWORD}" -e 'SELECT 1' >/dev/null 2>&1 && break
  sleep 2
done
mariadb -h mariadb -uroot -p"${DB_ROOT_PASSWORD}" -e 'SELECT 1' >/dev/null

echo "==> MariaDB charset"
mariadb -h mariadb -uroot -p"${DB_ROOT_PASSWORD}" \
  -e "SET GLOBAL character_set_server = 'utf8mb4'; SET GLOBAL collation_server = 'utf8mb4_unicode_ci';"

git config --global --add safe.directory "*"
cd "${BENCH_DIR}"
echo "==> new-site ${SITE}"
bench new-site "${SITE}" \
  --db-root-username root \
  --db-root-password "${DB_ROOT_PASSWORD}" \
  --admin-password admin \
  --mariadb-user-host-login-scope=% \
  --install-app erpnext \
  </dev/null

echo "==> install docweave"
bash "${REPO_DIR}/scripts/install-app.sh" "${SITE}"

bench --site "${SITE}" set-config allow_tests true
echo "==> run-tests"
bench --site "${SITE}" run-tests --app docweave
