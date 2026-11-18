#!/usr/bin/env bash
# Asks the setup questions and writes config.txt (run again any time to change settings).
cd "$(dirname "$0")"
echo "=== clip-watcher setup (saved to config.txt) ==="
read -rp "Channel (xqc, youtube:@handle, kick:name): " CHANNEL
read -rp "Min chat messages per 10s for a spike [10]: " MIN
read -rp "Clip length in seconds [30]: " LENGTH
read -rp "Hashtags [#gaming #shorts #twitch]: " TAGS
echo "Auto-upload targets: youtube, instagram, facebook (comma separated) or none"
read -rp "Upload to [none]: " UPLOAD
read -rp "Post one clip every N hours (0 = post every clip right away) [4]: " POST_EVERY
read -rp "Whisper model tiny/base/small [base]: " MODEL
read -rp "Recording quality (best, 720p60, 720p...) [best]: " QUALITY
UPLOAD="$(echo "${UPLOAD:-none}" | tr -d ' ' | tr '[:upper:]' '[:lower:]')"
{
  echo "CHANNEL='$CHANNEL'"; echo "MIN=${MIN:-10}"; echo "LENGTH=${LENGTH:-30}"
  echo "TAGS='${TAGS:-#gaming #shorts #twitch}'"; echo "UPLOAD='$UPLOAD'"
  echo "PRIVACY=public"; echo "MODEL=${MODEL:-base}"; echo "QUALITY='${QUALITY:-best}'"
  echo "POST_EVERY=${POST_EVERY:-4}"; echo "KEEP_REC_DAYS=1"
  echo "# Google Drive sync (after 'rclone config'), e.g. CW_RCLONE_DEST='gdrive:clip-watcher'"
  echo "CW_RCLONE_DEST=''"
} > config.txt
echo "Saved config.txt"
