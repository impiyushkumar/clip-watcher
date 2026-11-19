"""Sound design: a sound exactly on the peak, an optional reaction sound right after it,
a whoosh into the meme, background music that ducks under the voice, -14 LUFS.

Where sounds come from (Gemini sees ALL of them as one menu and picks what fits):
    assets/sound_kit/<group>/<category>/   bundled CC0 kit; catalog.json says when to use each
                                            category (built by `python3 -m clipwatcher build-kit`)
    sounds/sfx/                             your own sounds; the file name says what it is
    sounds/music/                           background tracks; one random track per clip
Without the kit a deep boom and a whoosh are generated into clips/.builtin_sounds/.
"""
import json
import os
import random
import re
import subprocess

from clipwatcher import paths, settings
from clipwatcher.log import log

AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
BUILTIN_SOUNDS = {  # file name -> ffmpeg lavfi source
    "impact.wav": "aevalsrc='0.9*sin(2*PI*(42+140*exp(-14*t))*t)*exp(-3.5*t)"
                  "+0.25*(random(0)-0.5)*exp(-30*t)':s=44100:d=1.1",
    "whoosh.wav": "anoisesrc=d=0.45:c=pink:a=0.5,highpass=f=500,lowpass=f=7000,"
                  "afade=t=in:d=0.25,afade=t=out:st=0.25:d=0.2",
}
WHOOSH_LEAD_S = 0.2   # the whoosh starts a little before the cut it leads into


def list_audio(folder):
    try:
        return sorted(name for name in os.listdir(folder) if name.lower().endswith(AUDIO_EXTENSIONS))
    except OSError:
        return []


def builtin_sound(name):
    """Path of a generated default sound, created on first use."""
    os.makedirs(paths.BUILTIN_SOUNDS_DIR, exist_ok=True)
    sound_path = os.path.join(paths.BUILTIN_SOUNDS_DIR, name)
    if not os.path.exists(sound_path):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", BUILTIN_SOUNDS[name], "-ac", "2", sound_path], check=True)
    return sound_path


DEFAULT_PEAK_SOUND = "impact/bass-boom"
CUSTOM_PREFIX = "custom/"


def load_sound_menu():
    """{category: "use when" text} for every kit category plus every sound in your library
    sounds/sfx/ (as "custom/<group>/<file>", described by sounds/sfx/catalog.json or by
    its file name). This is the menu Gemini chooses from."""
    menu = {}
    try:
        with open(paths.SOUND_KIT_CATALOG_FILE, encoding="utf-8") as catalog_file:
            for category, entry in json.load(catalog_file).items():
                menu[category] = entry["use_when"]
    except (OSError, ValueError, KeyError):
        pass
    try:
        with open(os.path.join(paths.SFX_DIR, "catalog.json"), encoding="utf-8") as catalog_file:
            library = json.load(catalog_file)
    except (OSError, ValueError):
        library = {}
    for folder, _subfolders, file_names in os.walk(paths.SFX_DIR):
        for file_name in sorted(file_names):
            if not file_name.lower().endswith(AUDIO_EXTENSIONS):
                continue
            relative = os.path.relpath(os.path.join(folder, file_name), paths.SFX_DIR).replace(os.sep, "/")
            description = (library.get(relative) or {}).get("use_when") or \
                os.path.splitext(file_name)[0].replace("-", " ").replace("_", " ")
            menu[CUSTOM_PREFIX + relative] = description
    return menu


def sound_files(category):
    """Absolute paths of every file in a menu category (variants of the same sound)."""
    if category.startswith(CUSTOM_PREFIX):
        file_path = os.path.join(paths.SFX_DIR, *category[len(CUSTOM_PREFIX):].split("/"))
        return [file_path] if os.path.isfile(file_path) else []
    folder = os.path.join(paths.SOUND_KIT_DIR, category)
    return [os.path.join(folder, name) for name in list_audio(folder)]


def best_category_by_keywords(text, menu):
    """No Gemini: the category whose name + "use when" shares the most words with `text`."""
    words = set(re.findall(r"[a-z]+", text.lower())) - {"the", "a", "an", "is", "it", "and", "or", "to", "in", "of"}
    scored = sorted(((len(words & set(re.findall(r"[a-z]+", (category + " " + description).lower()))), category)
                     for category, description in menu.items()), reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else None


def resolve_sound(category, fallback_text=""):
    """A file for `category` (random variant), else the keyword match, else the boom."""
    menu = load_sound_menu()
    for candidate in (category, best_category_by_keywords(fallback_text, menu) if fallback_text else None,
                      DEFAULT_PEAK_SOUND):
        files = sound_files(candidate) if candidate else []
        if files:
            return random.choice(files)
    return builtin_sound("impact.wav")


def whoosh_sound():
    files = sound_files("transition/whoosh")
    return random.choice(files) if files else builtin_sound("whoosh.wav")


def pick_music():
    if settings.MUSIC_VOLUME <= 0:
        return None
    tracks = list_audio(paths.MUSIC_DIR)
    return os.path.join(paths.MUSIC_DIR, random.choice(tracks)) if tracks else None


def media_duration_s(media_path):
    output = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "csv=p=0", media_path], capture_output=True, text=True, errors="replace").stdout
    try:
        return float(output.strip())
    except ValueError:
        return 0.0


def has_audio(media_path):
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                            "stream=index", "-of", "csv=p=0", media_path], capture_output=True, text=True, errors="replace")
    return probe.stdout.strip() != ""


def mix_audio(video_path, output_path, sound_events, music_path=None, normalize=True):
    """Mix sound_events [(sound_path, at_s, volume[, max_duration_s])] and ducked music into the clip's audio,
    level it to LOUDNESS_LUFS (if normalize), write output_path (video copied). Returns success.
    Sound files may be videos (a sticker meme's audio): their audio stream is used."""
    duration_s = media_duration_s(video_path)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video_path]
    if has_audio(video_path):
        voice_source = "[0:a]"
    else:
        command += ["-f", "lavfi", "-t", f"{duration_s:.2f}", "-i", "anullsrc=r=48000:cl=stereo"]
        voice_source = "[1:a]"
    first_extra_input = 2 if voice_source == "[1:a]" else 1
    graph = [f"{voice_source}aresample=48000,aformat=channel_layouts=stereo,asplit=2[voice][voice_key]"]
    mix_inputs = ["[voice]"]
    for offset, event in enumerate(sound_events):
        sound_path, at_s, volume = event[:3]
        trim = f"atrim=0:{event[3]:.2f}," if len(event) > 3 and event[3] else ""  # optional max duration
        command += ["-i", sound_path]
        delay_ms = max(0, int(at_s * 1000))
        label = f"[sfx{offset}]"
        graph.append(f"[{first_extra_input + offset}:a]{trim}aresample=48000,aformat=channel_layouts=stereo,"
                     f"volume={volume},adelay={delay_ms}|{delay_ms}{label}")
        mix_inputs.append(label)
    if music_path:
        command += ["-stream_loop", "-1", "-i", music_path]
        music_input = first_extra_input + len(sound_events)
        fade_out_start_s = max(0.0, duration_s - 0.6)
        graph.append(f"[{music_input}:a]aresample=48000,aformat=channel_layouts=stereo,"
                     f"atrim=0:{duration_s:.2f},volume={settings.MUSIC_VOLUME},"
                     f"afade=t=in:d=0.4,afade=t=out:st={fade_out_start_s:.2f}:d=0.6[music_raw]")
        graph.append("[music_raw][voice_key]sidechaincompress=threshold=0.03:ratio=8:attack=15:release=350[music]")
        mix_inputs.append("[music]")
    else:
        graph.append("[voice_key]anullsink")
    loudness = f",loudnorm=I={settings.LOUDNESS_LUFS}:TP=-1.5:LRA=11" if normalize else ""
    graph.append(f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:normalize=0"
                 f"{loudness},aresample=48000[audio]")
    command += ["-filter_complex", ";".join(graph), "-map", "0:v", "-map", "[audio]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", output_path]
    result = subprocess.run(command, capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        log(f"audio mix failed: {result.stderr.strip()[-300:]}")
    return result.returncode == 0


def integrated_loudness(media_path):
    """Measured loudness in LUFS (EBU R128), or None."""
    output = subprocess.run(["ffmpeg", "-hide_banner", "-i", media_path, "-af", "ebur128", "-f", "null", "-"],
                            capture_output=True, text=True, errors="replace").stderr
    match = re.findall(r"I:\s+(-?[\d.]+) LUFS", output)
    return float(match[-1]) if match else None


def correct_loudness(media_path, tolerance_db=1.0):
    """loudnorm's single pass undershoots on short, spiky meme edits: measure the result and
    apply the remaining gain (video copied, limited so peaks don't clip)."""
    measured = integrated_loudness(media_path)
    if measured is None or measured < -60 or abs(measured - settings.LOUDNESS_LUFS) <= tolerance_db:
        return
    gain_db = settings.LOUDNESS_LUFS - measured
    corrected_path = media_path + ".loud.mp4"
    result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", media_path,
                             "-af", f"volume={gain_db:.2f}dB,alimiter=limit=0.89:level=false", "-c:v", "copy",
                             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", corrected_path])
    if result.returncode == 0:
        os.replace(corrected_path, media_path)
    elif os.path.exists(corrected_path):
        os.remove(corrected_path)
