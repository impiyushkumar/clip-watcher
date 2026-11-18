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
        import torch
        n = int(os.environ.get("CW_THREADS", "0") or 0)
        if n > 0:
            torch.set_num_threads(n)
        _model = whisper.load_model(model_name)
    return _model.transcribe(path, word_timestamps=True, fp16=False, verbose=None)


def ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def caption_chunks(result, max_words=3, max_chars=16):
    """1-3 words at a time -> [(start, end, TEXT)]"""
    chunks, cur = [], []
    for seg in result.get("segments", []):
        for wd in seg.get("words", []):
            cur.append(wd)
            text = "".join(x["word"] for x in cur).strip()
            if len(cur) >= max_words or len(text) >= max_chars or text[-1:] in ".?!,":
                chunks.append(cur)
                cur = []
    if cur:
        chunks.append(cur)
    return [(c[0]["start"], c[-1]["end"], "".join(x["word"] for x in c).strip().upper().rstrip(","))
            for c in chunks]


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


def gemini_json(prompt, temperature=0.9):
    """Call Gemini and return parsed JSON, or None. Retries busy errors (429/5xx) and
    falls back to backup models, because a busy model is common at peak times."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    import json
    import requests
    models = [os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
              "gemini-2.5-flash", "gemini-2.5-flash-lite"]
    last = ""
    for model in dict.fromkeys(models):          # unique, in order
        for attempt in range(3):
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"responseMimeType": "application/json",
                                               "temperature": temperature}},
                    timeout=30)
                if r.status_code in (429, 500, 502, 503, 504):
                    last = f"{model}: {r.status_code}"
                    time.sleep(2 * (attempt + 1))
                    continue
                if r.status_code == 404:          # model name not available -> next model
                    last = f"{model}: not found"
                    break
                r.raise_for_status()
                return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            except Exception as e:
                last = f"{model}: {e}"
                time.sleep(2)
    log(f"Gemini unavailable ({last}) - using the normal hook")
    return None


def ai_hook(transcript, meta):
    """Meme-style hook from Gemini (optional: GEMINI_API_KEY in config.txt), else None."""
    if not os.environ.get("GEMINI_API_KEY") or not transcript:
        return None
    prompt = (
        "You write on-screen hooks for viral short-form clips of live streamers.\n"
        f"Streamer: {meta.get('creator') or 'unknown'}. Game/category: {meta.get('game') or 'unknown'}.\n"
        f"What was said in the 30-second clip (auto transcript, may have errors):\n\"{transcript[:1500]}\"\n\n"
        "Write ONE hook of 3-8 words in meme / Gen-Z clip-page style (e.g. 'HE REALLY THOUGHT HE HAD IT', "
        "'CHAT WAS NOT READY FOR THIS'). Only use what the transcript supports - no made-up events, "
        "no slurs, no claims about real people beyond the clip. No emojis, no hashtags, no quotes. "
        'Reply as JSON: {"hook": "..."}')
    out = gemini_json(prompt) or {}
    hook = re.sub(r"[^A-Za-z0-9 '?!.,&-]", "", str(out.get("hook", "")).strip()).upper()
    return hook if 2 <= len(hook.split()) <= 10 else None


def make_hook(result, fallback, meta=None):
    ai = ai_hook((result.get("text") or "").strip(), meta or {})
    if ai:
        return ai
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


HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")
FONT = os.environ.get("CW_FONT", "Anton")


def ass_time(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


def write_ass(path, chunks, hook, w=1080, h=1920):
    """Clip-page style: big hook at the top (no box), word-by-word captions that pop in,
    alternating white / yellow, thick black outline. Sizes are for a 1080x1920 canvas."""
    hook_lines = "\\N".join(textwrap.wrap(hook, 16)[:3])
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,{FONT},104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,7,3,8,60,60,230,1
Style: Cap,{FONT},128,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,2,0,1,8,4,2,60,60,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    if os.environ.get("CW_HOOK", "1") == "1":   # HOOK=0 in config.txt -> no text at the top
        ev.append(f"Dialogue: 1,0:00:00.00,9:00:00.00,Hook,,0,0,0,,{{\\fad(150,0)}}{hook_lines}")
    for i, (st, en, text) in enumerate(chunks):
        colour = "&H0000F0FF&" if i % 2 else "&H00FFFFFF&"  # yellow / white
        pop = "{\\fscx70\\fscy70\\t(0,90,\\fscx108\\fscy108)\\t(90,160,\\fscx100\\fscy100)\\c" + colour + "}"
        ev.append(f"Dialogue: 0,{ass_time(st)},{ass_time(max(en, st + 0.25))},Cap,,0,0,0,,{pop}{text}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(ev) + "\n")


MEME_DIR = os.path.join(HERE, "memes")
MEME_EXT = (".mp4", ".mov", ".webm", ".mkv", ".gif")


def list_memes():
    try:
        return sorted(f for f in os.listdir(MEME_DIR) if f.lower().endswith(MEME_EXT))
    except OSError:
        return []


def pick_meme(transcript, meta):
    """Choose a meme from memes/ that fits the moment (Gemini if available, else keywords),
    or None. File names describe the meme, e.g. 'shocked-scream.mp4'."""
    memes = list_memes()
    if not memes or random.random() > float(os.environ.get("MEME_CHANCE", "0.6")):
        return None
    if os.environ.get("GEMINI_API_KEY"):
        prompt = ("Pick the reaction meme that fits this live-stream clip best, or NONE if none fits.\n"
                  f"Streamer: {meta.get('creator')}. Game: {meta.get('game')}.\n"
                  f"Transcript: \"{transcript[:1200]}\"\n"
                  f"Memes (file names describe them): {memes}\n"
                  'Reply as JSON: {"meme": "<exact file name or NONE>"}')
        out = gemini_json(prompt, temperature=0.4)
        if out is not None:
            choice = out.get("meme")
            return choice if choice in memes else None
    words = set(re.findall(r"[a-z]+", transcript.lower()))
    scored = [(len(words & set(re.findall(r"[a-z]+", m.lower()))), m) for m in memes]
    best = max(scored)
    return best[1] if best[0] > 0 else random.choice(memes)


def insert_meme(video, meme, at, out, w, h):
    """Cut to the meme for up to MEME_SECONDS at `at` seconds, then back to the clip."""
    secs = float(os.environ.get("MEME_SECONDS", "2.2"))
    mpath = os.path.join(MEME_DIR, meme)
    has_audio = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                                "stream=index", "-of", "csv=p=0", mpath],
                               capture_output=True, text=True).stdout.strip() != ""
    norm = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=30,setsar=1,format=yuv420p")
    fc = (f"[0:v]trim=0:{at},setpts=PTS-STARTPTS,fps=30,format=yuv420p[v1];"
          f"[0:a]atrim=0:{at},asetpts=PTS-STARTPTS,aresample=44100[a1];"
          f"[1:v]trim=0:{secs},setpts=PTS-STARTPTS,{norm}[mv];"
          + (f"[1:a]atrim=0:{secs},asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo[ma];"
             if has_audio else f"anullsrc=r=44100:cl=stereo,atrim=0:{secs}[ma];")
          + f"[0:v]trim=start={at},setpts=PTS-STARTPTS,fps=30,format=yuv420p[v2];"
          f"[0:a]atrim=start={at},asetpts=PTS-STARTPTS,aresample=44100[a2];"
          f"[a1]aformat=channel_layouts=stereo[a1s];[a2]aformat=channel_layouts=stereo[a2s];"
          f"[v1][a1s][mv][ma][v2][a2s]concat=n=3:v=1:a=1[v][a]")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video,
           "-stream_loop", "-1" if meme.lower().endswith(".gif") else "0", "-i", mpath,
           "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
           "-threads", os.environ.get("CW_THREADS", "0"),
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out]
    return subprocess.run(cmd).returncode == 0


def burn(raw, srt, hook, out, has_captions=True, chunks=None, spike_at=None):
    d = os.path.dirname(os.path.abspath(out))
    ass = os.path.join(d, ".style.ass")
    w, h = os.environ.get("CW_RES", "1080x1920").split("x")
    write_ass(ass, chunks if has_captions else [], hook, int(w), int(h))
    vf = ""
    if spike_at is not None and os.environ.get("CW_ZOOM", "1") == "1":
        # meme "punch-in": quick 12% zoom right on the hype moment
        a, b = max(0, spike_at - 0.3), spike_at + 1.4
        vf += (f"zoompan=z='if(between(in_time,{a:.2f},{b:.2f}),1.12,1)':d=1:"
               f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=30,")
    vf += f"subtitles=.style.ass:fontsdir='{FONT_DIR}'"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-i", os.path.abspath(raw), "-vf", vf,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
           "-threads", os.environ.get("CW_THREADS", "0"),
           "-c:a", "copy", "-movflags", "+faststart", os.path.basename(out)]
    ok = subprocess.run(cmd, cwd=d).returncode == 0
    os.remove(ass)
    return ok


import random
import re

GAME_TAGS = {  # extra tags for the game being streamed (from Twitch/Kick/YouTube category)
    "grand theft auto vi": ["#gta6", "#gtavi", "#gta6gameplay", "#gta6clips", "#vicecity"],
    "grand theft auto v": ["#gta5", "#gtav", "#gtarp", "#gtaonline"],
    "just chatting": ["#irl", "#streamer", "#reaction"],
}
GENERIC_TAGS = ["#gaming", "#streamer", "#twitchclips", "#clips", "#viral", "#funny",
                "#fyp", "#gamingclips", "#livestream", "#reels"]
ALIASES = {  # channel name -> name fans search for
    "zackrawrr": "Asmongold", "kaicenat": "Kai Cenat", "ohnepixel": "ohnePixel",
    "theburntpeanut": "TheBurntPeanut", "xqc": "xQc", "jasontheween": "JasonTheWeen",
    "stableronaldo": "StableRonaldo", "dukedennis": "Duke Dennis", "ishowspeed": "IShowSpeed",
}
MAX_TAGS = {"instagram": 5, "facebook": 5, "youtube": 3, "default": 8}


def slug(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def display_name(meta):
    c = meta.get("creator") or ""
    return ALIASES.get(c.lower(), c)


def pick_tags(meta, base_tags, platform="default"):
    """Creator + game tags first, then your TAGS, then a rotating mix (identical tag sets
    on every post look spammy). Instagram allows 5 hashtags, so it gets the best 5."""
    creator = slug(display_name(meta))
    game = (meta.get("game") or "").lower()
    tags = []
    tags += GAME_TAGS.get(game, [f"#{slug(game)}"] if slug(game) else [])[:2]
    if creator:
        tags += [f"#{creator}", f"#{creator}clips"]
    tags += [t for t in (base_tags or "").split() if t.startswith("#")]
    tags += random.sample(GENERIC_TAGS, 4)
    seen, out = set(), []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:MAX_TAGS.get(platform, MAX_TAGS["default"])]


def caption_text(hook, source_url, tags, meta=None, platform="default"):
    meta = meta or {}
    who = display_name(meta)
    game = meta.get("game") or ""
    lines = [hook.capitalize() + (" 😳" if not hook.endswith("?") else " 👀")]
    if who:
        lines.append(f"🎮 {who}" + (f" playing {game}" if game and game.lower() != "just chatting" else ""))
    lines.append(f"🎥 Credit: {source_url}")
    cta = os.environ.get("CW_CTA", "Follow for daily stream clips 🔥")
    if cta:
        lines.append(cta)
    return "\n".join(lines) + "\n\n" + " ".join(pick_tags(meta, tags, platform)) + "\n"


def append_score(path, row):
    """One row per clip: adds the row, or fills new fields into the existing one."""
    rows = list(csv.DictReader(open(path, encoding="utf-8"))) if os.path.exists(path) else []
    for r in rows:
        if r.get("clip") == row.get("clip"):
            r.update({k: v for k, v in row.items() if v})
            break
    else:
        rows.append(row)
    cols = SCORE_COLS + [c for c in (rows[0].keys() if rows else []) if c not in SCORE_COLS]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in cols} for r in rows)


def process(raw, name, o):
    """o: dict with model, ready_dir, source_url, tags, hook_fallback, length,
    upload: comma list of youtube,instagram,facebook (or none), privacy, scoreboard"""
    os.makedirs(o["ready_dir"], exist_ok=True)
    log(f"transcribing {name} ...")
    result = transcribe(raw, o["model"])
    srt = os.path.join(o["ready_dir"], name + ".srt")
    n = write_short_srt(result, srt)
    hook = make_hook(result, o["hook_fallback"], o.get("meta"))
    final = os.path.join(o["ready_dir"], name + ".mp4")
    if not burn(raw, srt, hook, final, has_captions=n > 0, chunks=caption_chunks(result),
                spike_at=o.get("spike_at")):
        log(f"caption burn failed for {name}; keeping raw clip only")
        return
    meme = pick_meme((result.get("text") or ""), o.get("meta") or {})
    if meme and o.get("spike_at") is not None:
        w, h = os.environ.get("CW_RES", "1080x1920").split("x")
        tmp = final + ".meme.mp4"
        if insert_meme(final, meme, o["spike_at"] + 0.4, tmp, w, h):
            os.replace(tmp, final)
            log(f"meme cutaway: {meme}")
        else:
            log(f"meme insert failed ({meme}) - posting without it")
            if os.path.exists(tmp):
                os.remove(tmp)
    try:
        os.remove(raw)   # the finished clip replaces the raw cut - saves ~15-20 MB per clip
    except OSError:
        pass
    meta = o.get("meta") or {}
    cap = caption_text(hook, o["source_url"], o["tags"], meta)
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
            "created_ts": time.time(), "source": o["source_url"], "length_s": o["length"],
            "meta": meta}
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
    final, hook = item["final"], item["hook"]
    meta = item.get("meta") or {}
    targets = [t.strip() for t in upload.split(",") if t.strip() and t.strip() != "none"]
    urls = {}
    for t in targets:
        try:
            cap = caption_text(hook, item["source"], tags, meta, t)
            if t == "youtube":
                import uploader
                who = f" | {display_name(meta)}" if meta.get("creator") else ""
                title = (hook.capitalize()[:70] + who)[:90] + " #Shorts"
                urls[t] = uploader.upload(final, title, cap, " ".join(pick_tags(meta, tags)), privacy)
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
