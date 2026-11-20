"""Every creative decision around a clip, made by Gemini after WATCHING it: the hook box,
the title, a first comment, and the BEAT SHEET (render/beats.py): sounds, emojis, zooms,
text cards, meme cutaways and stickers, each timed to a word or an action.

Gemini gets: the clip itself as a small video WITH SOUND (it watches and listens), the
transcript with a timestamp on every word, the live chat during the clip, the streamer and
game, and the FULL menus: every sound category with its "use when", every emoji, every meme
in memes/ with its "use when". Every beat must come with evidence (the words spoken, a chat
line, or the visible action) and is checked: render/beats.validate_beats drops beats whose
quote or chat line isn't really there, and anything not in the menus.

Formats that work (vidIQ research, Nov 2026; docs/viral-playbook.md):
  * CONTEXT hook: "N3ON REALLY MESSED UP AFTER HE LEAKED GTA 6 LIVE"     (8.5M views)
  * POV hook:     "POV: YOU FINALLY DRIVE OVER AN NPC IN GTA 6"           (2000x breakout)
  * PEAK hook:    "PEAK GTA 6 NPC MOMENT"                                 (12K views/hour)
  * meme-dense edits: a beat every 1-2 s, each synced to a word or action, escalating to the
    peak: sound hits, emoji pops, white text cards ("nobody cares"), reaction-meme cutaways
Without GEMINI_API_KEY: clean templates + the single-peak edit, and NO memes or text cards
(without understanding the clip they would be guesses).
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
PROXY_WIDTH = 360        # the small copy of the clip Gemini watches

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
    summary: str = ""           # Gemini's understanding of what happens in the clip
    caption_fixes: list = None  # [(wrong, right)] transcript words Gemini heard differently
    rejected_beats: int = 0     # beats dropped for missing / false evidence


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


def valid_caption_fixes(raw_fixes, max_fixes=12):
    """[(wrong, right)] from Gemini's caption_fixes; short phrases only."""
    fixes = []
    for fix in raw_fixes if isinstance(raw_fixes, list) else []:
        if isinstance(fix, dict):
            wrong, right = str(fix.get("wrong", "")).strip(), str(fix.get("right", "")).strip()
            if wrong and right and wrong.lower() != right.lower() and len(wrong) <= 40 and len(right) <= 40:
                fixes.append((wrong, right))
    return fixes[:max_fixes]


def clip_proxy_mp4(video_path, start_s, length_s):
    """A small copy of the clip window WITH audio (360 px, low bitrate) for Gemini to watch
    and listen to. Timestamps in it are seconds into the clip. None if it can't be made."""
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{start_s:.2f}", "-t", f"{length_s:.2f}",
               "-i", video_path, "-vf", f"scale={PROXY_WIDTH}:-2,fps=15", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "32", "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-movflags", "frag_keyframe+empty_moov",
               "-f", "mp4", "-"]
    try:
        return subprocess.run(command, capture_output=True, timeout=120).stdout or None
    except subprocess.TimeoutExpired:
        return None


def timed_word_list(transcript):
    """[(start_s, word)] from Whisper's word timings."""
    return [(word["start"], word["word"]) for segment in transcript.get("segments", [])
            for word in segment.get("words", [])]


def chat_text(chat_messages):
    return "\n".join(f"  [{message_s:.1f}] {text[:100]}" for message_s, text in chat_messages[:200]) or "  (no chat)"


def build_prompt(timed_words, stream_info, sound_menu, emoji_names, meme_menu, length_s, peak_s, chat_messages=()):
    creator = creator_display_name(stream_info) or "the streamer"
    game = short_game_name(stream_info)
    sounds = "\n".join(f"  {category}: {use_when}" for category, use_when in sorted(sound_menu.items()))
    memes = "\n".join(f"  {name}: {use_when}" for name, use_when in sorted(meme_menu.items())) or "  (none)"
    return (
        "You are the editor of a viral meme clip page that posts GTA 6 live-stream moments to YouTube Shorts "
        "and TikTok. Edit like the best meme pages: a meme beat every 1-2 seconds, each one placed BECAUSE of "
        "something specific that is said or happens, escalating to the funniest moment.\n"
        f"Streamer: {creator}. Game: {game}. Clip length: {length_s:.1f} s. The loudest moment is at {peak_s:.1f} s.\n"
        "The attached video IS the clip (with sound): watch it and LISTEN to it - the streamer's words, tone, "
        "laughs, screams and the game sounds. Times are seconds from its start.\n"
        f"Transcript, [seconds] before each word (auto, may have errors): {timed_words[:2500]}\n"
        "Live chat during the clip, [seconds] (chat reacts 2-8 s AFTER the moment it is about):\n"
        f"{chat_text(chat_messages)}\n\n"
        "First understand the clip: what happens, what is said, why it is funny or shocking, and what chat "
        "reacted to. Then write:\n"
        "1. summary: 1-2 sentences of what actually happens in the clip.\n"
        "2. hook: the on-screen box, 4-12 words, ALL CAPS, no emojis/hashtags/quotes. CONTEXT "
        "(\"N3ON REALLY MESSED UP AFTER HE LEAKED GTA 6 LIVE\"), POV (\"POV: YOUR FIRST 10 SECONDS PLAYING GTA 6\") "
        f"or PEAK (\"PEAK GTA 6 NPC MOMENT\"). Mention {creator} or {game} when natural.\n"
        "3. emphasis: the single most important word of the hook (drawn in red).\n"
        f"4. title: max 70 chars, Gen-Z clip-page tone, names {creator} and {game}, 1-2 emojis at the end "
        f"(😭 💀 😳 🔥 ✌️), e.g. \"{creator} got PRESSED by a random NPC in {game} 😭\".\n"
        "5. comment: a short first comment that makes viewers reply (question or hot take), 1 emoji.\n"
        "6. caption_fixes: words the auto transcript got WRONG that you can clearly hear in the audio, as "
        "[{\"wrong\": \"know charge\", \"right\": \"no charge\"}] (empty list if it's fine).\n"
        "7. beats: edit beats across the clip. Each beat: {\"at\": seconds, \"kind\": ..., \"value\": ..., "
        "\"duration\": seconds (text cards/emoji only; memes always play in full), \"sound\": optional category for a text_card, "
        "\"reason\": why THIS meme/sound fits THIS moment, and the EVIDENCE: \"quote\": the exact words "
        "spoken at that time (copy them from the transcript), and/or \"chat\": a chat message reacting to it "
        "(copy it), and/or \"visual\": what you see happen at that time}. Beats whose quote or chat line "
        "is not really there at that time are thrown away. Kinds:\n"
        "   sound: a sound effect, value = category from the sound menu, landing EXACTLY on the word/action\n"
        f"   emoji: an animated emoji pops up (~1.5 s), value = one of {list(emoji_names)}\n"
        "   zoom: zoom punch + shake + flash on a hit, a reveal or a reaction (value \"\")\n"
        "   text_card: cut to a white card with short black text for ~0.9 s, value = 1-4 words of meme "
        "commentary in lowercase about what was just said/done, e.g. \"nobody cares\", \"he's cooked\", "
        "\"who asked?\" (right after the line it reacts to)\n"
        "   meme: cut to a reaction meme (1-2.5 s, with its own sound), value = file from the meme menu\n"
        "   sticker: small picture-in-picture meme over the clip (~2 s), value = file from the meme menu\n"
        "Rules: a meme/sound must MATCH the meaning of the moment (its 'use when' fits what is said or "
        "happens) - if nothing in the menu truly fits, skip it; never place one just to fill time. Always a "
        "sound + zoom on the peak. No two cutaways within 1.2 s; no cutaways before 1.0 s. The first 2 seconds decide "
        "whether people swipe away: put a strong, justified beat in them. Keep the pace: no stretch longer than ~3 s "
        "without a beat, as long as the clip gives you a reason. One sound per joke. MEMES: YOU decide how many this clip needs - one perfect meme or ten, whatever makes THIS clip funniest (0 is fine too); every one must truly fit its moment; each meme plays its WHOLE reaction (its full length), so place it where the clip can pause for it, never in the middle of an important line. Many people watch MUTED, so "
        "text cards and emojis must make the joke readable without sound.\n"
        "Sound menu (category: use when):\n" + sounds + "\n"
        "Meme menu (file: use when):\n" + memes + "\n"
        "Only describe what the video, transcript and chat support: no made-up events, no slurs, no claims "
        "about real people beyond the clip.\n"
        'Reply as JSON: {"summary": "...", "hook": "...", "emphasis": "...", "title": "...", "comment": "...", '
        '"caption_fixes": [{"wrong": "...", "right": "..."}], '
        '"beats": [{"at": 2.4, "kind": "sound", "value": "impact/punch", "reason": "...", "quote": "...", '
        '"chat": "", "visual": "..."}, ...]}')


def write_copy(transcript, stream_info, video_path=None, start_s=0.0, length_s=None, peak_s=None,
               sound_menu=None, emoji_names=(), meme_menu=None, chat_messages=()):
    """ClipCopy with an evidence-checked beat sheet from Gemini, which watches AND listens to
    the clip window of video_path (plus transcript and chat), or the template fallback
    (beats=None: peak edit only, no memes). chat_messages: [(seconds into the clip, text)]."""
    from clipwatcher.render.beats import MIN_CUTAWAY_GAP_S, validate_beats
    sound_menu, meme_menu = sound_menu or {}, meme_menu or {}
    length_s = length_s or settings.CLIP_LENGTH_S
    transcript_text = (transcript.get("text") or "").strip()
    fallback = fallback_copy(stream_info, transcript_text, emoji_names)
    if not settings.GEMINI_API_KEY:
        return fallback
    proxy = clip_proxy_mp4(video_path, start_s, length_s) if video_path else None
    frames = None if proxy else (frame_grid_jpeg(video_path, start_s, length_s) if video_path else None)
    prompt = build_prompt(timed_transcript(transcript), stream_info, sound_menu, emoji_names, meme_menu,
                          length_s, peak_s if peak_s is not None else length_s * 0.7, chat_messages)
    reply = ask_gemini_json(prompt, temperature=0.6, image_jpeg=frames,
                            media=[("video/mp4", proxy)] if proxy else ()) or {}
    hook = on_screen_text(str(reply.get("hook", "")))
    if not 2 <= len(hook.split()) <= 14:
        return fallback
    emphasis = on_screen_text(str(reply.get("emphasis", "")))
    from clipwatcher.render.memes import meme_key_color
    beats = validate_beats(reply.get("beats"), length_s, sound_menu, emoji_names, meme_menu,
                           timed_words=timed_word_list(transcript), chat_messages=chat_messages,
                           overlay_memes={name for name in meme_menu if meme_key_color(name)})
    beats = [beat for beat in beats if not (beat.is_cutaway and beat.at_s < MIN_CUTAWAY_GAP_S - 0.2)]
    return ClipCopy(
        hook=hook,
        emphasis=emphasis if emphasis in hook.replace(":", " ").split() else "",
        title=str(reply.get("title", "")).strip().strip('"')[:90] or fallback.title,
        comment=str(reply.get("comment", "")).strip()[:300] or fallback.comment,
        beats=beats or None, emoji=fallback.emoji,
        summary=str(reply.get("summary", "")).strip()[:400],
        caption_fixes=valid_caption_fixes(reply.get("caption_fixes")),
        rejected_beats=max(0, len(reply.get("beats") or []) - len(beats)))


def describe(copy):
    """One log line."""
    summary = {key: value for key, value in copy.__dict__.items() if value and key not in ("beats", "emoji")}
    if copy.beats:
        summary["beats"] = [f"{beat.at_s:.1f}s {beat.kind} {beat.value}".strip() for beat in copy.beats]
    return json.dumps(summary, ensure_ascii=False)
