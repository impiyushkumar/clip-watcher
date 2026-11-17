#!/usr/bin/env bash
# One-click launcher: installs on first run, remembers the channel, starts watching.
cd "$(dirname "$0")"
[ -d .venv ] || ./install.sh || { read -rp "Install failed. Press Enter..."; exit 1; }

CFG=config.txt
[ -f "$CFG" ] && source "$CFG"
if [ -z "${CHANNEL:-}" ]; then
  read -rp "Twitch channel to watch: " CHANNEL
  read -rp "Min messages per 10s for a spike [10]: " MIN
  printf 'CHANNEL=%s\nMIN=%s\nMODEL=base\n' "$CHANNEL" "${MIN:-10}" > "$CFG"
fi
./watch.sh "$CHANNEL" --min "${MIN:-10}" --model "${MODEL:-base}"
read -rp "Stopped. Press Enter to close..."
