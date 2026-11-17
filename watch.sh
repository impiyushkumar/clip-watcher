#!/usr/bin/env bash
# Usage: ./watch.sh <twitch_channel> [--min N] [--factor 2.5] [--model base]
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <twitch_channel> [--min N] [--factor F] [--model base]"; exit 1
fi
CHANNEL="$(echo "$1" | tr '[:upper:]' '[:lower:]')"; shift

[ -f .venv/bin/activate ] && source .venv/bin/activate
for t in ffmpeg streamlink whisper python3; do
  command -v "$t" >/dev/null || { echo "Missing $t - run ./install.sh first"; exit 1; }
done

mkdir -p rec clips
REC="rec/${CHANNEL}_$(date +%Y%m%d_%H%M%S).ts"

echo "Recording twitch.tv/$CHANNEL -> $REC  (Ctrl+C to stop)"
streamlink --retry-streams 30 --retry-max 0 -o "$REC" "https://twitch.tv/$CHANNEL" best &
SL_PID=$!
trap 'kill $SL_PID 2>/dev/null || true' EXIT

python3 -u watcher.py "$CHANNEL" --rec "$REC" "$@" || true
