#!/usr/bin/env bash
# One-click launcher: installs on first run, remembers your settings, starts watching.
cd "$(dirname "$0")"
[ -d .venv ] || ./install.sh || { read -rp "Install failed. Press Enter..."; exit 1; }
source .venv/bin/activate

CFG=config.txt
[ -f "$CFG" ] && source "$CFG"
if [ -z "${CHANNEL:-}" ]; then
  echo "=== clip-watcher first-time setup (saved to config.txt, edit it any time) ==="
  read -rp "Channel (xqc, youtube:@handle, kick:name): " CHANNEL
  read -rp "Min chat messages per 10s for a spike [10]: " MIN
  read -rp "Clip length in seconds [30]: " LENGTH
  read -rp "Hashtags [#gaming #shorts #twitch]: " TAGS
  read -rp "Auto-upload every clip to YouTube Shorts? (y/n) [n]: " YT
  UPLOAD=none; [ "${YT:-n}" = "y" ] && UPLOAD=youtube
  {
    echo "CHANNEL='$CHANNEL'"; echo "MIN=${MIN:-10}"; echo "LENGTH=${LENGTH:-30}"
    echo "TAGS='${TAGS:-#gaming #shorts #twitch}'"; echo "UPLOAD=$UPLOAD"
    echo "PRIVACY=public"; echo "MODEL=base"
  } > "$CFG"
fi

if [ "${UPLOAD:-none}" = "youtube" ] && [ ! -f token.json ]; then
  if [ ! -f client_secret.json ]; then
    echo "YouTube upload needs client_secret.json in this folder - see README 'YouTube auto-upload'."
    echo "Continuing WITHOUT upload for now (clips still go to clips/ready/)."
    UPLOAD=none
  else
    echo "A browser will open: log in to the YouTube channel clips should go to."
    python3 uploader.py --login || UPLOAD=none
  fi
fi

./watch.sh "$CHANNEL" --min "${MIN:-10}" --length "${LENGTH:-30}" --model "${MODEL:-base}" \
  --tags "${TAGS:-#gaming #shorts}" --upload "${UPLOAD:-none}" --privacy "${PRIVACY:-public}"
read -rp "Stopped. Press Enter to close..."
