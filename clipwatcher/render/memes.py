"""Choose a reaction meme from memes/ for a clip. File names describe the meme
(e.g. "shocked-scream.mp4"); see memes/README.md."""
import os
import random
import re

from clipwatcher import paths, settings
from clipwatcher.gemini import ask_gemini_json

MEME_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".gif")


def list_memes():
    try:
        return sorted(name for name in os.listdir(paths.MEMES_DIR) if name.lower().endswith(MEME_EXTENSIONS))
    except OSError:
        return []


def pick_meme(transcript_text, stream_info):
    """A meme file name, or None. Only MEME_CHANCE of clips get one.
    Gemini picks by file name if available, else the most transcript keywords in the name."""
    memes = list_memes()
    if not memes or random.random() > settings.MEME_CHANCE:
        return None
    if settings.GEMINI_API_KEY:
        prompt = ("Pick the reaction meme that fits this live-stream clip best, or NONE if none fits.\n"
                  f"Streamer: {stream_info.get('creator')}. Game: {stream_info.get('game')}.\n"
                  f"Transcript: \"{transcript_text[:1200]}\"\n"
                  f"Memes (file names describe them): {memes}\n"
                  'Reply as JSON: {"meme": "<exact file name or NONE>"}')
        reply = ask_gemini_json(prompt, temperature=0.4)
        if reply is not None:
            choice = reply.get("meme")
            return choice if choice in memes else None
    transcript_words = set(re.findall(r"[a-z]+", transcript_text.lower()))
    scored = [(len(transcript_words & set(re.findall(r"[a-z]+", meme.lower()))), meme) for meme in memes]
    best_score, best_meme = max(scored)
    return best_meme if best_score > 0 else random.choice(memes)
