"""The beat sheet: every meme moment in a clip, timed to what is said or shown.

Viral meme edits put something on screen every 1-2 seconds, each beat synced to a word
or an action (see docs/viral-playbook.md, "meme-dense edits"). Gemini plans the beats in
render/copywriting.py; this module defines them and makes them safe to render.

Beat kinds (at_s is seconds into the clip BEFORE any cutaway is inserted):
    sound      play a sound-kit category at at_s                 value = category
    emoji      pop an animated emoji at at_s                     value = emoji name
    zoom       zoom punch + shake + flash at at_s                value = ""
    text_card  cut away to a white card with black text          value = the text
    meme       cut away to a meme video (with its own audio)     value = meme file name
    sticker    meme video as a small picture-in-picture          value = meme file name
cutaways (text_card, meme) pause the clip; the rest are layered on top.

Every beat (except zoom) must carry EVIDENCE, so nothing is placed by guessing:
    reason   why this sound/meme/card fits this moment
    quote    the words spoken right there (checked against the word-timed transcript)
    chat     a chat message reacting to it (checked against chat near that time)
    visual   what happens on screen at that moment (Gemini watched the clip)
At least one of quote / chat / visual is required, and a quote or chat line that doesn't
actually occur near `at_s` gets the beat dropped.
"""
import re
from dataclasses import dataclass

KINDS = ("sound", "emoji", "zoom", "text_card", "meme", "sticker")
CUTAWAY_KINDS = ("text_card", "meme")
MAX_PER_KIND = {"sound": 8, "emoji": 4, "zoom": 4, "text_card": 3, "meme": 5, "sticker": 2}
MAX_BEATS = 16
MIN_CUTAWAY_GAP_S = 1.2      # cutaways closer than this feel like a glitch
MIN_SAME_KIND_GAP_S = 0.6
DEFAULT_DURATIONS_S = {"text_card": 0.9, "meme": 1.8, "sticker": 2.0, "emoji": 1.6}
MAX_DURATIONS_S = {"text_card": 1.6, "meme": 3.0, "sticker": 3.0, "emoji": 2.5}
MAX_TEXT_CARD_CHARS = 40
QUOTE_WINDOW_S = (1.5, 1.0)      # a quoted word must be spoken this long before / after the beat
CHAT_WINDOW_S = (1.0, 10.0)      # chat reacts up to ~10 s after the moment
MIN_QUOTE_MATCH = 0.5            # share of the quoted words that must be found


def words_of(text):
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def quote_is_spoken(quote, at_s, timed_words):
    """True when most words of `quote` are said within QUOTE_WINDOW_S of at_s."""
    quoted = [word for word in words_of(quote) if len(word) > 1] or words_of(quote)
    if not quoted:
        return False
    nearby = {word for word_start_s, text in timed_words
              if at_s - QUOTE_WINDOW_S[0] <= word_start_s <= at_s + QUOTE_WINDOW_S[1] for word in words_of(text)}
    return sum(word in nearby for word in quoted) / len(quoted) >= MIN_QUOTE_MATCH


def chat_is_present(chat_line, at_s, chat_messages):
    """True when a chat message near at_s shares most of its words with `chat_line`."""
    wanted = set(words_of(chat_line))
    if not wanted:
        return False
    for message_s, text in chat_messages:
        if at_s - CHAT_WINDOW_S[0] <= message_s <= at_s + CHAT_WINDOW_S[1]:
            if len(wanted & set(words_of(text))) / len(wanted) >= MIN_QUOTE_MATCH:
                return True
    return False


def has_evidence(beat, timed_words, chat_messages):
    """Zoom beats need none; others need a quote / chat line that really occurs there, or a visual."""
    if beat.kind == "zoom":
        return True
    if not beat.reason:
        return False
    if beat.quote and not quote_is_spoken(beat.quote, beat.at_s, timed_words):
        return False
    if beat.chat and not chat_is_present(beat.chat, beat.at_s, chat_messages):
        return False
    return bool(beat.quote or beat.chat or beat.visual)


@dataclass
class Beat:
    at_s: float
    kind: str
    value: str = ""
    duration_s: float = 0.0
    sound: str = ""          # optional sound category played with a text card / cutaway
    reason: str = ""         # why it fits (kept in the edit report)
    quote: str = ""          # spoken words it reacts to
    chat: str = ""           # chat message it reacts to
    visual: str = ""         # on-screen action it reacts to
    is_overlay: bool = False  # a keyed (green-screen) meme: laid over the clip, not a cutaway

    @property
    def is_cutaway(self):
        return self.kind in CUTAWAY_KINDS and not self.is_overlay


def validate_beats(raw_beats, length_s, sound_menu, emoji_names, meme_names, timed_words=(), chat_messages=(),
                   overlay_memes=()):
    """Turn Gemini's list of dicts into safe Beats: known kinds, values that exist in the
    menus, times inside the clip, real evidence (see module docstring), sane durations,
    per-kind limits, no cutaway pile-ups. timed_words: [(start_s, word)];
    chat_messages: [(seconds into the clip, text)]; overlay_memes: keyed memes (not cutaways)."""
    allowed_values = {"sound": set(sound_menu), "emoji": set(emoji_names),
                      "meme": set(meme_names), "sticker": set(meme_names)}
    beats = []
    for raw in raw_beats if isinstance(raw_beats, list) else []:
        if not isinstance(raw, dict) or raw.get("kind") not in KINDS:
            continue
        kind = raw["kind"]
        try:
            at_s = float(raw.get("at", raw.get("at_s", -1)))
            duration_s = float(raw.get("duration", 0) or DEFAULT_DURATIONS_S.get(kind, 0))
        except (TypeError, ValueError):
            continue
        if not 0.0 <= at_s <= length_s - 0.2:
            continue
        value = str(raw.get("value", "") or "").strip()
        if kind in allowed_values and value not in allowed_values[kind]:
            continue
        if kind == "text_card":
            value = value[:MAX_TEXT_CARD_CHARS]
            if not value:
                continue
        sound = str(raw.get("sound", "") or "")
        beat = Beat(at_s=round(at_s, 2), kind=kind, value=value,
                    duration_s=round(min(duration_s, MAX_DURATIONS_S.get(kind, duration_s)), 2),
                    sound=sound if sound in sound_menu else "",
                    reason=str(raw.get("reason", "") or "").strip()[:200],
                    quote=str(raw.get("quote", "") or "").strip()[:120],
                    chat=str(raw.get("chat", "") or "").strip()[:120],
                    visual=str(raw.get("visual", "") or "").strip()[:160],
                    is_overlay=kind == "meme" and value in overlay_memes)
        if has_evidence(beat, timed_words, chat_messages):
            beats.append(beat)
    return enforce_limits(sorted(beats, key=lambda beat: beat.at_s))


def enforce_limits(beats):
    kept, counts, last_at_by_kind, last_cutaway_at = [], {}, {}, None
    for beat in beats:
        if counts.get(beat.kind, 0) >= MAX_PER_KIND[beat.kind] or len(kept) >= MAX_BEATS:
            continue
        if beat.kind in last_at_by_kind and beat.at_s - last_at_by_kind[beat.kind] < MIN_SAME_KIND_GAP_S:
            continue
        if beat.is_cutaway and last_cutaway_at is not None and beat.at_s - last_cutaway_at < MIN_CUTAWAY_GAP_S:
            continue
        kept.append(beat)
        counts[beat.kind] = counts.get(beat.kind, 0) + 1
        last_at_by_kind[beat.kind] = beat.at_s
        if beat.is_cutaway:
            last_cutaway_at = beat.at_s
    return kept


def fallback_beats(onset_s, peak_s, peak_sound="", emoji="", reaction_sound=""):
    """No Gemini: the classic single-peak edit (sound + zoom + emoji on the loudest moment).
    No memes or text cards: without understanding the clip they would be guesses."""
    reason = "loudest moment of the clip (no AI: peak edit only)"
    beats = [Beat(at_s=onset_s, kind="zoom", reason=reason),
             Beat(at_s=onset_s, kind="sound", value=peak_sound, reason=reason, visual="peak")]
    if emoji:
        beats.append(Beat(at_s=onset_s, kind="emoji", value=emoji, duration_s=DEFAULT_DURATIONS_S["emoji"],
                          reason=reason, visual="peak"))
    if reaction_sound:
        beats.append(Beat(at_s=peak_s + 0.5, kind="sound", value=reaction_sound, reason=reason, visual="peak"))
    return beats
