#!/usr/bin/env bash
# Creates spike.localhost on the Story 0.0 bench: ERPNext installed and the
# setup wizard completed. Throwaway site for the Epic 0 spikes. Safe to rerun;
# it never drops an existing site.
#   bash spikes/setup_site.sh
set -Eeuo pipefail

BENCH_DIR="/home/vscode/frappe-bench"
SITE="spike.localhost"
DB_ROOT_PASSWORD="123"
ADMIN_PASSWORD="admin"
export PATH="${HOME}/.local/bin:${PATH}"
cd "${BENCH_DIR}"

if [[ ! -d "sites/${SITE}" ]]; then
  bench new-site "${SITE}" \
    --db-root-username root \
    --db-root-password "${DB_ROOT_PASSWORD}" \
    --admin-password "${ADMIN_PASSWORD}" \
    --mariadb-user-host-login-scope=% \
    --install-app erpnext \
    </dev/null
fi

if [[ "$(bench --site "${SITE}" execute frappe.is_setup_complete 2>/dev/null | tail -n1)" != "true" ]]; then
  bench --site "${SITE}" execute frappe.desk.page.setup_wizard.setup_wizard.setup_complete \
    --kwargs '{"args": {
      "language": "English", "country": "United States",
      "timezone": "America/New_York", "currency": "USD",
      "company_name": "Spike Co", "company_abbr": "SPK",
      "chart_of_accounts": "Standard",
      "fy_start_date": "2026-01-01", "fy_end_date": "2026-12-31",
      "enable_telemetry": 0
    }}'
fi
bench --site "${SITE}" list-apps
