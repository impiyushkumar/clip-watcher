"""Turns a raw 9:16 clip into a post-ready Short:
Whisper transcript -> word-timed captions burned in + hook text on top,
caption .txt (credit + hashtags), optional YouTube upload, scoreboard.csv row."""
import csv
import os
import subprocess
import textwrap
import time

_model = None
SCORE_COLS = ["clip", "created", "source", "hook", "length_s", "youtube_url",
              "views", "likes", "comments", "stats_updated", "instagram_url", "facebook_url", "posted"]


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def transcribe(path, model_name):
    global _model
    import whisper
    if _model is None:
        log(f"loading whisper model '{model_name}' (first time only)...")
        _model = whisper.load_model(model_name)
    return _model.transcribe(path, word_timestamps=True, fp16=False, verbose=None)


def ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def write_short_srt(result, path, max_words=3, max_chars=18):
    """Short-form style: 1-3 words on screen at a time."""
    chunks, cur = [], []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            cur.append(w)
            text = "".join(x["word"] for x in cur).strip()
            if len(cur) >= max_words or len(text) >= max_chars or text[-1:] in ".?!,":
                chunks.append(cur)
                cur = []
    if cur:
        chunks.append(cur)
    with open(path, "w", encoding="utf-8") as f:
        for i, c in enumerate(chunks, 1):
            text = "".join(x["word"] for x in c).strip().upper()
            f.write(f"{i}\n{ts(c[0]['start'])} --> {ts(c[-1]['end'])}\n{text}\n\n")
    return len(chunks)


def make_hook(result, fallback):
    try:  # learned by learn.py from your own results
        import json
        n = int(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            "clips", "auto.json"))).get("hook_words", 7))
    except (OSError, ValueError):
        n = 7
    words = (result.get("text") or "").strip().split()
    if len(words) < 3:
        return fallback.upper()
    hook = " ".join(words[:n]).rstrip(",.")
    return (hook + ("..." if len(words) > n else "")).upper()


def burn(raw, srt, hook, out, has_captions=True):
    d = os.path.dirname(os.path.abspath(out))
    hook_file = os.path.join(d, ".hook.txt")
    with open(hook_file, "w", encoding="utf-8") as f:
        f.write("\n".join(textwrap.wrap(hook, 18)[:3]))
    style = ("Fontname=DejaVu Sans,Bold=1,FontSize=13,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,BorderStyle=1,Outline=2.5,Shadow=0,"
             "Alignment=2,MarginV=70")
    subs = f"subtitles={os.path.basename(srt)}:force_style='{style}'," if has_captions else ""
    vf = (subs + f"drawtext=textfile=.hook.txt:font='Sans':fontsize=68:fontcolor=white:"
          f"line_spacing=12:box=1:boxcolor=black@0.65:boxborderw=24:"
          f"x=(w-text_w)/2:y=230")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-i", os.path.abspath(raw), "-vf", vf,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-c:a", "copy", "-movflags", "+faststart", os.path.basename(out)]
    ok = subprocess.run(cmd, cwd=d).returncode == 0
    os.remove(hook_file)
    return ok


def caption_text(hook, source_url, tags):
    return f"{hook.capitalize()}\n\n🎥 {source_url}\n\n{tags}\n"


def append_score(path, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCORE_COLS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in SCORE_COLS})


def process(raw, name, o):
    """o: dict with model, ready_dir, source_url, tags, hook_fallback, length,
    upload: comma list of youtube,instagram,facebook (or none), privacy, scoreboard"""
    os.makedirs(o["ready_dir"], exist_ok=True)
    log(f"transcribing {name} ...")
    result = transcribe(raw, o["model"])
    srt = os.path.join(o["ready_dir"], name + ".srt")
    n = write_short_srt(result, srt)
    hook = make_hook(result, o["hook_fallback"])
    final = os.path.join(o["ready_dir"], name + ".mp4")
    if not burn(raw, srt, hook, final, has_captions=n > 0):
        log(f"caption burn failed for {name}; keeping raw clip only")
        return
    cap = caption_text(hook, o["source_url"], o["tags"])
    with open(os.path.join(o["ready_dir"], name + ".txt"), "w", encoding="utf-8") as f:
        f.write(cap)
    log(f"READY: {final}  (hook: {hook!r}, {n} caption lines)")

    dest = os.environ.get("CW_RCLONE_DEST")  # e.g. gdrive:clip-watcher
    if dest:
        for ext in (".mp4", ".txt"):
            subprocess.run(["rclone", "copy", os.path.join(o["ready_dir"], name + ext), dest])
        log(f"synced to {dest}")

    item = {"clip": name, "final": final, "caption": cap, "hook": hook,
            "score": o.get("score", 0), "created": time.strftime("%Y-%m-%d %H:%M"),
            "created_ts": time.time(), "source": o["source_url"], "length_s": o["length"]}
    if o.get("queue_dir"):  # scheduled mode: poster.py posts the best clip every N hours
        import json
        os.makedirs(o["queue_dir"], exist_ok=True)
        with open(os.path.join(o["queue_dir"], name + ".json"), "w", encoding="utf-8") as f:
            json.dump(item, f, indent=1)
        log(f"queued for posting: {name} (score {item['score']})")
        return
    post_item(item, o["upload"], o["tags"], o["privacy"], o["scoreboard"], o["ready_dir"])


def post_item(item, upload, tags, privacy, scoreboard, ready_dir="clips/ready"):
    """Upload one finished clip to every target and log it. Returns {target: url}."""
    final, cap, hook = item["final"], item["caption"], item["hook"]
    targets = [t.strip() for t in upload.split(",") if t.strip() and t.strip() != "none"]
    urls = {}
    for t in targets:
        try:
            if t == "youtube":
                import uploader
                title = hook.capitalize()[:85] + " #Shorts"
                urls[t] = uploader.upload(final, title, cap, tags, privacy)
            elif t == "instagram":
                import meta_uploader
                urls[t] = meta_uploader.upload_instagram(final, cap)
            elif t == "facebook":
                import meta_uploader
                urls[t] = meta_uploader.upload_facebook(final, cap)
            else:
                log(f"unknown upload target {t!r}")
                continue
            log(f"UPLOADED to {t}: {urls[t]}")
        except Exception as e:
            log(f"{t} upload failed: {e}  (clip is still in {ready_dir})")
    append_score(scoreboard, {
        "clip": item["clip"], "created": item["created"], "source": item["source"],
        "hook": hook, "length_s": item["length_s"],
        "youtube_url": urls.get("youtube", ""), "instagram_url": urls.get("instagram", ""),
        "facebook_url": urls.get("facebook", ""), "posted": time.strftime("%Y-%m-%d %H:%M")})
    return urls
