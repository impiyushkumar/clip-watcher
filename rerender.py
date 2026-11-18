#!/usr/bin/env python3
"""Re-render queued clips in the current style (captions, hook on/off, memes, zoom).

Old clips that were made with an earlier style still sit in clips/queue/. This rebuilds
each one from its raw cut in clips/raw/, keeping its score and what it was already posted to.
Clips whose raw cut no longer exists can be removed with --drop-missing.

    python rerender.py                 # re-render everything still waiting in the queue
    python rerender.py --drop-missing  # also remove queued clips that can't be rebuilt
Stop the service first so nothing posts mid-way:  sudo systemctl stop clip-watcher
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
# use the same settings as the service (config.txt -> the env names run.sh exports)
MAP = {"RES": "CW_RES", "THREADS": "CW_THREADS", "HOOK": "CW_HOOK", "ZOOM": "CW_ZOOM",
       "CTA": "CW_CTA", "GEMINI_API_KEY": "GEMINI_API_KEY", "GEMINI_MODEL": "GEMINI_MODEL",
       "MEME_CHANCE": "MEME_CHANCE", "MEME_SECONDS": "MEME_SECONDS", "MODEL": "MODEL", "TAGS": "TAGS"}
if os.path.exists("config.txt"):
    for line in open("config.txt", encoding="utf-8"):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.strip().split("=", 1)
            if k in MAP and v.strip("'\""):
                os.environ.setdefault(MAP[k], v.strip("'\""))
import postprocess  # noqa: E402  (after env is set)

drop = "--drop-missing" in sys.argv
done = missing = 0
for path in sorted(glob.glob("clips/queue/*.json")):
    item = json.load(open(path, encoding="utf-8"))
    name = item["clip"]
    raw = os.path.join("clips", "raw", name + ".mp4")
    if not os.path.exists(raw):
        missing += 1
        if drop:
            base = os.path.splitext(item["final"])[0]
            for ext in (".mp4", ".srt", ".txt"):
                if os.path.exists(base + ext):
                    os.remove(base + ext)
            os.remove(path)
            print(f"dropped (no raw cut): {name}")
        else:
            print(f"skip (no raw cut): {name}")
        continue
    length = int(float(item.get("length_s") or 30))
    platform, _, rest = name.partition("_")
    meta = item.get("meta") or {"creator": rest.rsplit("_", 2)[0], "game": ""}
    opts = {"model": os.environ.get("MODEL", "tiny"), "ready_dir": "clips/ready",
            "source_url": item.get("source", ""), "tags": os.environ.get("TAGS", "#gaming #shorts"),
            "hook_fallback": "wait for it...", "length": length, "upload": "none",
            "privacy": "public", "scoreboard": "clips/scoreboard.csv", "queue_dir": "clips/queue",
            "score": item.get("score", 0), "spike_at": max(3, round(length * 2 / 3)), "meta": meta}
    posted_to = item.get("posted_to", {})
    postprocess.process(raw, name, opts)
    new = json.load(open(path, encoding="utf-8"))
    if posted_to:
        new["posted_to"] = posted_to
    new["created_ts"] = item.get("created_ts", new["created_ts"])
    json.dump(new, open(path, "w", encoding="utf-8"), indent=1)
    done += 1
print(f"re-rendered {done} clip(s); {missing} without a raw cut"
      + (" (removed)" if drop and missing else ""))
