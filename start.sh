#!/usr/bin/env bash
# One-click launcher: installs on first run, asks the setup questions once, then starts.
cd "$(dirname "$0")"
[ -d .venv ] || ./scripts/install.sh || { read -rp "Install failed. Press Enter..."; exit 1; }
source .venv/bin/activate

[ -f config.txt ] && source config.txt
if [ -z "${CHANNELS:-${CHANNEL:-}}" ]; then ./scripts/configure.sh; source config.txt; fi

if echo ",$UPLOAD," | grep -q ",youtube," && [ ! -f token.json ] && [ -f client_secret.json ]; then
  echo "A browser will open: log in to the YouTube channel clips should go to."
  python3 -m clipwatcher youtube-login
fi
if echo ",$UPLOAD," | grep -Eq ",(instagram|facebook)," && [ ! -f meta.json ]; then
  echo "Instagram/Facebook upload needs a one-time Meta setup (docs/setup-meta.md)."
  read -rp "Run it now? (y/n) [n]: " ANSWER; [ "$ANSWER" = "y" ] && python3 -m clipwatcher meta-setup
fi

echo "Starting... (Ctrl+C to stop)"
./scripts/run.sh
read -rp "Stopped. Press Enter to close..."
