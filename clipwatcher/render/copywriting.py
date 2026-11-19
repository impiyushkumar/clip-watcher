"""Every creative decision around a clip, made by Gemini after WATCHING it: the hook box,
the title, a first comment, and the BEAT SHEET (render/beats.py): sounds, emojis, zooms,
text cards, meme cutaways and stickers, each timed to a word or an action.

Gemini gets: a grid of frames every ~1.5 s (each labelled with its time), the transcript
with a timestamp on every word, the streamer and game, and the FULL menus: every sound
category with its "use when", every emoji, every meme in memes/ with its "use when".
Everything it names is validated against the menus (render/beats.validate_beats).

Formats that work (vidIQ research, Nov 2026; docs/viral-playbook.md):
  * CONTEXT hook: "N3ON REALLY MESSED UP AFTER HE LEAKED GTA 6 LIVE"     (8.5M views)
  * POV hook:     "POV: YOU FINALLY DRIVE OVER AN NPC IN GTA 6"           (2000x breakout)
  * PEAK hook:    "PEAK GTA 6 NPC MOMENT"                                 (12K views/hour)
  * meme-dense edits: a beat every 1-2 s, each synced to a word or action, escalating to the
    peak: sound hits, emoji pops, white text cards ("nobody cares"), reaction-meme cutaways
Without GEMINI_API_KEY: clean templates + the classic single-peak edit (never raw transcript
fragments, which read as gibberish: "1 AND TIME 4 AND AM AGO...").
"""
import json
import math
import os
import random
import re
import subprocess
from dataclasses import dataclass

from clipwatcher import settings
from clipwatcher.gemini import ask_gemini_json
from clipwatcher.publish.post_text import creator_display_name

GAME_SHORT_NAMES = {"grand theft auto vi": "GTA 6", "grand theft auto v": "GTA 5"}
ON_SCREEN_ALLOWED = re.compile(r"[^A-Za-z0-9 '?!.,&%$#:\-]")  # the font has no emoji glyphs
CONTACT_SHEET_FRAME_WIDTH = 360
GRID_FRAME_WIDTH = 240

FALLBACK_HOOKS = [
    "{creator} WAS NOT READY FOR THIS IN {game}",
    "PEAK {game} MOMENT",
    "THIS {game} MOMENT BROKE {creator}",
    "{creator} CAN'T BELIEVE WHAT HAPPENED IN {game}",
    "NOBODY EXPECTED THIS IN {game}",
]
FALLBACK_TITLES = [
    "{creator} was NOT ready for this in {game} 😭",
    "Peak {game} moment with {creator} 💀",
    "This {game} moment broke {creator} 😭",
    "{creator} can't believe what happened in {game} 💀",
    "Nobody expected this from {creator} in {game} 😳",
]
FALLBACK_COMMENTS = ["Would you have done the same? 😭", "Rate this moment 1-10 💀",
                     "Who else is playing GTA 6 rn? 🔥"]


@dataclass
class ClipCopy:
    hook: str                   # on-screen context box, UPPERCASE, no emoji
    emphasis: str = ""          # one word of the hook drawn in red
    title: str = ""             # post title with emojis (no #Shorts; post_text adds that)
    comment: str = ""           # first comment (a question that makes people reply)
    beats: list = None          # [Beat] planned by Gemini; None = use the single-peak fallback
    emoji: str = ""             # fallback only: emoji for the peak


def short_game_name(stream_info):
    game = (stream_info.get("game") or "").strip()
    if not game or game.lower() == "just chatting":
        return "GTA 6"  # this channel is GTA 6 focused
    return GAME_SHORT_NAMES.get(game.lower(), game)


def on_screen_text(text):
    """Uppercase, emoji-free, single-spaced (safe for the burned-in font)."""
    return re.sub(r"\s+", " ", ON_SCREEN_ALLOWED.sub("", text or "")).strip().upper()


def contact_sheet_jpeg(video_path, times_s):
    """One JPEG with the frames at `times_s` side by side, so Gemini can see the moment."""
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    for time_s in times_s:
        command += ["-ss", f"{max(0.0, time_s):.2f}", "-i", video_path]
    scaled = "".join(f"[{index}:v]scale={CONTACT_SHEET_FRAME_WIDTH}:-2,setsar=1[f{index}];"
                     for index in range(len(times_s)))
    stacked = "".join(f"[f{index}]" for index in range(len(times_s)))
    command += ["-filter_complex", f"{scaled}{stacked}hstack=inputs={len(times_s)}",
                "-frames:v", "1", "-f", "image2", "-vcodec", "mjpeg", "-q:v", "4", "-"]
    try:
        return subprocess.run(command, capture_output=True, timeout=60).stdout or None
    except subprocess.TimeoutExpired:
        return None


def frame_grid_jpeg(video_path, start_s, length_s, every_s=1.5, columns=5):
    """One JPEG grid: a frame every `every_s` seconds of [start_s, start_s + length_s],
    each labelled with its time in the final clip, so Gemini can time beats to actions."""
    from clipwatcher import paths
    frame_count = max(1, math.ceil(length_s / every_s - 0.01))
    rows = (frame_count + columns - 1) // columns
    font_file = os.path.join(paths.FONTS_DIR, "DejaVuSans-Bold.ttf")
    label = (f"drawtext=fontfile='{font_file}':text='%{{eif\\:t\\:d}}.%{{eif\\:mod(t*10\\,10)\\:d}}s':x=6:y=6:fontsize=26:"
             "fontcolor=yellow:box=1:boxcolor=black@0.6")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{start_s:.2f}", "-t", f"{length_s:.2f}",
               "-i", video_path, "-vf", f"fps=1/{every_s},scale={GRID_FRAME_WIDTH}:-2,"
               f"{label},tile={columns}x{rows}", "-frames:v", "1", "-f", "image2", "-vcodec", "mjpeg",
               "-q:v", "5", "-"]
    try:
        return subprocess.run(command, capture_output=True, timeout=90).stdout or None
    except subprocess.TimeoutExpired:
        return None


def timed_transcript(transcript, max_words=120):
    """"[0.4] no [0.6] way ..." so Gemini can sync beats to exact words."""
    words = [word for segment in transcript.get("segments", []) for word in segment.get("words", [])]
    return " ".join(f"[{word['start']:.1f}]{word['word']}" for word in words[:max_words]) or "(nobody talks)"


def fallback_copy(stream_info, transcript_text="", emoji_names=()):
    from clipwatcher.render.emojis import emoji_by_keywords
    creator = creator_display_name(stream_info) or "HE"
    game = short_game_name(stream_info)
    template_index = random.randrange(len(FALLBACK_HOOKS))
    hook = on_screen_text(FALLBACK_HOOKS[template_index].format(creator=creator, game=game))
    title = FALLBACK_TITLES[template_index].format(creator=creator, game=game)
    creator_word = on_screen_text(creator).split(" ")[0]
    emphasis = creator_word if creator_word in hook.split() else hook.split()[0]
    emoji = emoji_by_keywords(transcript_text) if emoji_names else ""
    return ClipCopy(hook=hook, emphasis=emphasis, title=title, emoji=emoji or "",
                    comment=random.choice(FALLBACK_COMMENTS))


def build_prompt(timed_words, stream_info, sound_menu, emoji_names, meme_menu, length_s, peak_s):
    creator = creator_display_name(stream_info) or "the streamer"
    game = short_game_name(stream_info)
    sounds = "\n".join(f"  {category}: {use_when}" for category, use_when in sorted(sound_menu.items()))
    memes = "\n".join(f"  {name}: {use_when}" for name, use_when in sorted(meme_menu.items())) or "  (none)"
    return (
        "You are the editor of a viral meme clip page that posts GTA 6 live-stream moments to YouTube Shorts "
        "and TikTok. Edit like the best meme pages: something happens every 1-2 seconds, every beat perfectly "
        "synced to a word or an action, escalating to the funniest moment.\n"
        f"Streamer: {creator}. Game: {game}. Clip length: {length_s:.1f} s. The loudest moment is at {peak_s:.1f} s.\n"
        "The image is a grid of frames, one every 1.5 s, each labelled with its time in seconds.\n"
        f"Transcript, [seconds] before each word (auto, may have errors): {timed_words[:2500]}\n\n"
        "Watch the frames, read the transcript, work out what happens and why it's funny or shocking, then write:\n"
        "1. hook: the on-screen box, 4-12 words, ALL CAPS, no emojis/hashtags/quotes. CONTEXT "
        "(\"N3ON REALLY MESSED UP AFTER HE LEAKED GTA 6 LIVE\"), POV (\"POV: YOUR FIRST 10 SECONDS PLAYING GTA 6\") "
        f"or PEAK (\"PEAK GTA 6 NPC MOMENT\"). Mention {creator} or {game} when natural.\n"
        "2. emphasis: the single most important word of the hook (drawn in red).\n"
        f"3. title: max 70 chars, Gen-Z clip-page tone, names {creator} and {game}, 1-2 emojis at the end "
        f"(😭 💀 😳 🔥 ✌️), e.g. \"{creator} got PRESSED by a random NPC in {game} 😭\".\n"
        "4. comment: a short first comment that makes viewers reply (question or hot take), 1 emoji.\n"
        "5. beats: 4-10 edit beats across the WHOLE clip, each {\"at\": seconds, \"kind\": ..., \"value\": ..., "
        "\"duration\": seconds (cutaways/emoji/sticker only), \"sound\": optional category for a text_card}. Kinds:\n"
        "   sound: a sound effect, value = category from the sound menu, landing EXACTLY on the word/action\n"
        f"   emoji: an animated emoji pops up (~1.5 s), value = one of {list(emoji_names)}\n"
        "   zoom: zoom punch + shake + flash on a hit, a reveal or a reaction (value \"\")\n"
        "   text_card: cut to a white card with short black text for ~0.9 s, value = 1-4 words of meme "
        "commentary in lowercase, e.g. \"nobody cares\", \"emotionally damaged\", \"he's cooked\", \"i need help.\", "
        "\"who asked?\" (put it right after the line it reacts to)\n"
        "   meme: cut to a reaction meme (1-2.5 s, with its sound), value = file from the meme menu; only if it "
        "clearly matches the moment\n"
        "   sticker: small picture-in-picture meme over the clip (~2 s), value = file from the meme menu\n"
        "Rules: always a sound + zoom on the peak; sync every beat to a word or action you can see/read; "
        "no two cutaways within 1.2 s; cutaways never before 1.0 s (the first second must show the action); "
        "fewer, well-timed beats beat random ones.\n"
        "Sound menu (category: use when):\n" + sounds + "\n"
        "Meme menu (file: use when):\n" + memes + "\n"
        "Only describe what the frames and transcript support: no made-up events, no slurs, no claims about real "
        "people beyond the clip.\n"
        'Reply as JSON: {"hook": "...", "emphasis": "...", "title": "...", "comment": "...", '
        '"beats": [{"at": 2.4, "kind": "sound", "value": "impact/punch"}, ...]}')


def write_copy(transcript, stream_info, video_path=None, start_s=0.0, length_s=None, peak_s=None,
               sound_menu=None, emoji_names=(), meme_menu=None):
    """ClipCopy with a beat sheet from Gemini (watching the clip window of video_path),
    or the template fallback (beats=None)."""
    from clipwatcher.render.beats import MIN_CUTAWAY_GAP_S, validate_beats
    sound_menu, meme_menu = sound_menu or {}, meme_menu or {}
    length_s = length_s or settings.CLIP_LENGTH_S
    transcript_text = (transcript.get("text") or "").strip()
    fallback = fallback_copy(stream_info, transcript_text, emoji_names)
    if not settings.GEMINI_API_KEY:
        return fallback
    frames = frame_grid_jpeg(video_path, start_s, length_s) if video_path else None
    prompt = build_prompt(timed_transcript(transcript), stream_info, sound_menu, emoji_names, meme_menu,
                          length_s, peak_s if peak_s is not None else length_s * 0.7)
    reply = ask_gemini_json(prompt, temperature=0.8, image_jpeg=frames) or {}
    hook = on_screen_text(str(reply.get("hook", "")))
    if not 2 <= len(hook.split()) <= 14:
        return fallback
    emphasis = on_screen_text(str(reply.get("emphasis", "")))
    beats = validate_beats(reply.get("beats"), length_s, sound_menu, emoji_names, meme_menu)
    beats = [beat for beat in beats if not (beat.is_cutaway and beat.at_s < MIN_CUTAWAY_GAP_S - 0.2)]
    return ClipCopy(
        hook=hook,
        emphasis=emphasis if emphasis in hook.replace(":", " ").split() else "",
        title=str(reply.get("title", "")).strip().strip('"')[:90] or fallback.title,
        comment=str(reply.get("comment", "")).strip()[:300] or fallback.comment,
        beats=beats or None, emoji=fallback.emoji)


def describe(copy):
    """One log line."""
    summary = {key: value for key, value in copy.__dict__.items() if value and key != "beats"}
    if copy.beats:
        summary["beats"] = [f"{beat.at_s:.1f}s {beat.kind} {beat.value}".strip() for beat in copy.beats]
    return json.dumps(summary, ensure_ascii=False)
