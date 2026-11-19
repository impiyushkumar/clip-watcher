#!/usr/bin/env bash
# Runs everything, forever (the systemd service and start.sh call this):
#   * one scheduler that posts queued clips (if POSTS_PER_DAY or POST_EVERY is set)
#   * one watch-channel.sh loop per channel in CHANNELS='kaicenat,ohnepixel,kick:n3on'
# Each loop waits for its stream, clips it, and starts over when the stream ends.
# All other settings are read from config.txt by the Python code (clipwatcher/settings.py).
cd "$(dirname "$0")/.."
source .venv/bin/activate
source config.txt
CHANNELS="${CHANNELS:-${CHANNEL:-}}"
[ -z "$CHANNELS" ] && { echo "No channel set - run ./scripts/configure.sh"; exit 1; }
echo "Uploading to: $(python3 -m clipwatcher targets)"
echo "Watching: $CHANNELS"
trap 'kill 0' EXIT INT TERM
# buffers from a previous run are useless after a restart - clear them so disk stays small
rm -rf rec/*/ 2>/dev/null

if [ -n "${POSTS_PER_DAY:-}" ] || [ "${POST_EVERY:-0}" != "0" ]; then
  QUEUE_FLAG=(--queue)   # clips wait in clips/queue/ for the scheduler
  ( while true; do       # restart the scheduler if it ever crashes
      python3 -u -m clipwatcher.publish.scheduler
      sleep 30
    done ) &
else
  QUEUE_FLAG=()          # post each clip as soon as it is ready
fi

for CHANNEL_ARG in $(echo "$CHANNELS" | tr ',' ' '); do
  ( while true; do
      LENGTH_S="${LENGTH:-30}"
      [ "${AUTO_LEARN:-1}" = "1" ] && LENGTH_S="$(python3 -m clipwatcher pick-length "$LENGTH_S" 2>/dev/null || echo "$LENGTH_S")"
      ./scripts/watch-channel.sh "$CHANNEL_ARG" --length "$LENGTH_S" "${QUEUE_FLAG[@]}" < /dev/null 2>&1 \
        | sed -u "s|^|[$CHANNEL_ARG] |"
      echo "[$CHANNEL_ARG] $(date '+%H:%M') stream ended or offline - checking again in 30s"; sleep 30
    done ) &
done
wait
