#!/usr/bin/env python3
"""Self-learning loop: reads how your posts performed and tunes clip-watcher.

What it learns (from clips/scoreboard.csv, views from the YouTube API):
  * best clip length      -> used automatically for the next stream
  * best posting hours    -> poster.py waits for a good hour (max one extra interval)
  * best hook style       -> short vs long hooks, question hooks
It keeps experimenting (about 1 in 5 streams tries a different length) so it never gets stuck.
Report: clips/learning.md   Settings it applies: clips/auto.json

  python learn.py                    # refresh stats + relearn now
  python learn.py --pick-length 30   # length for the next stream (used by run.sh/start.sh)
"""
import csv
import json
import os
import random
import statistics
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SCORE = os.path.join(HERE, "clips", "scoreboard.csv")
AUTO = os.path.join(HERE, "clips", "auto.json")
REPORT = os.path.join(HERE, "clips", "learning.md")
LENGTHS = [15, 20, 30, 45]
MIN_SAMPLES = 8        # posts with views before trusting the data
MIN_AGE_H = 24         # judge a post only after it had a day to get views
EXPLORE = 0.2          # share of streams that test a non-best length


def load_auto():
    try:
        return json.load(open(AUTO))
    except (OSError, ValueError):
        return {}


def rows_with_views():
    if not os.path.exists(SCORE):
        return []
    out = []
    for r in csv.DictReader(open(SCORE, encoding="utf-8")):
        posted = r.get("posted") or r.get("created") or ""
        try:
            ts = time.mktime(time.strptime(posted, "%Y-%m-%d %H:%M"))
        except ValueError:
            continue
        if r.get("views") and time.time() - ts >= MIN_AGE_H * 3600:
            r["_views"], r["_ts"] = int(r["views"]), ts
            out.append(r)
    return out


def ranked(groups):
    """median views per group, best first (groups with 2+ posts only)."""
    res = [(statistics.median(v), k, len(v)) for k, v in groups.items() if len(v) >= 2]
    return sorted(res, reverse=True)


def learn():
    rows = rows_with_views()
    auto = load_auto()
    lines = [f"# What clip-watcher learned ({time.strftime('%Y-%m-%d %H:%M')})", "",
             f"Posts with views (older than {MIN_AGE_H}h): **{len(rows)}**", ""]
    if len(rows) < MIN_SAMPLES:
        lines.append(f"Still exploring - need {MIN_SAMPLES} judged posts before changing settings.")
    else:
        by_len, by_hour, by_hook = defaultdict(list), defaultdict(list), defaultdict(list)
        for r in rows:
            v = r["_views"]
            by_len[int(float(r.get("length_s") or 30))].append(v)
            by_hour[time.localtime(r["_ts"]).tm_hour].append(v)
            hook = r.get("hook", "")
            by_hook["short hook (<=4 words)" if len(hook.split()) <= 4 else "long hook (5+ words)"].append(v)
            by_hook["question hook" if "?" in hook else "statement hook"].append(v)

        hk = {k: m for m, k, n in ranked(by_hook)}
        if "short hook (<=4 words)" in hk and "long hook (5+ words)" in hk:
            auto["hook_words"] = 4 if hk["short hook (<=4 words)"] >= hk["long hook (5+ words)"] else 7
        lens = ranked(by_len)
        if lens:
            auto["length"] = lens[0][1]
        hours = ranked(by_hour)
        overall = statistics.median(r["_views"] for r in rows)
        auto["best_hours"] = sorted(h for med, h, n in hours if med >= overall)[:8]
        auto["median_views"] = overall

        lines += ["## Clip length (median views)"]
        lines += [f"- {k}s: {int(m)} views ({n} posts)" for m, k, n in lens] or ["- not enough variety yet"]
        lines += ["", "## Posting hour (median views)"]
        lines += [f"- {k:02d}:00: {int(m)} views ({n} posts)" for m, k, n in hours[:8]] or ["- not enough data yet"]
        lines += ["", "## Hook style (median views)"]
        lines += [f"- {k}: {int(m)} views ({n} posts)" for m, k, n in ranked(by_hook)]
        best = sorted(rows, key=lambda r: r["_views"], reverse=True)[:5]
        lines += ["", "## Top posts"] + [f"- {r['_views']} views - {r['hook']}" for r in best]
        lines += ["", "## Applied automatically",
                  f"- clip length: **{auto.get('length')}s** (still tests others ~{int(EXPLORE*100)}% of streams)",
                  f"- preferred posting hours: {auto.get('best_hours') or 'any'}",
                  f"- hook length: up to {auto.get('hook_words', 7)} words"]
    auto["updated"] = time.strftime("%Y-%m-%d %H:%M")
    os.makedirs(os.path.dirname(AUTO), exist_ok=True)
    json.dump(auto, open(AUTO, "w"), indent=1)
    open(REPORT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return auto


def refresh_and_learn():
    try:
        import uploader
        if os.path.exists(uploader.TOKEN) and os.path.exists(SCORE):
            uploader.update_stats(SCORE)
    except Exception as e:
        print(f"stats refresh skipped: {e}")
    return learn()


def pick_length(default):
    auto = load_auto()
    tried = {int(float(r.get("length_s") or 0)) for r in csv.DictReader(open(SCORE))} if os.path.exists(SCORE) else set()
    untested = [l for l in LENGTHS if l not in tried]
    if "length" not in auto:            # still exploring: try each length once, then default
        return untested[0] if untested and tried else default
    if random.random() < EXPLORE:       # keep testing so it can find something better
        return random.choice([l for l in LENGTHS if l != auto["length"]])
    return auto["length"]


if __name__ == "__main__":
    if "--pick-length" in sys.argv:
        i = sys.argv.index("--pick-length")
        default = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 30
        print(pick_length(default))
    else:
        refresh_and_learn()
        print(open(REPORT).read())
