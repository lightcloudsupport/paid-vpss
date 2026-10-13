#!/usr/bin/env bash
# LightCloud Paid VPS Bot — installer (Ubuntu/Debian, run as root)
set -e
cd "$(dirname "$0")"

echo "▶ Installing system packages…"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip snapd git curl

if ! command -v lxc >/dev/null 2>&1; then
  echo "▶ Installing LXD…"
  snap install lxd
  lxd init --auto
fi

echo "▶ Python environment…"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "▶ Created .env — edit it now:  nano .env"
fi

cat > /etc/systemd/system/paid-vps-bot.service <<UNIT
[Unit]
Description=Paid VPS Discord Bot
After=network-online.target

[Service]
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable paid-vps-bot

echo "✅ Done. Fill in .env, then run:  systemctl start paid-vps-bot  (logs: journalctl -u paid-vps-bot -f)"
