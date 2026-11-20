#!/usr/bin/env bash
# Records ONE channel into a rolling buffer and runs the chat watcher on it.
# Usage: ./scripts/watch-channel.sh <channel> [--length 30] [--min 10] [--queue] ...
#   <channel>:  xqc | twitch:xqc | youtube:@handle | youtube:UC... | kick:slug
# Extra options go to clipwatcher/capture/channel_watcher.py (--help lists them).
# Exits when the stream ends and every pending clip is finished.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -lt 1 ]; then
  echo "Usage: $0 <channel|twitch:name|youtube:@handle|kick:name> [--min N] [--factor F] [--length S]"; exit 1
fi
CHANNEL_ARG="$1"; shift
lower() { echo "$1" | tr '[:upper:]' '[:lower:]'; }
case "$CHANNEL_ARG" in
  youtube:*|yt:*) PLATFORM=youtube; CHANNEL="${CHANNEL_ARG#*:}" ;;
  kick:*)         PLATFORM=kick;    CHANNEL="$(lower "${CHANNEL_ARG#*:}")" ;;
  twitch:*)       PLATFORM=twitch;  CHANNEL="$(lower "${CHANNEL_ARG#*:}")" ;;
  *)              PLATFORM=twitch;  CHANNEL="$(lower "$CHANNEL_ARG")" ;;
esac
case "$PLATFORM" in
  twitch)  STREAM_URL="https://twitch.tv/$CHANNEL" ;;
  kick)    STREAM_URL="https://kick.com/$CHANNEL" ;;
  youtube) case "$CHANNEL" in
             http*) STREAM_URL="$CHANNEL" ;;
             UC*)   STREAM_URL="https://www.youtube.com/channel/$CHANNEL/live" ;;
             *)     STREAM_URL="https://www.youtube.com/@${CHANNEL#@}/live" ;;
           esac ;;
esac

[ -f .venv/bin/activate ] && source .venv/bin/activate
[ -f config.txt ] && source config.txt
for tool in ffmpeg streamlink whisper python3; do
  command -v "$tool" >/dev/null || { echo "Missing $tool - run ./scripts/install.sh first"; exit 1; }
done

mkdir -p rec clips
# housekeeping: old end markers, recordings older than KEEP_REC_DAYS, stale buffers, old raw cuts
find rec -name '*.ended' -mtime +0 -delete 2>/dev/null || true
find rec -name '*.ts' -mtime +"${KEEP_REC_DAYS:-1}" -delete 2>/dev/null || true
find rec -mindepth 1 -maxdepth 1 -type d -mmin +180 -exec rm -rf {} + 2>/dev/null || true
find clips/raw -name '*.mp4' -mtime +3 -delete 2>/dev/null || true

# rolling buffer: 10 s pieces + list.csv; the watcher keeps only the last KEEP_MINUTES
SAFE_CHANNEL="$(echo "$CHANNEL" | tr -cd 'A-Za-z0-9_-' | tail -c 40)"
RECORDING_DIR="rec/${PLATFORM}_${SAFE_CHANNEL}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RECORDING_DIR"

echo "Recording $STREAM_URL -> $RECORDING_DIR/  (Ctrl+C to stop)"
streamlink --retry-streams 30 --retry-max 0 -O "$STREAM_URL" "${QUALITY:-best}" | \
  ffmpeg -hide_banner -loglevel error -i pipe:0 -map 0 -c copy -f segment -segment_time 10 \
    -segment_list "$RECORDING_DIR/list.csv" -segment_list_type csv "$RECORDING_DIR/seg_%06d.ts" &
RECORDER_PID=$!
trap 'kill $RECORDER_PID 2>/dev/null || true' EXIT

# when the stream ends: drop the .ended marker (the watcher finishes pending clips and exits);
# safety net: force-stop the watcher after STREAM_END_GRACE seconds (default 15 min)
( while kill -0 $RECORDER_PID 2>/dev/null; do sleep 5; done
  echo "Stream ended - finishing pending clips..."; touch "$RECORDING_DIR.ended"
  sleep "${STREAM_END_GRACE:-900}"
  pkill -f -- "--rec $RECORDING_DIR" 2>/dev/null ) &

python3 -u -m clipwatcher.capture.channel_watcher "$CHANNEL" --platform "$PLATFORM" \
  --rec "$RECORDING_DIR" --source-url "$STREAM_URL" "$@" || true
