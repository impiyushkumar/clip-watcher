#!/usr/bin/env bash
# Runner (server service, or called by start.sh): watches every channel in
# CHANNELS='kaicenat,ohnepixel,kick:n3on' at the same time, forever.
# Each channel waits for its stream, clips it, and starts over when the stream ends.
# All clips go into one queue; poster.py posts the best ones on your schedule.
cd "$(dirname "$0")"
source .venv/bin/activate
source config.txt
export QUALITY KEEP_REC_DAYS CW_RCLONE_DEST KEEP_MINUTES KEEP_CLIP_DAYS
# small-server tuning (set in config.txt): output size, CPU threads per job
export CW_RES="${RES:-1080x1920}" CW_THREADS="${THREADS:-0}" CW_LAYOUT="${LAYOUT:-crop}" CW_CTA="${CTA:-Follow for daily stream clips 🔥}" GEMINI_API_KEY="${GEMINI_API_KEY:-}" GEMINI_MODEL="${GEMINI_MODEL:-gemini-flash-latest}" CW_ZOOM="${ZOOM:-1}"
CHANNELS="${CHANNELS:-$CHANNEL}"
[ -z "$CHANNELS" ] && { echo "No channel set - run ./configure.sh"; exit 1; }
UPLOAD="$(UPLOAD="$UPLOAD" ./check_uploads.sh)"; echo "Uploading to: $UPLOAD"
echo "Watching: $CHANNELS"
trap 'kill 0' EXIT INT TERM

# scheduler: one poster for all channels (restarts itself if it crashes)
if [ -n "${POSTS_PER_DAY:-}" ] || [ "${POST_EVERY:-0}" != "0" ]; then
  QARGS=(--queue clips/queue --upload none)
  ( while true; do
      CW_ALLOWED="$UPLOAD" python3 -u poster.py --per-day "${POSTS_PER_DAY:-}" --every "${POST_EVERY:-4}" \
        --upload "$UPLOAD" --tags "${TAGS:-#gaming #shorts}" --privacy "${PRIVACY:-public}"
      sleep 30
    done ) &
else
  QARGS=(--upload "$UPLOAD")
fi

# one watcher loop per channel
for CH in $(echo "$CHANNELS" | tr ',' ' '); do
  ( while true; do
      L="${LENGTH:-30}"
      [ "${AUTO_LEARN:-1}" = "1" ] && L="$(python3 learn.py --pick-length "$L" 2>/dev/null || echo "$L")"
      ./watch.sh "$CH" --min "${MIN:-10}" --factor "${FACTOR:-2.5}" --cooldown "${COOLDOWN:-0}" --length "$L" --model "${MODEL:-base}" \
        --tags "${TAGS:-#gaming #shorts}" --privacy "${PRIVACY:-public}" "${QARGS[@]}" < /dev/null 2>&1 \
        | sed -u "s|^|[$CH] |"
      echo "[$CH] $(date '+%H:%M') stream ended or offline - checking again in 30s"; sleep 30
    done ) &
done
wait
