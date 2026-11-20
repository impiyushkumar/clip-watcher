#!/usr/bin/env bash
# Asks the setup questions and writes config.txt in the repo root (run again any time).
# Every setting, including ones not asked here, is documented in config.example.txt.
cd "$(dirname "$0")/.."
echo "=== clip-watcher setup (saved to config.txt) ==="
echo "Channels to watch, comma separated (up to 3 on a 2-CPU server), e.g. kaicenat,ohnepixel,kick:n3on"
read -rp "Channels: " CHANNELS
read -rp "Min chat messages per 10s for a spike [10]: " MIN
read -rp "Clip length in seconds [15]: " LENGTH
read -rp "Hashtags [#gta6 #shorts]: " TAGS
echo "Auto-upload targets: youtube, instagram, facebook (comma separated) or none"
read -rp "Upload to [none]: " UPLOAD
read -rp "Posts per day per platform [youtube=6,instagram=10,facebook=10]: " POSTS_PER_DAY
read -rp "Whisper model tiny/base/small [small]: " MODEL
read -rp "Gemini API key (free, https://aistudio.google.com/apikey - strongly recommended) []: " GEMINI_API_KEY
read -rp "Recording quality (best, 720p60, 720p...) [best]: " QUALITY
UPLOAD="$(echo "${UPLOAD:-none}" | tr -d ' ' | tr '[:upper:]' '[:lower:]')"
{
  echo "CHANNELS='$(echo "$CHANNELS" | tr -d ' ')'"; echo "MIN=${MIN:-10}"; echo "LENGTH=${LENGTH:-15}"
  echo "TAGS='${TAGS:-#gta6 #shorts}'"; echo "UPLOAD='$UPLOAD'"
  echo "PRIVACY=public"; echo "MODEL=${MODEL:-small}"; echo "GEMINI_API_KEY='${GEMINI_API_KEY:-}'"; echo "LAYOUT=split"; echo "QUALITY='${QUALITY:-best}'"
  echo "POSTS_PER_DAY='${POSTS_PER_DAY:-youtube=6,instagram=10,facebook=10}'"; echo "KEEP_REC_DAYS=1"; echo "AUTO_LEARN=1"
  echo "# Google Drive sync (after 'rclone config'), e.g. CW_RCLONE_DEST='gdrive:clip-watcher'"
  echo "CW_RCLONE_DEST=''"
} > config.txt
echo "Saved config.txt"
