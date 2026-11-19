"""Self-learning: reads how your posts performed and tunes clip-watcher. No outside AI.

From clips/scoreboard.csv (views come from the YouTube API) it learns:
    best clip length    -> used for the next stream (scripts/run.sh asks pick-length)
    best posting hours  -> the scheduler waits for a good hour (max one extra interval)
    best hook length    -> reported in learning.md (hooks are written by render/copywriting.py)
About 1 in 5 streams still tests a different length, so it keeps exploring.
Output: clips/auto.json (applied settings) and clips/learning.md (human report).

    python3 -m clipwatcher learn            # refresh stats + relearn now
    python3 -m clipwatcher pick-length 30   # length for the next stream
"""
import json
import os
import random
import statistics
import time
from collections import defaultdict

from clipwatcher import paths
from clipwatcher.publish import scoreboard

CANDIDATE_LENGTHS_S = [10, 15, 20, 30]
MIN_JUDGED_POSTS = 8     # posts with views before trusting the data
MIN_POST_AGE_H = 24      # judge a post only after it had a day to get views
EXPLORE_SHARE = 0.2      # share of streams that test a non-best length
SHORT_HOOK, LONG_HOOK = "short hook (<=4 words)", "long hook (5+ words)"


def load_auto_settings():
    try:
        with open(paths.AUTO_SETTINGS_FILE) as auto_file:
            return json.load(auto_file)
    except (OSError, ValueError):
        return {}


def judged_rows():
    """Scoreboard rows that have views and are at least MIN_POST_AGE_H old."""
    rows = []
    for row in scoreboard.read_rows():
        posted = row.get("posted") or row.get("created") or ""
        try:
            posted_ts = time.mktime(time.strptime(posted, "%Y-%m-%d %H:%M"))
        except ValueError:
            continue
        if row.get("views") and time.time() - posted_ts >= MIN_POST_AGE_H * 3600:
            row["_views"], row["_posted_ts"] = int(row["views"]), posted_ts
            rows.append(row)
    return rows


def rank_by_median(views_by_group):
    """[(median_views, group, post_count)] best first, groups with 2+ posts only."""
    ranking = [(statistics.median(views), group, len(views))
               for group, views in views_by_group.items() if len(views) >= 2]
    return sorted(ranking, reverse=True)


def learn():
    """Recompute auto.json and learning.md. Returns the auto settings dict."""
    rows = judged_rows()
    auto_settings = load_auto_settings()
    report = [f"# What clip-watcher learned ({time.strftime('%Y-%m-%d %H:%M')})", "",
              f"Posts with views (older than {MIN_POST_AGE_H}h): **{len(rows)}**", ""]
    if len(rows) < MIN_JUDGED_POSTS:
        report.append(f"Still exploring - need {MIN_JUDGED_POSTS} judged posts before changing settings.")
    else:
        views_by_length, views_by_hour, views_by_hook = defaultdict(list), defaultdict(list), defaultdict(list)
        for row in rows:
            views = row["_views"]
            views_by_length[int(float(row.get("length_s") or 30))].append(views)
            views_by_hour[time.localtime(row["_posted_ts"]).tm_hour].append(views)
            hook = row.get("hook", "")
            views_by_hook[SHORT_HOOK if len(hook.split()) <= 4 else LONG_HOOK].append(views)
            views_by_hook["question hook" if "?" in hook else "statement hook"].append(views)

        hook_ranking = rank_by_median(views_by_hook)
        hook_medians = {group: median for median, group, _count in hook_ranking}
        if SHORT_HOOK in hook_medians and LONG_HOOK in hook_medians:
            auto_settings["hook_words"] = 4 if hook_medians[SHORT_HOOK] >= hook_medians[LONG_HOOK] else 7
        length_ranking = rank_by_median(views_by_length)
        if length_ranking:
            auto_settings["length"] = length_ranking[0][1]
        hour_ranking = rank_by_median(views_by_hour)
        overall_median = statistics.median(row["_views"] for row in rows)
        auto_settings["best_hours"] = sorted(hour for median, hour, _count in hour_ranking
                                             if median >= overall_median)[:8]
        auto_settings["median_views"] = overall_median

        report += ["## Clip length (median views)"]
        report += [f"- {length}s: {int(median)} views ({count} posts)"
                   for median, length, count in length_ranking] or ["- not enough variety yet"]
        report += ["", "## Posting hour (median views)"]
        report += [f"- {hour:02d}:00: {int(median)} views ({count} posts)"
                   for median, hour, count in hour_ranking[:8]] or ["- not enough data yet"]
        report += ["", "## Hook style (median views)"]
        report += [f"- {group}: {int(median)} views ({count} posts)" for median, group, count in hook_ranking]
        top_rows = sorted(rows, key=lambda row: row["_views"], reverse=True)[:5]
        report += ["", "## Top posts"] + [f"- {row['_views']} views - {row['hook']}" for row in top_rows]
        report += ["", "## Applied automatically",
                   f"- clip length: **{auto_settings.get('length')}s** "
                   f"(still tests others ~{int(EXPLORE_SHARE * 100)}% of streams)",
                   f"- preferred posting hours: {auto_settings.get('best_hours') or 'any'}",
                   f"- hook length: up to {auto_settings.get('hook_words', 7)} words"]
    auto_settings["updated"] = time.strftime("%Y-%m-%d %H:%M")
    os.makedirs(os.path.dirname(paths.AUTO_SETTINGS_FILE), exist_ok=True)
    with open(paths.AUTO_SETTINGS_FILE, "w") as auto_file:
        json.dump(auto_settings, auto_file, indent=1)
    with open(paths.LEARNING_REPORT_FILE, "w", encoding="utf-8") as report_file:
        report_file.write("\n".join(report) + "\n")
    return auto_settings


def refresh_and_learn():
    """Pull fresh YouTube views (if logged in), then learn."""
    try:
        from clipwatcher.publish import youtube
        if youtube.is_logged_in() and os.path.exists(paths.SCOREBOARD_FILE):
            youtube.refresh_stats()
    except Exception as error:
        print(f"stats refresh skipped: {error}")
    return learn()


def pick_clip_length(default_s):
    """Clip length for the next stream: explore untested lengths first, then mostly the best."""
    auto_settings = load_auto_settings()
    tried_lengths = {int(float(row.get("length_s") or 0)) for row in scoreboard.read_rows()}
    untested = [length for length in CANDIDATE_LENGTHS_S if length not in tried_lengths]
    if "length" not in auto_settings:  # still exploring: try each length once, then the default
        return untested[0] if untested and tried_lengths else default_s
    if random.random() < EXPLORE_SHARE:
        return random.choice([length for length in CANDIDATE_LENGTHS_S if length != auto_settings["length"]])
    return auto_settings["length"]
