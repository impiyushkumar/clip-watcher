"""Post one finished clip to platforms right now, and log the links in the scoreboard."""
import os
import time

from clipwatcher import paths
from clipwatcher.log import log
from clipwatcher.publish import meta_graph, scoreboard, youtube
from clipwatcher.publish.post_text import build_caption, pick_hashtags, search_phrases, youtube_title

PLATFORMS = ("youtube", "instagram", "facebook")


def split_targets(targets_text):
    """"youtube, instagram" -> ["youtube", "instagram"]; "none" -> []."""
    return [target.strip() for target in (targets_text or "").split(",")
            if target.strip() and target.strip() != "none"]


def usable_targets(targets_text, explain=False):
    """Only the platforms that are actually logged in / set up."""
    usable = []
    for target in split_targets(targets_text):
        if target == "youtube" and not youtube.is_logged_in():
            reason = "not logged in (python3 -m clipwatcher youtube-login)"
        elif target in ("instagram", "facebook") and not meta_graph.is_configured():
            reason = "meta.json missing (python3 -m clipwatcher meta-setup)"
        elif target not in PLATFORMS:
            reason = "unknown platform"
        else:
            usable.append(target)
            continue
        if explain:
            log(f"{target}: {reason} - skipping")
    return usable


def resolve_path(path):
    """Queue items store paths relative to the repo root."""
    return path if os.path.isabs(path) else os.path.join(paths.ROOT_DIR, path)


def post_clip(queue_item, targets_text, hashtags, privacy):
    """Upload `queue_item` (see render/pipeline.py) to each target. Returns {platform: url}."""
    video_path = resolve_path(queue_item["final"])
    hook = queue_item["hook"]
    title = queue_item.get("title", "")
    stream_info = queue_item.get("meta") or {}
    urls = {}
    for target in split_targets(targets_text):
        try:
            caption = build_caption(hook, queue_item["source"], hashtags, stream_info, target, title=title)
            if target == "youtube":
                urls[target] = youtube.upload_short(video_path, youtube_title(hook, stream_info, title), caption,
                                                    " ".join(pick_hashtags(stream_info, hashtags)), privacy,
                                                    extra_tags=search_phrases(stream_info))
                if queue_item.get("comment"):
                    youtube.post_comment(urls[target], queue_item["comment"])
            elif target == "instagram":
                urls[target] = meta_graph.upload_instagram_reel(video_path, caption)
            elif target == "facebook":
                urls[target] = meta_graph.upload_facebook_reel(video_path, caption)
            else:
                log(f"unknown upload target {target!r}")
                continue
            log(f"UPLOADED to {target}: {urls[target]}")
        except Exception as error:
            log(f"{target} upload failed: {error}  (clip is still in {paths.READY_CLIPS_DIR})")
    scoreboard.upsert_row({
        "clip": queue_item["clip"], "created": queue_item["created"], "source": queue_item["source"],
        "hook": hook, "length_s": queue_item["length_s"],
        "youtube_url": urls.get("youtube", ""), "instagram_url": urls.get("instagram", ""),
        "facebook_url": urls.get("facebook", ""), "posted": time.strftime("%Y-%m-%d %H:%M")})
    return urls
