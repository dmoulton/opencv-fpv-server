#!/usr/bin/env bash
#
# Install and enable the systemd service for THIS checkout.
# Run it from anywhere; it figures out the repo path and the invoking user.
#
#   ./deploy/install-service.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${SUDO_USER:-$USER}"
UNIT_NAME="opencv-fpv-server.service"
UNIT_PATH="/etc/systemd/system/${UNIT_NAME}"
PYTHON="${REPO_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
    echo "No virtualenv at ${REPO_DIR}/.venv" >&2
    echo "Create it first:" >&2
    echo "    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

echo "Installing ${UNIT_NAME}"
echo "    repo: ${REPO_DIR}"
echo "    user: ${SERVICE_USER}"

sudo tee "${UNIT_PATH}" > /dev/null <<EOF
[Unit]
Description=OpenCV FPV / webcam streaming server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
SupplementaryGroups=video
WorkingDirectory=${REPO_DIR}
ExecStart=${PYTHON} ${REPO_DIR}/server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "${UNIT_NAME}"

echo
sudo systemctl status "${UNIT_NAME}" --no-pager || true
echo
echo "Follow logs with:  journalctl -u ${UNIT_NAME} -f"
