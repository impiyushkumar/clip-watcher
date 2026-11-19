"""Caption text and hashtags for a post. Edit the tables below to add games or creators."""
import random
import re

from clipwatcher import settings

GAME_HASHTAGS = {  # stream category (lowercase) -> extra tags
    "grand theft auto vi": ["#gta6", "#gtavi", "#gta6gameplay", "#gta6clips", "#vicecity"],
    "grand theft auto v": ["#gta5", "#gtav", "#gtarp", "#gtaonline"],
    "just chatting": ["#irl", "#streamer", "#reaction"],
}
GENERIC_HASHTAGS = ["#gaming", "#streamer", "#twitchclips", "#clips", "#viral", "#funny",
                    "#fyp", "#gamingclips", "#livestream", "#reels"]
CREATOR_ALIASES = {  # channel name -> the name fans search for
    "zackrawrr": "Asmongold", "kaicenat": "Kai Cenat", "ohnepixel": "ohnePixel",
    "theburntpeanut": "TheBurntPeanut", "xqc": "xQc", "jasontheween": "JasonTheWeen",
    "stableronaldo": "StableRonaldo", "dukedennis": "Duke Dennis", "ishowspeed": "IShowSpeed",
}
MAX_HASHTAGS = {"instagram": 5, "facebook": 5, "youtube": 3, "default": 8}
RANDOM_GENERIC_COUNT = 4  # identical tag sets on every post look spammy


def slugify(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def creator_display_name(stream_info):
    creator = stream_info.get("creator") or ""
    return CREATOR_ALIASES.get(creator.lower(), creator)


def pick_hashtags(stream_info, base_hashtags, platform="default"):
    """Game tags, creator tags, your TAGS, then a random generic mix; deduplicated and
    cut to the platform's limit."""
    creator_slug = slugify(creator_display_name(stream_info))
    game = (stream_info.get("game") or "").lower()
    hashtags = list(GAME_HASHTAGS.get(game, [f"#{slugify(game)}"] if slugify(game) else []))[:2]
    if creator_slug:
        hashtags += [f"#{creator_slug}", f"#{creator_slug}clips"]
    hashtags += [tag for tag in (base_hashtags or "").split() if tag.startswith("#")]
    hashtags += random.sample(GENERIC_HASHTAGS, RANDOM_GENERIC_COUNT)
    seen, unique = set(), []
    for tag in hashtags:
        if tag.lower() not in seen:
            seen.add(tag.lower())
            unique.append(tag)
    return unique[:MAX_HASHTAGS.get(platform, MAX_HASHTAGS["default"])]


def build_caption(hook, source_url, base_hashtags, stream_info=None, platform="default"):
    """Hook line, creator/game line, credit, call to action, hashtags."""
    stream_info = stream_info or {}
    creator = creator_display_name(stream_info)
    game = stream_info.get("game") or ""
    lines = [hook.capitalize() + (" 😳" if not hook.endswith("?") else " 👀")]
    if creator:
        playing = f" playing {game}" if game and game.lower() != "just chatting" else ""
        lines.append(f"🎮 {creator}{playing}")
    lines.append(f"🎥 Credit: {source_url}")
    if settings.CALL_TO_ACTION:
        lines.append(settings.CALL_TO_ACTION)
    return "\n".join(lines) + "\n\n" + " ".join(pick_hashtags(stream_info, base_hashtags, platform)) + "\n"


def youtube_title(hook, stream_info):
    creator = f" | {creator_display_name(stream_info)}" if stream_info.get("creator") else ""
    return (hook.capitalize()[:70] + creator)[:90] + " #Shorts"
