"""Fill YOUR private meme library (git-ignored, stays on your machine/server):

    sounds/sfx/<group>/<name>.mp3   meme sounds from MyInstants (1,400+ named meme sounds:
                                    vine boom, bruh, fahhh, airhorn, metal pipe...)
    sounds/sfx/catalog.json         title + group + "use when" per sound (Gemini reads it)
    memes/<name>.mp4                reaction meme videos from a pack file (YouTube via yt-dlp)

    python3 -m clipwatcher import-sounds                     # top 30 pages (~1,000 sounds)
    python3 -m clipwatcher import-sounds --pages 40 --search "fahh,bruh,metal pipe,taco bell"
    python3 -m clipwatcher label-sounds                      # (re)sort + describe with Gemini
    python3 -m clipwatcher import-memes packs/reaction-memes.txt

Groups match the bundled kit (impact, fail, win, hype, danger, comedy, transition, money)
plus "reaction" (screams, laughs, "bruh", "oh no") and "quote" (famous spoken lines).
YouTube blocks cloud servers: set YTDLP_COOKIES to a cookies.txt exported from your
browser, or run import-memes on your own PC and copy memes/ to the server.
These are third-party clips: whether you use them is your call (see docs/viral-playbook.md).
"""
import concurrent.futures
import html
import json
import os
import re
import shutil
import subprocess
import tempfile

from clipwatcher import paths, settings
from clipwatcher.log import log

MYINSTANTS = "https://www.myinstants.com"
BROWSER_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
SOUND_GROUPS = ("impact", "fail", "win", "hype", "danger", "comedy", "transition", "money", "reaction", "quote")
UNSORTED_GROUP = "unsorted"
MAX_SOUND_S = 6.0
MAX_SOURCE_SOUND_S = 30.0       # longer than this is a song, not a meme sound
LABEL_BATCH_SIZE = 120
INSTANT_PATTERN = re.compile(
    r"play\('(?P<path>/media/sounds/[^']+\.mp3)'.*?class=\"instant-link link-secondary\">(?P<title>[^<]+)<", re.S)


def sounds_catalog_path():
    return os.path.join(paths.SFX_DIR, "catalog.json")


def load_sounds_catalog():
    try:
        with open(sounds_catalog_path(), encoding="utf-8") as catalog_file:
            return json.load(catalog_file)
    except (OSError, ValueError):
        return {}


def save_sounds_catalog(catalog):
    os.makedirs(paths.SFX_DIR, exist_ok=True)
    with open(sounds_catalog_path(), "w", encoding="utf-8") as catalog_file:
        json.dump(dict(sorted(catalog.items())), catalog_file, indent=1, ensure_ascii=False)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "sound"


def fetch_page(url):
    return subprocess.run(["curl", "-s", "-L", "--max-time", "30", "-A", BROWSER_USER_AGENT, url],
                          capture_output=True, text=True, errors="replace").stdout


def list_myinstants(pages, searches):
    """[(title, mp3 url)] from the best-of-all-time + trending lists and the searches, deduplicated."""
    list_urls = [f"{MYINSTANTS}/en/best_of_all_time/us/?page={page}" for page in range(1, pages + 1)]
    list_urls += [f"{MYINSTANTS}/en/trending/us/?page={page}" for page in range(1, 4)]
    list_urls += [f"{MYINSTANTS}/en/search/?name={query.strip().replace(' ', '+')}" for query in searches if query.strip()]
    found = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for page_html in pool.map(fetch_page, list_urls):
            for match in INSTANT_PATTERN.finditer(page_html):
                found.setdefault(MYINSTANTS + match.group("path"), html.unescape(match.group("title")).strip())
    return [(title, url) for url, title in found.items()]


def media_duration_s(media_path):
    output = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                             media_path], capture_output=True, text=True, errors="replace").stdout
    try:
        return float(output.strip())
    except ValueError:
        return 0.0


def download_sound(title, url, work_dir):
    """Download, skip songs, trim leading silence + to MAX_SOUND_S, level. Returns (file name, title) or None."""
    from clipwatcher.media_kit import export_sound
    source_path = os.path.join(work_dir, slugify(url.rsplit("/", 1)[-1]) + ".mp3")
    if subprocess.run(["curl", "-s", "-f", "-L", "--max-time", "60", "-A", BROWSER_USER_AGENT, "-o", source_path,
                       url]).returncode != 0:
        return None
    if not 0.1 < media_duration_s(source_path) <= MAX_SOURCE_SOUND_S:
        return None
    trimmed_path = source_path + ".trim.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", source_path, "-t", str(MAX_SOUND_S),
                    trimmed_path])
    file_name = slugify(title) + ".mp3"
    output_path = os.path.join(paths.SFX_DIR, UNSORTED_GROUP, file_name)
    if os.path.exists(output_path):  # downloaded by an earlier, interrupted run
        return file_name, title
    if not os.path.exists(trimmed_path):
        return None
    return (file_name, title) if export_sound(trimmed_path, output_path) else None


def safe_download(item, work_dir):
    try:
        return download_sound(*item, work_dir)
    except Exception as error:  # one broken sound must not stop the import
        log(f"skipped {item[0]!r}: {error}")
        return None


def import_sounds(pages=30, searches=()):
    """Download MyInstants meme sounds into sounds/sfx/unsorted/, then label them."""
    candidates = list_myinstants(pages, searches)
    catalog = load_sounds_catalog()
    known_sources = {entry.get("source") for entry in catalog.values()}
    candidates = [(title, url) for title, url in candidates if url not in known_sources]
    log(f"sound import: {len(candidates)} new sounds found on MyInstants")
    added = 0
    with tempfile.TemporaryDirectory(prefix="clipwatcher-sounds-") as work_dir, \
            concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for (title, url), result in zip(candidates, pool.map(lambda item: safe_download(item, work_dir), candidates)):
            if result:
                file_name, _title = result
                catalog[f"{UNSORTED_GROUP}/{file_name}"] = {"title": title, "use_when": title.lower(), "source": url}
                added += 1
                if added % 100 == 0:
                    save_sounds_catalog(catalog)
                    log(f"sound import: {added} sounds so far")
    save_sounds_catalog(catalog)
    log(f"sound import: {added} sounds added to {paths.SFX_DIR}")
    label_sounds()
    return added


def label_sounds():
    """Gemini sorts unsorted sounds into groups and writes a "use when" for each (by title)."""
    catalog = load_sounds_catalog()
    unsorted = [key for key in catalog if key.startswith(UNSORTED_GROUP + "/")]
    if not unsorted:
        return
    if not settings.GEMINI_API_KEY:
        log(f"label-sounds: no GEMINI_API_KEY - {len(unsorted)} sounds stay in sounds/sfx/{UNSORTED_GROUP}/ "
            "(titles still work as descriptions)")
        return
    from clipwatcher.gemini import ask_gemini_json
    for batch_start in range(0, len(unsorted), LABEL_BATCH_SIZE):
        batch = unsorted[batch_start:batch_start + LABEL_BATCH_SIZE]
        titles = "\n".join(f"{index}: {catalog[key]['title']}" for index, key in enumerate(batch))
        reply = ask_gemini_json(
            "These are names of meme sound effects from a soundboard. For each, pick a group from "
            f"{list(SOUND_GROUPS)} and write a short 'use_when' (what the sound is + the kind of moment in a "
            "GTA 6 live-stream clip it fits, max 15 words). Reply as JSON: {\"sounds\": [{\"index\": 0, "
            "\"group\": \"...\", \"use_when\": \"...\"}, ...]}\n" + titles, temperature=0.2) or {}
        for item in reply.get("sounds", []):
            try:
                key = batch[int(item["index"])]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            group = item.get("group") if item.get("group") in SOUND_GROUPS else UNSORTED_GROUP
            new_key = f"{group}/{key.split('/', 1)[1]}"
            if group != UNSORTED_GROUP and not os.path.exists(os.path.join(paths.SFX_DIR, new_key)):
                os.makedirs(os.path.join(paths.SFX_DIR, group), exist_ok=True)
                shutil.move(os.path.join(paths.SFX_DIR, key), os.path.join(paths.SFX_DIR, new_key))
                catalog[new_key] = catalog.pop(key)
                key = new_key
            if item.get("use_when"):
                catalog[key]["use_when"] = str(item["use_when"])[:160]
        save_sounds_catalog(catalog)
        log(f"label-sounds: {min(batch_start + LABEL_BATCH_SIZE, len(unsorted))}/{len(unsorted)} done")


def import_memes(pack_file):
    """Import every line of a pack file: "query or URL | name | use when" (name and use when optional)."""
    from clipwatcher.render.memes import add_meme, load_catalog
    existing = {entry.get("source") for entry in load_catalog().values()}
    added = 0
    with open(pack_file, encoding="utf-8") as pack:
        lines = [line.strip() for line in pack if line.strip() and not line.lstrip().startswith("#")]
    for line in lines:
        parts = [part.strip() for part in line.split("|")]
        query, name = parts[0], (parts[1] if len(parts) > 1 else None)
        use_when = parts[2] if len(parts) > 2 else None
        source = query if query.startswith("http") else f"ytsearch1:{query}"
        if source in existing:
            continue
        try:
            add_meme(source, name=name, use_when=use_when)
            added += 1
        except Exception as error:
            log(f"meme import failed for {query!r}: {error}")
    log(f"meme import: {added} memes added to {paths.MEMES_DIR}")
    return added
