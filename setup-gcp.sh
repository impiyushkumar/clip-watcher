#!/usr/bin/env bash
# One-command setup on a fresh Ubuntu server (GCP / any VPS):
#   git clone https://github.com/impiyushkumar/clip-watcher && cd clip-watcher && ./setup-gcp.sh
# Installs everything and runs clip-watcher as a service that starts on boot and restarts itself.
set -euo pipefail
cd "$(dirname "$0")"
DIR="$(pwd)"; USER_NAME="$(whoami)"

sudo apt-get update
sudo apt-get install -y ffmpeg git python3-venv python3-pip tmux rclone
./install.sh
[ -f config.txt ] || ./configure.sh

sudo tee /etc/systemd/system/clip-watcher.service >/dev/null <<UNIT
[Unit]
Description=clip-watcher (auto-clip live streams)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$DIR
ExecStart=$DIR/run.sh
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now clip-watcher

echo
echo "clip-watcher is running and will start on every boot."
echo "  live log:     journalctl -u clip-watcher -f"
echo "  stop/start:   sudo systemctl stop clip-watcher / sudo systemctl start clip-watcher"
echo "  settings:     ./configure.sh  then  sudo systemctl restart clip-watcher"
echo "  clips:        $DIR/clips/ready/"
