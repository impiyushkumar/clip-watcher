#!/usr/bin/env bash
# One-click launcher: installs on first run, remembers your settings, starts watching.
cd "$(dirname "$0")"
[ -d .venv ] || ./install.sh || { read -rp "Install failed. Press Enter..."; exit 1; }
source .venv/bin/activate

CFG=config.txt
[ -f "$CFG" ] && source "$CFG"
if [ -z "${CHANNEL:-}" ]; then ./configure.sh; source "$CFG"; fi
export QUALITY KEEP_REC_DAYS CW_RCLONE_DEST

if echo ",$UPLOAD," | grep -q ",youtube," && [ ! -f token.json ] && [ -f client_secret.json ]; then
  echo "A browser will open: log in to the YouTube channel clips should go to."
  python3 uploader.py --login
fi
if echo ",$UPLOAD," | grep -Eq ",(instagram|facebook)," && [ ! -f meta.json ]; then
  echo "Instagram/Facebook upload needs a one-time Meta setup (README)."
  read -rp "Run it now? (y/n) [n]: " M; [ "$M" = "y" ] && python3 meta_uploader.py --setup
fi
UPLOAD="$(./check_uploads.sh)"
echo "Uploading to: $UPLOAD"

./watch.sh "$CHANNEL" --min "${MIN:-10}" --length "${LENGTH:-30}" --model "${MODEL:-base}" \
  --tags "${TAGS:-#gaming #shorts}" --upload "${UPLOAD:-none}" --privacy "${PRIVACY:-public}"
read -rp "Stopped. Press Enter to close..."
