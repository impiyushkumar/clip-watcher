"""Build the bundled media kit: meme-style sound effects and animated emojis that are
LEGAL to use in monetized Shorts. Output is committed to the repo:

    assets/sound_kit/<group>/<category>/<name>.mp3
            group = WHEN to use it: impact (on the peak hit), fail, win, hype, danger,
            comedy, transition, money. Category = what it is, e.g. fail/mission-failed.
    assets/sound_kit/catalog.json   every category with its "use when" description + files
    assets/sound_kit/README.md      the same, for humans
    assets/emoji/<name>.webm        animated reaction emojis (200 px, VP9 with transparency)
    assets/CREDITS.md                        sources and licenses

Sources (nothing ripped from YouTube or meme soundboards: those are copyrighted and get
Shorts muted / claimed):
  * Kenney.nl audio packs - CC0 (public domain): impacts, glass, UI dings, lasers, coins,
    jingles and voice lines like "mission failed", "game over", "flawless victory".
  * Synthesized here with ffmpeg - our own: vine-style booms, airhorn, fail trombone,
    record scratch, riser, bonk, boing, ding, buzzer, siren, heartbeat, whoosh.
  * Google Noto animated emoji - CC BY 4.0 (credit in CREDITS.md).

    python3 -m clipwatcher build-kit            # everything
    python3 -m clipwatcher build-kit sounds     # only sounds (or: emoji)
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile

from clipwatcher import paths
from clipwatcher.log import log

BROWSER_USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0 Safari/537.36")
KENNEY_PACKS = ["impact-sounds", "interface-sounds", "digital-audio", "casino-audio", "sci-fi-sounds",
                "rpg-audio", "music-jingles", "voiceover-pack", "voiceover-pack-fighter"]
# (pack, file-name regex, category). First match wins; files matching nothing are skipped
# (footsteps, UI clicks, card shuffles: useless for meme edits).
KENNEY_RULES = [
    ("impact-sounds", r"^impactPunch", "punch"),
    ("impact-sounds", r"^impactGlass", "glass-break"),
    ("impact-sounds", r"^impactBell", "bell"),
    ("impact-sounds", r"^impact(Metal|Plate|Tin)", "metal-hit"),
    ("impact-sounds", r"^impact(Wood|Plank)", "wood-hit"),
    ("impact-sounds", r"^impact(Soft|Generic|Mining)", "thud"),
    ("interface-sounds", r"^error", "error"),
    ("interface-sounds", r"^(confirmation|bong|pluck|question|glass)", "ding"),
    ("interface-sounds", r"^glitch", "glitch"),
    ("interface-sounds", r"^scratch", "scratch"),
    ("interface-sounds", r"^drop", "pop"),
    ("digital-audio", r"^(laser|zap_|zapTwoTone)", "laser"),
    ("digital-audio", r"^(powerUp|highUp|phaserUp|zapThreeToneUp|threeTone|twoTone)", "power-up"),
    ("digital-audio", r"^(lowDown|highDown|phaserDown|zapThreeToneDown|lowThreeTone)", "power-down"),
    ("digital-audio", r"^(pepSound|phaseJump)", "bloop"),
    ("digital-audio", r"^spaceTrash", "glitch"),
    ("casino-audio", r"^chip", "money"),
    ("casino-audio", r"^di(c)?e", "dice"),
    ("sci-fi-sounds", r"^(explosionCrunch|lowFrequency_explosion)", "explosion"),
    ("sci-fi-sounds", r"^laser", "laser"),
    ("sci-fi-sounds", r"^forceField", "force-field"),
    ("sci-fi-sounds", r"^impactMetal", "metal-hit"),
    ("sci-fi-sounds", r"^computerNoise", "glitch"),
    ("sci-fi-sounds", r"^slime", "slime"),
    ("rpg-audio", r"^handleCoins", "money"),
    ("rpg-audio", r"^(knifeSlice|drawKnife)", "knife"),
    ("rpg-audio", r"^chop", "thud"),
    ("rpg-audio", r"^creak", "creak"),
    ("rpg-audio", r"^metalPot", "metal-hit"),
    ("music-jingles", r"^jingles_NES", "jingle-8bit"),
    ("music-jingles", r"^jingles_SAX", "jingle-sax"),
    ("music-jingles", r"^jingles_HIT", "jingle-hit"),
    ("music-jingles", r"^jingles_PIZZI", "jingle-sneaky"),
    ("music-jingles", r"^jingles_STEEL", "jingle-steel"),
]
# Where every flat category goes in the kit, and WHEN to use it. Gemini reads these
# descriptions (via sound_kit/catalog.json) to choose a sound that fits the actual moment.
# Categories not listed here are dropped (not useful for meme edits).
CATEGORY_GUIDE = {
    # impact: lands exactly on the peak frame
    "boom": ("impact/bass-boom", "the classic meme bass boom: shock reveal, staring in disbelief, 'wait what', dramatic realization"),
    "punch": ("impact/punch", "someone or something gets hit, a fist fight, an NPC gets punched, a car hits a person"),
    "thud": ("impact/thud", "a body falls, someone gets knocked down, a heavy landing, ragdoll physics"),
    "metal-hit": ("impact/metal-clang", "car crash, hitting a pole or wall, metal objects colliding"),
    "wood-hit": ("impact/wood-knock", "light comedic hit, something knocking or bonking, door bang"),
    "glass-break": ("impact/glass-shatter", "windows smashing, car windshield breaking, something fragile shattering, a 'broken' reaction"),
    "explosion": ("impact/explosion", "explosions, cars blowing up, grenades, total chaos"),
    "bonk": ("impact/bonk", "cartoon bonk: dumb mistake, hitting your head, 'go to horny jail' energy, silly fail"),
    # fail: when something goes wrong
    "fail-trombone": ("fail/sad-trombone", "wah-wah-wah-waaah: an obvious fail, plan goes wrong, cringe moment"),
    "power-down": ("fail/power-down", "losing, dying, getting arrested, energy draining away, disappointment"),
    "error": ("fail/error-buzzer", "wrong answer buzzer: bad decision, failed attempt, 'nope'"),
    "voice-mission-failed": ("fail/mission-failed", "GTA-style 'MISSION FAILED': the streamer dies, gets caught, the heist fails"),
    "voice-game-over": ("fail/game-over", "'GAME OVER': death, total fail, everything is ruined"),
    "voice-you-lose": ("fail/you-lose", "'YOU LOSE': losing a fight, a race or an argument"),
    "voice-loser": ("fail/loser", "'LOSER': mocking a big fail or a sore loser"),
    "voice-wrong": ("fail/wrong", "'WRONG': a bad guess or a wrong decision"),
    "voice-time-over": ("fail/time-over", "'TIME OVER': too late, missed the chance"),
    # win: when something goes right
    "power-up": ("win/power-up", "a glow-up, getting something good, leveling up, a lucky moment"),
    "voice-mission-completed": ("win/mission-completed", "'MISSION COMPLETED': pulling off a heist or plan perfectly"),
    "voice-flawless-victory": ("win/flawless-victory", "'FLAWLESS VICTORY': a clean win, an epic play, outsmarting someone"),
    "voice-you-win": ("win/you-win", "'YOU WIN': winning a fight, race or argument"),
    "voice-winner": ("win/winner", "'WINNER': an obvious win, a flex"),
    "voice-new-highscore": ("win/new-highscore", "'NEW HIGHSCORE': breaking a record, a crazy stunt"),
    "voice-level-up": ("win/level-up", "'LEVEL UP': improvement, a rank up, a glow-up"),
    "voice-objective-achieved": ("win/objective-achieved", "'OBJECTIVE ACHIEVED': got what they wanted"),
    "voice-congratulations": ("win/congratulations", "'CONGRATULATIONS': sarcastic or real congratulations"),
    "voice-correct": ("win/correct", "'CORRECT': guessing right, being right"),
    "jingle-hit": ("win/jingle-victory", "a short victory jingle at the end of a win"),
    # hype: energy and action
    "airhorn": ("hype/airhorn", "MLG airhorn: an insane play, a hype moment, celebration"),
    "voice-fight": ("hype/fight", "'FIGHT!': a fight is about to start, a standoff, a confrontation"),
    "voice-go-go-go": ("hype/go-go-go", "'GO GO GO': fleeing, a chase starts, running from cops"),
    "voice-go": ("hype/go", "'GO!': the start of a race, chase or crazy idea"),
    "voice-multi-kill": ("hype/multi-kill", "'MULTI KILL': taking out many NPCs or cops at once"),
    "voice-combo": ("hype/combo", "'COMBO': chaining stunts or hits"),
    "voice-combo-breaker": ("hype/combo-breaker", "'COMBO BREAKER': something interrupts a streak"),
    "voice-final-round": ("hype/final-round", "'FINAL ROUND': the last attempt, a showdown"),
    "voice-sudden-death": ("hype/sudden-death", "'SUDDEN DEATH': a tense do-or-die moment"),
    "voice-prepare-yourself": ("hype/prepare-yourself", "'PREPARE YOURSELF': right before something crazy happens"),
    "voice-kill-him": ("hype/kill-him", "'KILL HIM': chat or streamer going after an NPC (comedic)"),
    "riser": ("hype/riser", "tension rising into a reveal or before the peak"),
    # danger: tension and threat
    "siren": ("danger/siren", "police show up, wanted level, getting chased by cops"),
    "heartbeat": ("danger/heartbeat", "suspense, hiding, about to get caught, nervous moment"),
    "sting": ("danger/suspense-sting", "a dark reveal, something creepy or ominous"),
    "voice-look-out": ("danger/look-out", "'LOOK OUT': sudden danger, a car or NPC coming"),
    "voice-get-down": ("danger/get-down", "'GET DOWN': gunfire, ducking"),
    "voice-fire-in-the-hole": ("danger/fire-in-the-hole", "'FIRE IN THE HOLE': a grenade or explosion is coming"),
    "voice-watch-my-back": ("danger/watch-my-back", "'WATCH MY BACK': paranoia, being followed"),
    "voice-call-for-backup": ("danger/call-for-backup", "'CALL FOR BACKUP': outnumbered, overwhelmed"),
    "voice-cover-me": ("danger/cover-me", "'COVER ME': a shootout"),
    "voice-hurry-up": ("danger/hurry-up", "'HURRY UP': running out of time, panic"),
    "voice-medic": ("danger/medic", "'MEDIC!': someone gets badly hurt (comedic)"),
    "voice-sniper": ("danger/sniper", "'SNIPER': getting shot from far away out of nowhere"),
    "voice-target-destroyed": ("danger/target-destroyed", "'TARGET DESTROYED': something or someone obliterated"),
    # comedy: silly and absurd
    "boing": ("comedy/boing", "cartoon boing: bouncing, jumping, goofy physics, something springy"),
    "record-scratch": ("comedy/record-scratch", "'wait, what?' freeze moment: something awkward or unexpected stops everything"),
    "slime": ("comedy/squish", "gross or squishy moment, stepping in something"),
    "bloop": ("comedy/bloop", "a small silly sound for a goofy action or a dumb idea"),
    "jingle-sax": ("comedy/sexy-sax", "flirting, rizz, a romantic or suggestive moment (Lucia, dates, strip club jokes)"),
    "jingle-sneaky": ("comedy/sneaky", "sneaking, stealing, being sus, a mischievous plan"),
    "jingle-8bit": ("comedy/8bit-jingle", "retro game jingle: gamer moments, nostalgic or nerdy reactions"),
    "jingle-steel": ("comedy/island-vibes", "chill tropical vibe: Vice City beaches, vacation, relaxing in-game"),
    "voice-its-a-tie": ("comedy/its-a-tie", "'IT'S A TIE': both fail, nobody wins"),
    "voice-tie-breaker": ("comedy/tie-breaker", "'TIE BREAKER': deciding an argument"),
    # transitions
    "whoosh": ("transition/whoosh", "fast cut, a meme cutaway, something flying past"),
    "glitch": ("transition/glitch", "a game glitch or bug, lag, the game breaking, a buggy NPC"),
    "scratch": ("transition/scratch", "a quick scratch or rewind"),
    "laser": ("transition/zap", "sci-fi zap: something weird, a teleport, a glitchy physics moment"),
    "force-field": ("transition/warp", "a strange or supernatural moment, a weird effect"),
    # money
    "money": ("money/coins", "money, robbing a store, a heist payout, buying something, getting rich"),
    "dice": ("money/dice-roll", "gambling, taking a risk, a casino, luck"),
    "ding": ("money/ding", "a positive notification: correct, a lightbulb idea, something clicks"),
    "pop": ("money/pop", "a small pop for something appearing"),
}
# synthesized sounds: name -> (flat category, ffmpeg lavfi audio source)
SYNTH_SOUNDS = {
    "boom-vine": ("boom", "aevalsrc='0.95*sin(2*PI*(45+150*exp(-15*t))*t)*exp(-3*t)':s=44100:d=1.3"),
    "boom-deep": ("boom", "aevalsrc='0.95*sin(2*PI*(32+90*exp(-10*t))*t)*exp(-2.2*t)':s=44100:d=1.8"),
    "boom-distorted": ("boom", "aevalsrc='max(-0.7,min(0.7,2.2*sin(2*PI*(50+160*exp(-14*t))*t)*exp(-3*t)))':s=44100:d=1.2"),
    "boom-cinematic": ("boom", "aevalsrc='0.8*sin(2*PI*(38+120*exp(-8*t))*t)*exp(-1.5*t)+0.3*(random(0)-0.5)*exp(-6*t)':s=44100:d=2.5,lowpass=f=1800"),
    "airhorn": ("airhorn", "aevalsrc='0.22*(sgn(sin(2*PI*466*t))+sgn(sin(2*PI*554*t))+sgn(sin(2*PI*698*t)))*if(lt(mod(t,0.33),0.26),1,0)':s=44100:d=1.3,lowpass=f=3200"),
    "airhorn-long": ("airhorn", "aevalsrc='0.22*(sgn(sin(2*PI*466*t))+sgn(sin(2*PI*554*t))+sgn(sin(2*PI*698*t)))':s=44100:d=1.4,lowpass=f=3200,afade=t=out:st=1.1:d=0.3"),
    "fail-trombone": ("fail-trombone", "aevalsrc='0.35*(sin(2*PI*F*t)+0.5*sin(4*PI*F*t)+0.3*sin(6*PI*F*t))*min(1,10*mod(t,0.5))':"
                      "s=44100:d=2.4".replace("F", "(if(lt(t,0.5),392,if(lt(t,1.0),370,if(lt(t,1.5),349,330+6*sin(2*PI*6*t)))))")),
    "record-scratch": ("record-scratch", "aevalsrc='0.9*(random(0)-0.5)*abs(sin(2*PI*7*t))+0.4*sin(2*PI*(400+900*sin(2*PI*5*t))*t)':s=44100:d=0.55,bandpass=f=1500:w=1800"),
    "riser": ("riser", "aevalsrc='(0.35*sin(2*PI*(150*t+260*t*t))+0.25*(random(0)-0.5))*t/2':s=44100:d=2.0,highpass=f=200"),
    "bonk": ("bonk", "aevalsrc='0.9*sin(2*PI*(700*exp(-18*t))*t)*exp(-14*t)':s=44100:d=0.45"),
    "boing": ("boing", "aevalsrc='0.7*sin(2*PI*220*t+3*sin(2*PI*14*t)*exp(-2*t))*exp(-3.5*t)':s=44100:d=1.0"),
    "ding": ("ding", "aevalsrc='0.6*sin(2*PI*1318*t)*exp(-4*t)+0.3*sin(2*PI*2637*t)*exp(-6*t)':s=44100:d=1.3"),
    "buzzer-wrong": ("error", "aevalsrc='0.35*sgn(sin(2*PI*110*t))*if(lt(t,0.75),1,0)':s=44100:d=0.8,lowpass=f=2500"),
    "siren": ("siren", "aevalsrc='0.45*sin(2*PI*750*t-200*cos(2*PI*1.6*t))':s=44100:d=2.0,afade=t=out:st=1.6:d=0.4"),
    "heartbeat": ("heartbeat", "aevalsrc='0.9*sin(2*PI*55*t)*(exp(-25*mod(t,0.8))+0.7*exp(-25*max(0,mod(t,0.8)-0.22))*gte(mod(t,0.8),0.22))':s=44100:d=1.6"),
    "sting-suspense": ("sting", "aevalsrc='0.5*sin(2*PI*65*t)*min(1,t*3)+0.4*sin(2*PI*(98+2*sin(2*PI*5*t))*t)*min(1,t*3)':s=44100:d=2.0,afade=t=out:st=1.4:d=0.6"),
    "whoosh-fast": ("whoosh", "anoisesrc=d=0.35:c=pink:a=0.6,highpass=f=700,lowpass=f=7000,afade=t=in:d=0.18,afade=t=out:st=0.18:d=0.17"),
    "whoosh-slow": ("whoosh", "anoisesrc=d=0.8:c=pink:a=0.6,highpass=f=400,lowpass=f=6000,afade=t=in:d=0.45,afade=t=out:st=0.45:d=0.35"),
    "glitch-stutter": ("glitch", "aevalsrc='0.5*sgn(sin(2*PI*(300+2000*random(0))*t))*if(lt(mod(t,0.06),0.03),1,0)':s=44100:d=0.5,lowpass=f=5000"),
}
NOTO_EMOJI_URL = "https://fonts.gstatic.com/s/e/notoemoji/latest/{code}/512.gif"
EMOJIS = {  # name -> codepoint(s), all verified to exist as Noto animated GIFs (Nov 2026)
    "sos": "1f198", "rainbow": "1f308", "wave": "1f30a", "burger": "1f354", "pizza": "1f355",
    "champagne": "1f37e", "popcorn": "1f37f", "jack-o-lantern": "1f383", "fireworks": "1f386",
    "party-popper": "1f389", "confetti": "1f38a", "bullseye": "1f3af", "slot-machine": "1f3b0",
    "die": "1f3b2", "music-notes": "1f3b6", "racing-car": "1f3ce_fe0f", "motorcycle": "1f3cd_fe0f",
    "trophy": "1f3c6", "gold-medal": "1f947", "crocodile": "1f40a", "monkey": "1f412", "eyes": "1f440",
    "eye": "1f441_fe0f", "point-up": "1f446", "point-down": "1f447", "point-left": "1f448",
    "point-right": "1f449", "waving": "1f44b", "ok-hand": "1f44c", "thumbs-up": "1f44d",
    "thumbs-down": "1f44e", "clapping": "1f44f", "crown": "1f451", "alien": "1f47d", "ghost": "1f47b",
    "angry-devil": "1f47f", "skull": "1f480", "dancing": "1f483", "kiss": "1f48b", "gem": "1f48e",
    "broken-heart": "1f494", "heart-arrow": "1f498", "blue-heart": "1f499", "green-heart": "1f49a",
    "yellow-heart": "1f49b", "purple-heart": "1f49c", "hundred": "1f4af", "bomb": "1f4a3",
    "collision": "1f4a5", "poop": "1f4a9", "dizzy": "1f4ab", "flexed-biceps": "1f4aa",
    "money-wings": "1f4b8", "camera-flash": "1f4f8", "bell": "1f514", "crystal-ball": "1f52e",
    "middle-finger": "1f595", "black-heart": "1f5a4", "smiling-devil": "1f608", "heart-eyes": "1f60d",
    "cool-sunglasses": "1f60e", "smirk": "1f60f", "neutral": "1f610", "expressionless": "1f611",
    "unamused": "1f612", "blowing-kiss": "1f618", "angry-face": "1f620", "angry": "1f621",
    "steam-from-nose": "1f624", "fearful": "1f628", "weary": "1f629", "tired": "1f62b",
    "grimacing": "1f62c", "loudly-crying": "1f62d", "open-mouth": "1f62e", "hushed": "1f62f",
    "screaming-in-fear": "1f631", "astonished": "1f632", "flushed": "1f633", "sleeping": "1f634",
    "dizzy-face": "1f635", "upside-down": "1f643", "eye-roll": "1f644", "see-no-evil": "1f648",
    "folded-hands": "1f64f", "car": "1f697", "rotating-light": "1f6a8", "traffic-light": "1f6a6",
    "airplane": "2708_fe0f", "zipper-mouth": "1f910", "nerd": "1f913", "robot": "1f916",
    "rock-on": "1f918", "call-me": "1f919", "handshake": "1f91d", "crossed-fingers": "1f91e",
    "clown": "1f921", "nauseated": "1f922", "rolling-on-floor-laughing": "1f923", "drooling": "1f924",
    "sneezing": "1f927", "raised-eyebrow": "1f928", "shushing": "1f92b", "cursing": "1f92c",
    "hand-over-mouth": "1f92d", "vomiting": "1f92e", "mind-blown": "1f92f", "party": "1f973",
    "woozy": "1f974", "hot-face": "1f975", "cold-face": "1f976", "pleading": "1f97a",
    "yawning": "1f971", "smiling-tear": "1f972", "holding-back-tears": "1f979", "shark": "1f988",
    "orangutan": "1f9a7", "monocle": "1f9d0", "brain": "1f9e0", "juice": "1f9c3", "melting": "1fae0",
    "saluting": "1fae1", "open-eyes-hand-over-mouth": "1fae2", "peeking-eye": "1fae3",
    "pinched-fingers": "1f90c", "white-heart": "1f90d", "orange-heart": "1f9e1", "index-up": "261d_fe0f",
    "warning": "26a0_fe0f", "lightning": "26a1", "victory": "270c_fe0f", "check": "2705",
    "sparkles": "2728", "cross": "274c", "question": "2753", "exclamation": "2757",
    "double-exclamation": "203c_fe0f", "red-heart": "2764_fe0f", "tears-of-joy": "1f602",
    "fire": "1f525", "thinking": "1f914", "sparkler": "1f387",
}
EMOJI_SIZE_PX = 200
PEAK_DBFS = -3.0


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def run_ffmpeg(*arguments):
    return subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
                          capture_output=True, text=True)


def peak_dbfs(audio_path):
    output = subprocess.run(["ffmpeg", "-hide_banner", "-i", audio_path, "-af", "volumedetect", "-f", "null", "-"],
                            capture_output=True, text=True).stderr
    match = re.search(r"max_volume: (-?[\d.]+) dB", output)
    return float(match.group(1)) if match else None


def export_sound(source_path, output_path):
    """Trim leading silence, match peak loudness to PEAK_DBFS, write a small mono mp3."""
    current_peak = peak_dbfs(source_path)
    gain_db = 0.0 if current_peak is None else PEAK_DBFS - current_peak
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    result = run_ffmpeg("-i", source_path, "-af",
                        f"silenceremove=start_periods=1:start_threshold=-50dB,volume={gain_db:.1f}dB",
                        "-ac", "1", "-ar", "44100", "-b:a", "96k", output_path)
    return result.returncode == 0


def kenney_category(pack, file_name):
    stem = os.path.splitext(file_name)[0]
    if pack.startswith("voiceover-pack"):
        phrase = slugify(stem.replace("war_", "").replace("'", ""))
        if not phrase or phrase.isdigit() or phrase.startswith("preview"):
            return None
        return f"voice-{phrase}"
    for rule_pack, pattern, category in KENNEY_RULES:
        if rule_pack == pack and re.search(pattern, stem):
            return category
    return None


def download_kenney_pack(pack, work_dir):
    """Download and unzip one Kenney pack (the site hands out signed links per session)."""
    page_url = f"https://kenney.nl/assets/{pack}"
    cookie_jar = os.path.join(work_dir, "cookies.txt")
    curl = ["curl", "-s", "-L", "--max-time", "180", "-c", cookie_jar, "-b", cookie_jar, "-A", BROWSER_USER_AGENT]
    subprocess.run(curl + ["-o", os.devnull, page_url], check=True)
    link_reply = subprocess.run(curl + ["-e", page_url, "-H", "Accept: application/json",
                                        f"https://kenney.nl/download-link/{f'assets/{pack}'.encode().hex()}"],
                                capture_output=True, text=True).stdout
    download_url = json.loads(link_reply)["url"]
    zip_path = os.path.join(work_dir, pack + ".zip")
    subprocess.run(curl + ["-o", zip_path, download_url], check=True)
    extract_dir = os.path.join(work_dir, pack)
    zipfile.ZipFile(zip_path).extractall(extract_dir)
    return extract_dir


def build_sounds():
    """(Re)build assets/sound_kit/ and its catalog. Returns the catalog list."""
    if os.path.isdir(paths.SOUND_KIT_DIR):
        shutil.rmtree(paths.SOUND_KIT_DIR)
    catalog = []
    with tempfile.TemporaryDirectory(prefix="clipwatcher-kit-") as work_dir:
        for pack in KENNEY_PACKS:
            log(f"sound kit: downloading Kenney {pack} (CC0)")
            extract_dir = download_kenney_pack(pack, work_dir)
            for folder, _subfolders, file_names in sorted(os.walk(extract_dir)):
                for file_name in sorted(file_names):
                    if not file_name.lower().endswith((".ogg", ".wav", ".mp3")):
                        continue
                    category = CATEGORY_GUIDE.get(kenney_category(pack, file_name) or "", (None,))[0]
                    if not category:
                        continue
                    voice = ("-female" if "female" in folder.lower() else "-male" if "male" in folder.lower()
                             else "-fighter" if pack.endswith("fighter") else "")
                    name = slugify(os.path.splitext(file_name)[0]) + voice
                    relative = os.path.join(category, name + ".mp3")
                    if export_sound(os.path.join(folder, file_name), os.path.join(paths.SOUND_KIT_DIR, relative)):
                        catalog.append({"file": relative, "category": category, "source": f"Kenney {pack}",
                                        "license": "CC0 1.0"})
        log("sound kit: synthesizing meme-style sounds")
        for name, (flat_category, lavfi_source) in SYNTH_SOUNDS.items():
            category = CATEGORY_GUIDE[flat_category][0]
            raw_path = os.path.join(work_dir, name + ".wav")
            if run_ffmpeg("-f", "lavfi", "-i", lavfi_source, raw_path).returncode != 0:
                log(f"sound kit: could not synthesize {name}")
                continue
            relative = os.path.join(category, name + ".mp3")
            if export_sound(raw_path, os.path.join(paths.SOUND_KIT_DIR, relative)):
                catalog.append({"file": relative, "category": category, "source": "synthesized (clip-watcher)",
                                "license": "CC0 1.0"})
    write_catalog(catalog)
    log(f"sound kit: {len(catalog)} sounds in {len({entry['category'] for entry in catalog})} categories")
    return catalog


def write_catalog(sounds):
    """catalog.json: {category: {"use_when": ..., "files": [...]}} + a README for humans."""
    use_when = {category: description for category, description in CATEGORY_GUIDE.values()}
    categories = {}
    for sound in sorted(sounds, key=lambda entry: entry["file"]):
        entry = categories.setdefault(sound["category"], {"use_when": use_when[sound["category"]], "files": [],
                                                          "sources": []})
        entry["files"].append(sound["file"])
        if sound["source"] not in entry["sources"]:
            entry["sources"].append(sound["source"])
    with open(paths.SOUND_KIT_CATALOG_FILE, "w", encoding="utf-8") as catalog_file:
        json.dump(dict(sorted(categories.items())), catalog_file, indent=1, ensure_ascii=False)
    lines = ["# Sound kit", "",
             "Built by `python3 -m clipwatcher build-kit`. Folders are grouped by WHEN to use them; "
             "Gemini reads the same descriptions from `catalog.json` and picks the sound that fits the "
             "actual moment (it also sees frames of the clip). All sounds are CC0 (see `../CREDITS.md`).", "",
             "| Sound | Use when | Files |", "|---|---|---|"]
    lines += [f"| `{category}` | {entry['use_when']} | {len(entry['files'])} |"
              for category, entry in sorted(categories.items())]
    with open(os.path.join(paths.SOUND_KIT_DIR, "README.md"), "w", encoding="utf-8") as readme:
        readme.write("\n".join(lines) + "\n")


def build_emoji():
    """Download every EMOJIS entry and store it as a 200 px transparent VP9 .webm in assets/emoji/."""
    os.makedirs(paths.EMOJI_DIR, exist_ok=True)
    built = 0
    with tempfile.TemporaryDirectory(prefix="clipwatcher-emoji-") as work_dir:
        for name, code in sorted(EMOJIS.items()):
            output_path = os.path.join(paths.EMOJI_DIR, name + ".webm")
            if os.path.exists(output_path):
                built += 1
                continue
            source_path = os.path.join(work_dir, name + ".gif")
            download = subprocess.run(["curl", "-s", "-f", "-L", "--max-time", "60", "-o", source_path,
                                       NOTO_EMOJI_URL.format(code=code)])
            if download.returncode != 0:
                log(f"emoji: {name} not available")
                continue
            result = run_ffmpeg("-i", source_path, "-vf", f"fps=20,scale={EMOJI_SIZE_PX}:-1:flags=lanczos,format=yuva420p",
                                "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "40", "-auto-alt-ref", "0", output_path)
            built += result.returncode == 0
    log(f"emoji: {built} animated emojis in {paths.EMOJI_DIR}")
    return built


def write_credits():
    with open(paths.ASSET_CREDITS_FILE, "w", encoding="utf-8") as credits_file:
        credits_file.write(
            "# Asset credits\n\n"
            "| Folder | Source | License |\n|---|---|---|\n"
            "| `assets/fonts/` | Anton by Vernon Adams | SIL Open Font License (`fonts/OFL-Anton.txt`) |\n"
            "| `assets/sound_kit/` (Kenney categories) | [Kenney.nl](https://kenney.nl) audio packs: "
            + ", ".join(KENNEY_PACKS) + " | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |\n"
            "| `assets/sound_kit/` (synthesized) | generated by `clipwatcher/media_kit.py` | CC0 1.0 |\n"
            "| `assets/emoji/` | [Google Noto Emoji animations](https://googlefonts.github.io/noto-emoji-animation/) "
            "| [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |\n\n"
            "Rebuild everything with `python3 -m clipwatcher build-kit`.\n"
            "Every sound is listed with its source in `assets/sound_kit/catalog.json`.\n")


def build_kit(parts=("sounds", "emoji")):
    if "sounds" in parts:
        build_sounds()
    if "emoji" in parts:
        build_emoji()
    write_credits()
