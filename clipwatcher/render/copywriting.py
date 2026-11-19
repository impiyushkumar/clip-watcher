"""Every creative decision around a clip, made by Gemini after WATCHING it:
the hook box, the title, the sound on the peak, a reaction sound after it, the emoji
that pops up, the meme cutaway and a comment question. One call per clip.

Gemini gets: a contact sheet (frames before / on / after the peak), the transcript, the
streamer and game, and the FULL menus: every sound category in the kit with its
"use when" description, every emoji, every meme in memes/. It must pick what fits the
actual moment; names are validated against the menus.

Formats that work on viral GTA 6 streamer clips (researched with vidIQ, Nov 2026; see
docs/viral-playbook.md):
  * CONTEXT hook: "N3ON REALLY MESSED UP AFTER HE LEAKED GTA 6 LIVE"     (8.5M views)
  * POV hook:     "POV: YOU FINALLY DRIVE OVER AN NPC IN GTA 6"           (2000x breakout)
  * PEAK hook:    "PEAK GTA 6 NPC MOMENT"                                 (12K views/hour)
  * title: streamer + what happened + game + 1-2 emojis: "Clix got PRESSED by an NPC in GTA 6 😭"
Without GEMINI_API_KEY it falls back to clean templates and keyword picks. It never uses raw
transcript fragments, which read as gibberish ("1 AND TIME 4 AND AM AGO...").
"""
import json
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
    peak_sound: str = ""        # sound menu category for the peak, "" = keyword pick / boom
    reaction_sound: str = ""    # sound menu category right after the peak, "" = none
    emoji: str = ""             # emoji name to pop up on the peak, "" = none
    meme: str = ""              # file name from memes/, "" = none
    comment: str = ""           # first comment (a question that makes people reply)


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


def build_prompt(transcript_text, stream_info, sound_menu, emoji_names, meme_names, length_s):
    creator = creator_display_name(stream_info) or "the streamer"
    game = short_game_name(stream_info)
    sounds = "\n".join(f"  {category}: {use_when}" for category, use_when in sorted(sound_menu.items()))
    return (
        "You are the editor of a viral YouTube Shorts / TikTok clip page for live streamers playing GTA 6.\n"
        f"Streamer: {creator}. Game: {game}. Clip length: {length_s:.0f} s.\n"
        "The image shows 3 frames of the clip: ~2 s before the peak moment, ON the peak, ~1.5 s after.\n"
        f"Auto transcript (may have errors):\n\"{transcript_text[:1500]}\"\n\n"
        "Watch the frames and read the transcript, figure out what actually happens and why it's funny "
        "or shocking, then decide everything below so it fits THIS moment.\n\n"
        "1. hook: the on-screen box, 4-12 words, ALL CAPS, no emojis/hashtags/quotes. Use the format that "
        "fits best: CONTEXT (\"N3ON REALLY MESSED UP AFTER HE LEAKED GTA 6 LIVE\"), POV "
        "(\"POV: YOUR FIRST 10 SECONDS PLAYING GTA 6\"), or PEAK (\"PEAK GTA 6 NPC MOMENT\"). "
        f"Mention {creator} or {game} when it reads naturally.\n"
        "2. emphasis: the single most important word of the hook (drawn in red).\n"
        f"3. title: max 70 characters, Gen-Z clip-page tone, names {creator} and {game}, 1-2 emojis at the end "
        f"(😭 💀 😳 🔥 ✌️), e.g. \"{creator} got PRESSED by a random NPC in {game} 😭\".\n"
        "4. peak_sound: the sound that lands EXACTLY on the peak. Pick the category whose 'use when' "
        "matches what happens on screen. Menu:\n" + sounds + "\n"
        "5. reaction_sound: an optional second sound right after the peak that comments on it (e.g. "
        "fail/mission-failed after a death, win/flawless-victory after a clean win, comedy/record-scratch "
        "for an awkward freeze), or NONE. Use NONE when it would be too much.\n"
        f"6. emoji: the animated emoji that pops up on the peak, exact name from {list(emoji_names)}, or NONE.\n"
        f"7. meme: a reaction meme video to cut to after the moment, exact file name from {list(meme_names)}, "
        "or NONE if none clearly fits (NONE is often best).\n"
        "8. comment: a short first comment that makes viewers reply (a question or a hot take), with 1 emoji.\n"
        "Only describe what the frames and transcript support: no made-up events, no slurs, no claims about "
        "real people beyond the clip.\n"
        'Reply as JSON: {"hook": "...", "emphasis": "...", "title": "...", "peak_sound": "...", '
        '"reaction_sound": "...", "emoji": "...", "meme": "...", "comment": "..."}')


def write_copy(transcript_text, stream_info, video_path=None, peak_s=None, length_s=None,
               sound_menu=None, emoji_names=(), meme_names=()):
    """ClipCopy from Gemini (watching frames around peak_s of video_path), or the fallback."""
    sound_menu = sound_menu or {}
    fallback = fallback_copy(stream_info, transcript_text, emoji_names)
    if not settings.GEMINI_API_KEY:
        return fallback
    frames = (contact_sheet_jpeg(video_path, [peak_s - 2.0, peak_s, peak_s + 1.5])
              if video_path and peak_s is not None else None)
    prompt = build_prompt(transcript_text, stream_info, sound_menu, emoji_names, meme_names,
                          length_s or settings.CLIP_LENGTH_S)
    reply = ask_gemini_json(prompt, temperature=0.8, image_jpeg=frames) or {}
    hook = on_screen_text(str(reply.get("hook", "")))
    if not 2 <= len(hook.split()) <= 14:
        return fallback
    emphasis = on_screen_text(str(reply.get("emphasis", "")))

    def valid(value, allowed):
        return value if isinstance(value, str) and value in allowed else ""

    return ClipCopy(
        hook=hook,
        emphasis=emphasis if emphasis in hook.replace(":", " ").split() else "",
        title=str(reply.get("title", "")).strip().strip('"')[:90] or fallback.title,
        peak_sound=valid(reply.get("peak_sound"), sound_menu),
        reaction_sound=valid(reply.get("reaction_sound"), sound_menu),
        emoji=valid(reply.get("emoji"), set(emoji_names)),
        meme=valid(reply.get("meme"), set(meme_names)),
        comment=str(reply.get("comment", "")).strip()[:300] or fallback.comment)


def describe(copy):
    """One log line."""
    return json.dumps({key: value for key, value in copy.__dict__.items() if value}, ensure_ascii=False)
