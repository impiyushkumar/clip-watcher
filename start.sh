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
UPLOAD="$(UPLOAD="$UPLOAD" ./check_uploads.sh)"
echo "Uploading to: $UPLOAD"

if [ "${AUTO_LEARN:-1}" = "1" ]; then
    LENGTH="$(python3 learn.py --pick-length "${LENGTH:-30}" 2>/dev/null || echo "${LENGTH:-30}")"
    echo "Self-learning on: clip length this stream = ${LENGTH}s"
  fi
  QARGS=()
  if [ "${POST_EVERY:-0}" != "0" ]; then
    QARGS=(--queue clips/queue --upload none)
    pkill -f "poster.py" 2>/dev/null
    python3 -u poster.py --every "$POST_EVERY" --upload "$UPLOAD" --tags "${TAGS:-#gaming #shorts}" \
      --privacy "${PRIVACY:-public}" &
  fi
  ./watch.sh "$CHANNEL" --min "${MIN:-10}" --length "${LENGTH:-30}" --model "${MODEL:-base}" \
  --tags "${TAGS:-#gaming #shorts}" --upload "${UPLOAD:-none}" --privacy "${PRIVACY:-public}" "${QARGS[@]}"
pkill -f poster.py 2>/dev/null
read -rp "Stopped. Press Enter to close..."
