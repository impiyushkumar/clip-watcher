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
# housekeeping: drop recordings older than KEEP_REC_DAYS (default 1) and old raw clips
find rec -name '*.ended' -mtime +0 -delete 2>/dev/null || true
find rec -name '*.ts' -mtime +"${KEEP_REC_DAYS:-1}" -delete 2>/dev/null || true
find rec -mindepth 1 -maxdepth 1 -type d -mmin +180 -exec rm -rf {} + 2>/dev/null || true
find clips/raw -name '*.mp4' -mtime +3 -delete 2>/dev/null || true
SAFE="$(echo "$CHANNEL" | tr -cd 'A-Za-z0-9_-' | tail -c 40)"
# rolling buffer: the stream is saved as 10 s pieces; watcher.py keeps only the last
# KEEP_MINUTES (default 10) so disk use stays ~0.5 GB per channel instead of 3-4 GB/hour
REC="rec/${PLATFORM}_${SAFE}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$REC"

echo "Recording $URL -> $REC/  (Ctrl+C to stop)"
streamlink --retry-streams 30 --retry-max 0 -O "$URL" "${QUALITY:-best}" | \
  ffmpeg -hide_banner -loglevel error -i pipe:0 -map 0 -c copy -f segment -segment_time 10 \
    -segment_list "$REC/list.csv" -segment_list_type csv "$REC/seg_%06d.ts" &
SL_PID=$!
trap 'kill $SL_PID 2>/dev/null || true' EXIT

# when the stream ends: give pending clips 3 min to finish, then stop the watcher
( while kill -0 $SL_PID 2>/dev/null; do sleep 5; done
  echo "Stream ended - finishing pending clips..."; touch "$REC.ended"
  sleep "${STREAM_END_GRACE:-900}"   # safety net: force-stop after 15 min
  pkill -f -- "--rec $REC" 2>/dev/null ) &

python3 -u watcher.py "$CHANNEL" --platform "$PLATFORM" --rec "$REC" --source-url "$URL" "$@" || true
