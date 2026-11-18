#!/usr/bin/env bash
# Headless runner (server / background): reads config.txt and watches forever.
# Each time a stream ends it starts over and waits for the next one.
cd "$(dirname "$0")"
source .venv/bin/activate
while true; do
  source config.txt
  export QUALITY KEEP_REC_DAYS CW_RCLONE_DEST
  UPLOAD="$(UPLOAD="$UPLOAD" ./check_uploads.sh)"; echo "Uploading to: $UPLOAD"
  if [ "${AUTO_LEARN:-1}" = "1" ]; then
    LENGTH="$(python3 learn.py --pick-length "${LENGTH:-30}" 2>/dev/null || echo "${LENGTH:-30}")"
    echo "Self-learning on: clip length this stream = ${LENGTH}s"
  fi
  QARGS=()
  if [ -n "${POSTS_PER_DAY:-}" ] || [ "${POST_EVERY:-0}" != "0" ]; then
    QARGS=(--queue clips/queue --upload none)
    pkill -f "poster.py" 2>/dev/null
    CW_ALLOWED="$UPLOAD" python3 -u poster.py --per-day "${POSTS_PER_DAY:-}" --every "${POST_EVERY:-4}" \
      --upload "$UPLOAD" --tags "${TAGS:-#gaming #shorts}" \
      --privacy "${PRIVACY:-public}" &
  fi
  ./watch.sh "$CHANNEL" --min "${MIN:-10}" --length "${LENGTH:-30}" --model "${MODEL:-base}" \
    --tags "${TAGS:-#gaming #shorts}" --upload "${UPLOAD:-none}" --privacy "${PRIVACY:-public}" "${QARGS[@]}" < /dev/null
  echo "$(date) watcher stopped - restarting in 30s"; sleep 30
done
