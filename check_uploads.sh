#!/usr/bin/env bash
# Prints the usable upload targets from $UPLOAD, dropping ones that are not set up yet.
OUT=""
for t in $(echo "${UPLOAD:-none}" | tr ',' ' '); do
  case "$t" in
    youtube)  [ -f token.json ] && OUT="$OUT,youtube" || echo "youtube: not logged in (python3 uploader.py --login) - skipping" >&2 ;;
    instagram|facebook) [ -f meta.json ] && OUT="$OUT,$t" || echo "$t: meta.json missing (python3 meta_uploader.py --setup) - skipping" >&2 ;;
  esac
done
OUT="${OUT#,}"; echo "${OUT:-none}"
