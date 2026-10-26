#!/usr/bin/env bash
# Serves the bench with gunicorn on 127.0.0.1:8001 for the REST baseline.
# gthread workers, as in frappe_docker: idle connections (a browser, port
# forwarding probes) cannot tie up a worker the way they do with sync workers.
#   bash spikes/serve_rest.sh
set -Eeuo pipefail
cd /home/vscode/frappe-bench/sites
exec ../env/bin/gunicorn -b 127.0.0.1:8001 \
  --worker-class gthread --workers 2 --threads 4 \
  --timeout 120 --pid /home/vscode/frappe-bench/spike-gunicorn.pid \
  --preload frappe.app:application
