# Conventions

Rules every contributor (human or AI) follows in this repo. If code and this file disagree,
fix the code. If a rule needs to change, change it here first in the same commit.

## 1. Naming

### Folders
| Kind | Rule | Examples |
|---|---|---|
| Python package | `lowercase`, one word if possible, else `snake_case`; named after a **pipeline stage or role** | `clipwatcher/`, `capture/`, `render/`, `publish/` |
| Other folders | `lowercase`, one word, plural for collections | `scripts/`, `docs/`, `tests/`, `assets/fonts/`, `memes/` |
| Runtime data | `lowercase`, git-ignored, created by the code | `clips/raw/`, `clips/ready/`, `clips/queue/`, `rec/` |

### Files
| Kind | Rule | Examples |
|---|---|---|
| Python module | `snake_case.py`, a **noun for what it is or does**. No `utils.py`, `helpers.py` (except in tests), `misc.py`, `new_*.py`, `*_v2.py` | `spike_detector.py`, `clip_cutter.py`, `post_text.py` |
| Shell script | `kebab-case.sh`, **verb first** | `install.sh`, `watch-channel.sh`, `setup-server.sh` |
| Docs | `kebab-case.md` in `docs/` | `setup-youtube.md` |
| Root docs | `UPPERCASE.md` | `README.md`, `AGENTS.md`, `CONVENTIONS.md`, `CLAUDE.md` |
| Tests | `tests/test_<module or feature>.py` | `tests/test_spike_detector.py` |

### Python code
| Thing | Style | Examples |
|---|---|---|
| Variables, functions, arguments | `snake_case`, full words | `clip_name`, `recording_dir`, `pick_hashtags()` |
| Functions | **verb first** | `cut_raw_clip()`, `build_caption()`, `load_auto_settings()` |
| Booleans | `is_` / `has_` / `show_` / a yes-no word | `is_good_hour`, `has_audio()`, `SHOW_HOOK` |
| Classes | `PascalCase` noun | `SpikeDetector`, `ClipJob`, `Scheduler` |
| Constants | `UPPER_SNAKE_CASE`, at the top of the module | `BUCKET_S`, `MAX_HASHTAGS` |
| Private | leading `_` | `_loaded_model`, `_text()` |
| Unused values | leading `_` | `for _attempt in range(3)` |

**Unit suffixes are required** when a number has a unit:

| Suffix | Meaning | Example |
|---|---|---|
| `_s` | seconds (duration or offset) | `before_s`, `spike_at_s`, `length_s` |
| `_ts` | unix timestamp (seconds since 1970) | `created_ts`, `recording_start_ts` |
| `_h` | hours | `max_age_h`, `interval_h` |
| `_percent` | 0-100 | `DISK_LIMIT_PERCENT` |
| `_path` / `_file` | a file path | `raw_path`, `SCOREBOARD_FILE` |
| `_dir` | a folder path | `recording_dir`, `QUEUE_DIR` |

**Not allowed:** single-letter names (`a`, `o`, `r`, `t`, `it`, `p`), except `i`/`j` as plain
loop counters; vague names (`data2`, `tmp`, `stuff`, `thing`, `obj`, `res`); abbreviations that
aren't standard (`cfg`, `cnt`, `msg_q`). Standard ones are fine: `url`, `id`, `json`, `csv`, `ffmpeg`.

### Shell scripts
- Variables: `UPPER_SNAKE_CASE`, full words (`RECORDING_DIR`, `STREAM_URL`, `CHANNEL_ARG`).
- Every script starts with `#!/usr/bin/env bash`, a comment saying what it does and how to call
  it, then `cd "$(dirname "$0")/.."` (scripts in `scripts/`) so it works from any folder.

### Settings (config.txt)
- Keys are `UPPER_SNAKE_CASE`. Python reads them only through `clipwatcher/settings.py`, where
  each one gets a descriptive Python name with a unit suffix (`LENGTH` -> `CLIP_LENGTH_S`).
- New settings: add them to `settings.py` **and** `config.example.txt`.

### Names stored on disk: never rename
These are read back from users' servers, so renaming breaks existing data:
- `config.txt` keys (`CHANNELS`, `MIN`, `LENGTH`, `TAGS`, `RES`, ...)
- queue item keys in `clips/queue/*.json` (`clip`, `final`, `hook`, `score`, `created_ts`, `meta`, `posted_to`, ...)
- `clips/scoreboard.csv` columns, `clips/auto.json` keys, `meta.json` / `token.json` formats
- clip names: `<platform>_<channel>_<YYYYmmdd_HHMMSS>`

Add new keys instead. Inside Python, map them to good names (e.g. queue key `meta` is called
`stream_info` in code).

## 2. Structure

- **Where code goes:** pick the stage first. Capture (chat, spikes, recording, cutting) ->
  `clipwatcher/capture/`. Making the video (whisper, captions, hook, memes, ffmpeg effects) ->
  `clipwatcher/render/`. Text, uploads, schedule, cleanup -> `clipwatcher/publish/`.
  Shared across stages -> `clipwatcher/` top level. See `AGENTS.md` for the file map.
- **Paths:** only from `clipwatcher/paths.py` (`paths.QUEUE_DIR`), never hand-built relative paths.
- **Settings:** only from `clipwatcher/settings.py` (`settings.OUTPUT_RESOLUTION`), never
  `os.environ` elsewhere.
- **Logging:** `from clipwatcher.log import log`; no bare `print` except in CLI output.
- **Imports:** absolute (`from clipwatcher.render.hook import make_hook`). Heavy or optional
  packages (`whisper`, `torch`, `googleapiclient`, `websocket`, `requests`, `chat_downloader`)
  are imported **inside** the function that needs them, so every module imports without them.
- **Entry points:** manual tasks are commands in `clipwatcher/__main__.py`
  (`python3 -m clipwatcher <command>`). Long-running processes are modules with `main()`
  started by `scripts/`. No new top-level scripts in the repo root.
- **One job per module.** If a module grows past ~300 lines or does two jobs, split it.

## 3. Code style

- Python 3.9+, standard library first; new dependencies go in `requirements.txt` with a comment.
- Every module starts with a docstring: what it does, and how to run it if runnable.
- Every public function gets a one-line docstring when its name doesn't say everything
  (return value, units, side effects).
- Keep functions pure where possible (see `spike_detector.py`, `subtitles.py`, `post_text.py`) so
  they can be tested without ffmpeg or network.
- Never commit secrets: `config.txt`, `client_secret*.json`, `token.json`, `meta.json` are git-ignored.

## 4. Tests

- Run all: `python3 -m unittest discover -s tests -t .` (needs no extra packages; the ffmpeg
  test is skipped if ffmpeg is missing).
- Tests that touch files use `tests.helpers.TempRepoTestCase`, which points `paths` at a temp folder.
- Add or update a test with every behaviour change. Never call real upload APIs in tests.

## 5. Docs

- Behaviour or setting changed -> update `README.md` (user view), `config.example.txt`
  (settings) and `AGENTS.md` (map), in the same commit.
- Commit messages: imperative summary of the user-visible change (`Add Kick chat reconnect backoff`).
