#!/usr/bin/env bash
# Restart the Pellier backend and tail its log.
#
# The backend runs as the `pellier` systemd unit (uvicorn --reload for
# builders format), so it is ALWAYS running after bootstrap and reloads
# on .py save — participants normally never need this. It exists for a
# clean manual bounce. systemd owns the process: no nohup, no PID file,
# no second uvicorn fighting for :8000.
set -uo pipefail

echo "Restarting pellier service..."
sudo systemctl restart pellier || {
    echo "restart failed — check: journalctl -u pellier" >&2
    exit 1
}
exec journalctl -fu pellier --no-pager
