#!/usr/bin/env bash
# Bootstrap Xubuntu lab host for havikkivaaka / YKV dealer prep.
# Usage: sudo ./scripts/bootstrap-xubuntu.sh

set -euo pipefail

[[ "$(id -u)" -eq 0 ]] || { echo "Run as: sudo $0"; exit 1; }

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  openssh-server \
  python3 \
  python3-venv \
  python3-pip \
  netcat-openbsd \
  dnsmasq \
  git \
  rsync \
  curl \
  chromium-browser \
  || apt-get install -y \
    openssh-server python3 python3-venv python3-pip \
    netcat-openbsd dnsmasq git rsync curl chromium

systemctl enable --now ssh

# Prefer chromium binary name
if command -v chromium-browser >/dev/null; then
  echo "chromium-browser: $(command -v chromium-browser)"
elif command -v chromium >/dev/null; then
  echo "chromium: $(command -v chromium)"
else
  echo "WARN: chromium not found — install later if needed"
fi

echo "Bootstrap done."
echo "Next: python3 ~/havikkivaaka/tools/kcp_mock.py --port 2323"
