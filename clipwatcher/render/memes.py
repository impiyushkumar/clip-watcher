"""Choose a reaction meme from memes/ for a clip. File names describe the meme
(e.g. "shocked-scream.mp4"); see memes/README.md. Gemini's choice comes from
render/copywriting.py; this module applies MEME_CHANCE and the keyword fallback."""
import os
import random
import re

from clipwatcher import paths, settings

MEME_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".gif")


def list_memes():
    try:
        return sorted(name for name in os.listdir(paths.MEMES_DIR) if name.lower().endswith(MEME_EXTENSIONS))
    except OSError:
        return []


def pick_meme(chosen_name, transcript_text):
    """A meme file name, or None. Only MEME_CHANCE of clips get one. With Gemini, its choice
    is final (it may say none fits); without, the meme whose name shares the most words
    with the transcript wins (only if any word matches)."""
    memes = list_memes()
    if not memes or random.random() > settings.MEME_CHANCE:
        return None
    if settings.GEMINI_API_KEY:
        return chosen_name if chosen_name in memes else None
    transcript_words = set(re.findall(r"[a-z]+", transcript_text.lower()))
    scored = [(len(transcript_words & set(re.findall(r"[a-z]+", meme.lower()))), meme) for meme in memes]
    best_score, best_meme = max(scored)
    return best_meme if best_score > 0 else None
