#!/usr/bin/env bash
# Installs this repository into the bench as the Frappe app `docweave`.
# Used by the codespace (devcontainer.json) and by CI (scripts/ci-test.sh).
#
#   bash scripts/install-app.sh [SITE]     (SITE defaults to dev.localhost)
#
# Safe to rerun: a finished step is skipped. If apps/docweave exists and is
# not the symlink to this repository, it stops and deletes nothing.
set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
BENCH_DIR="${BENCH_DIR:-${HOME}/frappe-bench}"
SITE="${1:-${DOCWEAVE_SITE:-dev.localhost}}"
APP="docweave"
export PATH="${HOME}/.local/bin:${PATH}"

die() { echo "install-app.sh STOPPED: $*" >&2; exit 1; }
changed=0

[[ -d "${BENCH_DIR}/apps" && -f "${BENCH_DIR}/sites/apps.txt" ]] || die "No bench at ${BENCH_DIR}."
cd "${BENCH_DIR}"

# 1. apps/docweave -> this repository
link="apps/${APP}"
if [[ -L "${link}" ]]; then
  if [[ "$(cd "${link}" && pwd -P)" != "${REPO_DIR}" ]]; then
    die "${BENCH_DIR}/${link} is a symlink to $(readlink "${link}"), not to ${REPO_DIR}. Nothing was changed."
  fi
elif [[ -e "${link}" ]]; then
  die "${BENCH_DIR}/${link} exists and is not a symlink to ${REPO_DIR}. Nothing was changed; move it aside yourself."
else
  echo "==> Link ${link} -> ${REPO_DIR}"
  ln -s "${REPO_DIR}" "${link}"
  changed=1
fi

# 2. editable install into the bench venv
if env/bin/python -c "import ${APP}" >/dev/null 2>&1 \
  && [[ "$(env/bin/python -c "import ${APP}, os; print(os.path.realpath(os.path.dirname(os.path.dirname(${APP}.__file__))))")" == "${REPO_DIR}" ]]; then
  echo "${APP} is already installed in the bench venv."
else
  echo "==> pip install -e ${link}"
  if [[ -x env/bin/pip ]]; then
    env/bin/pip install --quiet -e "${link}"
  else
    uv pip install --quiet --python env/bin/python -e "${link}"
  fi
  changed=1
fi

# 3. apps.txt
if ! grep -qx "${APP}" sites/apps.txt; then
  echo "==> Add ${APP} to sites/apps.txt"
  [[ -z "$(tail -c1 sites/apps.txt)" ]] || echo >> sites/apps.txt
  echo "${APP}" >> sites/apps.txt
  changed=1
fi

# 4. install on the site
if [[ ! -f "sites/${SITE}/site_config.json" ]]; then
  echo "Site ${SITE} does not exist; skipping install-app."
elif grep -q "^${APP}[[:space:]]" <<<"$(bench --site "${SITE}" list-apps 2>/dev/null || true)"; then
  echo "${APP} is already installed on ${SITE}."
else
  echo "==> bench --site ${SITE} install-app ${APP}"
  bench --site "${SITE}" install-app "${APP}"
  changed=1
fi

if ((changed)); then echo "Done."; else echo "Nothing to do."; fi
