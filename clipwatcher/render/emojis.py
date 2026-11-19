"""Animated reaction emojis (assets/emoji/<name>.webm, built by media_kit.py) that pop up
on the peak, like the 😭 💀 😳 stickers on viral clips. Gemini picks one by name in
render/copywriting.py; without Gemini, MOOD_KEYWORDS picks one from the transcript."""
import os

from clipwatcher import paths

DEFAULT_EMOJI = "skull"
MOOD_KEYWORDS = {  # transcript word -> emoji (no-Gemini fallback)
    "lol": "tears-of-joy", "haha": "tears-of-joy", "funny": "rolling-on-floor-laughing",
    "dead": "skull", "died": "skull", "bro": "skull", "what": "flushed", "why": "flushed",
    "no": "loudly-crying", "nah": "loudly-crying", "help": "loudly-crying", "crying": "loudly-crying",
    "wow": "mind-blown", "insane": "mind-blown", "crazy": "mind-blown", "fire": "fire",
    "money": "money-wings", "cops": "rotating-light", "police": "rotating-light",
    "love": "heart-eyes", "beautiful": "heart-eyes", "scared": "screaming-in-fear",
    "angry": "angry", "mad": "angry", "clown": "clown", "car": "car", "boom": "collision",
}


def list_emojis():
    try:
        return sorted(os.path.splitext(name)[0] for name in os.listdir(paths.EMOJI_DIR) if name.endswith(".webm"))
    except OSError:
        return []


def emoji_path(name):
    path = os.path.join(paths.EMOJI_DIR, f"{name}.webm")
    return path if name and os.path.exists(path) else None


def emoji_by_keywords(transcript_text):
    available = set(list_emojis())
    for word in transcript_text.lower().replace("?", " ").replace("!", " ").split():
        if MOOD_KEYWORDS.get(word) in available:
            return MOOD_KEYWORDS[word]
    return DEFAULT_EMOJI if DEFAULT_EMOJI in available else None
