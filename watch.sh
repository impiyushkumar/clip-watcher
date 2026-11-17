#!/usr/bin/env bash
# Usage: ./watch.sh <channel> [--min N] [--factor 2.5] [--model base]
#   <channel>:  xqc | twitch:xqc | youtube:@handle | kick:slug
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <channel|twitch:name|youtube:@handle|kick:name> [--min N] [--factor F] [--model base]"; exit 1
fi
ARG="$1"; shift
lower() { echo "$1" | tr '[:upper:]' '[:lower:]'; }
case "$ARG" in
  youtube:*|yt:*) PLATFORM=youtube; CHANNEL="${ARG#*:}" ;;
  kick:*)         PLATFORM=kick;    CHANNEL="$(lower "${ARG#*:}")" ;;
  twitch:*)       PLATFORM=twitch;  CHANNEL="$(lower "${ARG#*:}")" ;;
  *)              PLATFORM=twitch;  CHANNEL="$(lower "$ARG")" ;;
esac
case "$PLATFORM" in
  twitch)  URL="https://twitch.tv/$CHANNEL" ;;
  kick)    URL="https://kick.com/$CHANNEL" ;;
  youtube) case "$CHANNEL" in
             http*) URL="$CHANNEL" ;;
             UC*)   URL="https://www.youtube.com/channel/$CHANNEL/live" ;;
             *)     URL="https://www.youtube.com/@${CHANNEL#@}/live" ;;
           esac ;;
esac

[ -f .venv/bin/activate ] && source .venv/bin/activate
for t in ffmpeg streamlink whisper python3; do
  command -v "$t" >/dev/null || { echo "Missing $t - run ./install.sh first"; exit 1; }
done

mkdir -p rec clips
SAFE="$(echo "$CHANNEL" | tr -cd 'A-Za-z0-9_-' | tail -c 40)"
REC="rec/${PLATFORM}_${SAFE}_$(date +%Y%m%d_%H%M%S).ts"

echo "Recording $URL -> $REC  (Ctrl+C to stop)"
streamlink --retry-streams 30 --retry-max 0 -o "$REC" "$URL" best &
SL_PID=$!
trap 'kill $SL_PID 2>/dev/null || true' EXIT

python3 -u watcher.py "$CHANNEL" --platform "$PLATFORM" --rec "$REC" --source-url "$URL" "$@" || true
