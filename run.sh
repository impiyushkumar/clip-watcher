#!/usr/bin/env bash
# Headless runner (server / background): reads config.txt and watches forever.
# Each time a stream ends it starts over and waits for the next one.
cd "$(dirname "$0")"
source .venv/bin/activate
while true; do
  source config.txt
  export QUALITY KEEP_REC_DAYS CW_RCLONE_DEST
  [ "${UPLOAD:-none}" = "youtube" ] && [ ! -f token.json ] && { echo "token.json missing - uploads off"; UPLOAD=none; }
  ./watch.sh "$CHANNEL" --min "${MIN:-10}" --length "${LENGTH:-30}" --model "${MODEL:-base}" \
    --tags "${TAGS:-#gaming #shorts}" --upload "${UPLOAD:-none}" --privacy "${PRIVACY:-public}" < /dev/null
  echo "$(date) watcher stopped - restarting in 30s"; sleep 30
done
