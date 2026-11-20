"""The hook: the big text at the top of the clip.

1. Gemini writes a meme-style hook (if GEMINI_API_KEY is set), else
2. the first `hook_words` words of the transcript (learner.py tunes hook_words), else
3. the fallback text (e.g. "wait for it...") when almost nothing was said.
"""
import json
import re

from clipwatcher import paths, settings
from clipwatcher.gemini import ask_gemini_json

DEFAULT_HOOK_WORDS = 7


def ai_hook(transcript_text, stream_info):
    """3-8 word hook from Gemini, or None."""
    if not settings.GEMINI_API_KEY or not transcript_text:
        return None
    prompt = (
        "You write on-screen hooks for viral short-form clips of live streamers.\n"
        f"Streamer: {stream_info.get('creator') or 'unknown'}. "
        f"Game/category: {stream_info.get('game') or 'unknown'}.\n"
        f"What was said in the 30-second clip (auto transcript, may have errors):\n\"{transcript_text[:1500]}\"\n\n"
        "Write ONE hook of 3-8 words in meme / Gen-Z clip-page style (e.g. 'HE REALLY THOUGHT HE HAD IT', "
        "'CHAT WAS NOT READY FOR THIS'). Only use what the transcript supports - no made-up events, "
        "no slurs, no claims about real people beyond the clip. No emojis, no hashtags, no quotes. "
        'Reply as JSON: {"hook": "..."}')
    reply = ask_gemini_json(prompt) or {}
    hook = re.sub(r"[^A-Za-z0-9 '?!.,&-]", "", str(reply.get("hook", "")).strip()).upper()
    return hook if 2 <= len(hook.split()) <= 10 else None


def learned_hook_words():
    try:
        with open(paths.AUTO_SETTINGS_FILE) as auto_file:
            return int(json.load(auto_file).get("hook_words", DEFAULT_HOOK_WORDS))
    except (OSError, ValueError):
        return DEFAULT_HOOK_WORDS


def make_hook(transcript, fallback, stream_info=None):
    transcript_text = (transcript.get("text") or "").strip()
    generated = ai_hook(transcript_text, stream_info or {})
    if generated:
        return generated
    words = transcript_text.split()
    if len(words) < 3:
        return fallback.upper()
    word_limit = learned_hook_words()
    hook = " ".join(words[:word_limit]).rstrip(",.")
    return (hook + ("..." if len(words) > word_limit else "")).upper()
