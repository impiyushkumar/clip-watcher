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
"""
from dataclasses import dataclass

KINDS = ("sound", "emoji", "zoom", "text_card", "meme", "sticker")
CUTAWAY_KINDS = ("text_card", "meme")
MAX_PER_KIND = {"sound": 6, "emoji": 4, "zoom": 4, "text_card": 3, "meme": 3, "sticker": 2}
MAX_BEATS = 12
MIN_CUTAWAY_GAP_S = 1.2      # cutaways closer than this feel like a glitch
MIN_SAME_KIND_GAP_S = 0.6
DEFAULT_DURATIONS_S = {"text_card": 0.9, "meme": 1.8, "sticker": 2.0, "emoji": 1.6}
MAX_DURATIONS_S = {"text_card": 1.6, "meme": 3.0, "sticker": 3.0, "emoji": 2.5}
MAX_TEXT_CARD_CHARS = 40


@dataclass
class Beat:
    at_s: float
    kind: str
    value: str = ""
    duration_s: float = 0.0
    sound: str = ""          # optional sound category played with a text card / cutaway

    @property
    def is_cutaway(self):
        return self.kind in CUTAWAY_KINDS


def validate_beats(raw_beats, length_s, sound_menu, emoji_names, meme_names):
    """Turn Gemini's list of dicts into safe Beats: known kinds, values that exist in the
    menus, times inside the clip, sane durations, per-kind limits, no cutaway pile-ups."""
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
        beats.append(Beat(at_s=round(at_s, 2), kind=kind, value=value,
                          duration_s=round(min(duration_s, MAX_DURATIONS_S.get(kind, duration_s)), 2),
                          sound=sound if sound in sound_menu else ""))
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
    """No Gemini: the classic single-peak edit (sound + zoom + emoji on the peak)."""
    beats = [Beat(at_s=onset_s, kind="zoom"), Beat(at_s=onset_s, kind="sound", value=peak_sound)]
    if emoji:
        beats.append(Beat(at_s=onset_s, kind="emoji", value=emoji, duration_s=DEFAULT_DURATIONS_S["emoji"]))
    if reaction_sound:
        beats.append(Beat(at_s=peak_s + 0.5, kind="sound", value=reaction_sound))
    return beats
