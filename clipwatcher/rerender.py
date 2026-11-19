"""Re-render queued clips in the current style (captions, hook on/off, memes, zoom).

Rebuilds every clip still waiting in clips/queue/ from its raw cut in clips/raw/,
keeping its score, creation time and what it was already posted to. Note: a clip's raw
cut is deleted after rendering, so only clips whose raw cut still exists can be rebuilt.

    python3 -m clipwatcher rerender                 # stop the service first
    python3 -m clipwatcher rerender --drop-missing  # also remove clips that can't be rebuilt
"""
import glob
import json
import os

from clipwatcher import paths, settings
from clipwatcher.log import log
from clipwatcher.publish.cleanup import delete_clip_files


def rerender_queue(drop_missing=False):
    from clipwatcher.render.pipeline import ClipJob, process_clip

    rebuilt_count = missing_count = 0
    for json_path in sorted(glob.glob(os.path.join(paths.QUEUE_DIR, "*.json"))):
        with open(json_path, encoding="utf-8") as item_file:
            old_item = json.load(item_file)
        clip_name = old_item["clip"]
        raw_path = os.path.join(paths.RAW_CLIPS_DIR, clip_name + ".mp4")
        if not os.path.exists(raw_path):
            missing_count += 1
            if drop_missing:
                delete_clip_files(old_item)
                os.remove(json_path)
                log(f"dropped (no raw cut): {clip_name}")
            else:
                log(f"skip (no raw cut): {clip_name}")
            continue
        length_s = int(float(old_item.get("length_s") or 30))
        _platform, _separator, rest = clip_name.partition("_")
        stream_info = old_item.get("meta") or {"creator": rest.rsplit("_", 2)[0], "game": ""}
        job = ClipJob(clip_name=clip_name, raw_path=raw_path, source_url=old_item.get("source", ""),
                      stream_info=stream_info, hashtags=settings.HASHTAGS, length_s=length_s,
                      spike_at_s=max(3, round(length_s * 2 / 3)), score=old_item.get("score", 0),
                      whisper_model=settings.WHISPER_MODEL, queue_for_schedule=True)
        new_item = process_clip(job)
        if new_item is None:
            continue
        if old_item.get("posted_to"):
            new_item["posted_to"] = old_item["posted_to"]
        new_item["created_ts"] = old_item.get("created_ts", new_item["created_ts"])
        with open(json_path, "w", encoding="utf-8") as item_file:
            json.dump(new_item, item_file, indent=1)
        rebuilt_count += 1
    log(f"re-rendered {rebuilt_count} clip(s); {missing_count} without a raw cut"
        + (" (removed)" if drop_missing and missing_count else ""))
