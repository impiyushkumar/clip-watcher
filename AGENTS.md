# AGENTS.md: map of the repo for AI agents

Read this first. It tells you what the project does, where every piece lives, and how to
check your change. Naming and structure rules are in **[CONVENTIONS.md](CONVENTIONS.md)**;
follow them.

## What it does
clip-watcher records a live **Twitch / YouTube / Kick** stream (the channel focuses on
**GTA 6** streamer clips), watches chat for hype spikes, finds the real peak in the audio and
turns it into a 15 s vertical Short edited like viral clip pages: facecam-on-top split layout,
a context hook box, 1-2 word captions, zoom/shake/flash + a fitting sound + an animated emoji
on the peak. **Gemini watches each clip** and picks the hook, title, sounds, emoji and meme from
the bundled kit. It posts to **YouTube Shorts / Instagram Reels / Facebook Reels** on a
freshness-weighted schedule and learns from view counts.
**Why it's built this way:** [docs/viral-playbook.md](docs/viral-playbook.md) (vidIQ research on
what's going viral). Read it before changing anything creative.

## Data flow
```
scripts/run.sh  (one per machine; systemd runs it on servers)
 ├─ publish/scheduler.py ........ posts queued clips on each platform's clock, cleans disk, relearns
 └─ for each channel: scripts/watch-channel.sh <channel>
       ├─ streamlink | ffmpeg  -> rec/<platform>_<channel>_<time>/seg_*.ts + list.csv  (rolling buffer)
       └─ capture/channel_watcher.py
            chat.py -> spike_detector.py -> facecam.py + clip_cutter.py (31 s search window, split layout)
                -> clips/raw/<clip>.mp4
            render/pipeline.py: moment_finder (loudest peak -> 15 s window) -> transcriber
                -> copywriting (Gemini watches a frame grid, plans the BEAT SHEET from the kit)
                -> video_effects (trim, colour, zoom beats, emoji/sticker beats, hook, captions,
                credit) -> sound beats -> cutaways (text cards, memes; last first)
                -> sound_design (ducked music, -14 LUFS + loudness correction)
                -> clips/ready/<clip>.mp4/.srt/.txt
                -> clips/queue/<clip>.json   (or post immediately if no schedule)
```

## Where everything is
| Path | What it is |
|---|---|
| `start.sh`, `start.command`, `start.bat`, `clip-watcher.desktop` | Double-click launchers (Linux / macOS / Windows-WSL / Linux desktop). All call `start.sh` -> `scripts/run.sh`. |
| `run.sh` | Shim kept for old systemd units; just runs `scripts/run.sh`. |
| `config.example.txt` | **Every setting, documented.** Users' real settings live in `config.txt` (git-ignored). |
| `requirements.txt` | Python packages. |
| **`clipwatcher/`** | **All Python code** (one package). |
| `clipwatcher/__main__.py` | CLI for manual tasks: `python3 -m clipwatcher <command>` (settings, targets, youtube-login, stats, meta-setup, meta-test, learn, pick-length, post-now, rerender). |
| `clipwatcher/settings.py` | Reads every setting (env > config.txt > default). The only place that reads config/env. |
| `clipwatcher/paths.py` | Every file/folder path. The only place paths are defined. |
| `clipwatcher/log.py` | `log()`: timestamped stdout. |
| `clipwatcher/heavy_job.py` | File lock so only one CPU-heavy job runs at a time across all channels. |
| `clipwatcher/gemini.py` | Optional Gemini JSON calls (text + one image, retries, backup models). Returns None without a key. |
| `clipwatcher/media_kit.py` | Builds `assets/sound_kit/` + `assets/emoji/` (`python3 -m clipwatcher build-kit`). `CATEGORY_GUIDE` = folder + "use when" for every sound category. |
| `clipwatcher/library_import.py` | Fills the private library: `import-sounds` (MyInstants -> `sounds/sfx/<group>/`), `label-sounds` (Gemini groups + describes), `import-memes <pack>` (yt-dlp -> `memes/`). |
| `clipwatcher/learner.py` | Self-learning from `clips/scoreboard.csv` -> `clips/auto.json` + `clips/learning.md`. |
| `clipwatcher/rerender.py` | Rebuild queued clips in the current style. |
| **`clipwatcher/capture/`** | **Stage 1**: chat + recording -> raw clips. |
| `capture/channel_watcher.py` | Entry point for one channel: wires chat, detector, cutter, render worker; exits when the stream ends and clips are done. |
| `capture/chat.py` | Anonymous chat readers: Twitch IRC, YouTube (chat-downloader), Kick (Pusher websocket); yield (arrival time, text). The texts go to Gemini with each clip. |
| `capture/spike_detector.py` | `SpikeDetector`: 10 s buckets vs 3-min median. Pure logic. |
| `capture/recording_buffer.py` | Reads `list.csv` of the rolling buffer, waits for the first piece, deletes old pieces. |
| `capture/facecam.py` | Where the webcam is: `FACECAMS` setting > cache > Gemini looks at a frame. |
| `capture/clip_cutter.py` | ffmpeg cut of the search window + 9:16 layout (split / crop / fit) -> `clips/raw/`. |
| **`clipwatcher/render/`** | **Stage 2**: raw clip -> finished Short. |
| `render/pipeline.py` | `ClipJob` + `process_clip()`: runs every render step in order, writes the queue item (format documented there). |
| `render/moment_finder.py` | Loudness envelope -> peak + onset -> which `LENGTH` window to keep. Pure math + one ffmpeg call. |
| `render/transcriber.py` | Whisper on just the final window, with GTA/streamer vocabulary hints. |
| `render/copywriting.py` | `ClipCopy`: one Gemini call (the clip itself as a small video WITH sound + word-timed transcript + live chat + full sound/emoji/meme menus) -> summary, hook, emphasis, title, comment and the beat sheet with evidence. Template fallback (no memes) without a key. |
| `render/beats.py` | `Beat` (sound, emoji, zoom, text_card, meme, sticker) with reason + evidence (quote / chat / visual); `validate_beats` checks menus, times, limits, cutaway spacing and that quotes/chat really occur there; single-peak fallback. |
| `render/text_cards.py` | White meme text cards ("nobody cares") rendered as short clips with an optional sound. |
| `render/subtitles.py` | 1-2 word caption chunks (low-confidence words dropped, swearing censored), styled `.ass`: hook box on the seam, captions, credit. Pure logic. |
| `render/video_effects.py` | ffmpeg: one pass for trim + colour + zoom/shake/flash at every zoom beat + emoji/sticker overlays + subtitles; `insert_cutaway` splices a meme (letterboxed) or card. |
| `render/sound_design.py` | Sound menu (kit catalog + `sounds/sfx/`), resolves a category to a file, mixes sounds + ducked music + loudness. |
| `render/emojis.py` | Lists `assets/emoji/*.webm`; keyword fallback. |
| `render/memes.py` | Meme library: `memes/catalog.json` ("use when" per meme), `add_meme` importer (trim, normalize, Gemini describes it). |
| **`clipwatcher/publish/`** | **Stage 3**: getting clips posted. |
| `publish/post_text.py` | Caption text, hashtags per platform, creator aliases, game tags, YouTube title. |
| `publish/poster.py` | `post_clip()` to platforms now; `usable_targets()` = which platforms are set up. |
| `publish/scheduler.py` | Long-running posting loop (per-platform intervals, best clip first, good hours). |
| `publish/cleanup.py` | Deletes posted/old files; drops weakest unposted clips if disk > `DISK_LIMIT`. |
| `publish/scoreboard.py` | Read/write `clips/scoreboard.csv`. |
| `publish/youtube.py` | YouTube OAuth login, Shorts upload, view stats. |
| `publish/meta_graph.py` | Instagram + Facebook Reels via Meta Graph API; interactive setup. |
| **`scripts/`** | **Shell scripts.** |
| `scripts/install.sh` | ffmpeg + `.venv` + requirements (CPU-only torch without NVIDIA). |
| `scripts/configure.sh` | Setup questions -> `config.txt`. |
| `scripts/run.sh` | Starts the scheduler + one watch loop per channel, forever. |
| `scripts/watch-channel.sh` | Records one channel into the rolling buffer and runs `channel_watcher`. |
| `scripts/setup-server.sh` | Fresh Ubuntu server: install + systemd service `clip-watcher`. |
| `assets/fonts/` | Anton (hook/captions, OFL) + DejaVu Sans/Serif Bold (text cards, free license). |
| `assets/sound_kit/<group>/<category>/` | 443 CC0 sounds, grouped by WHEN to use them (impact, fail, win, hype, danger, comedy, transition, money). `catalog.json` = "use when" per category (what Gemini reads); `README.md` = same table. Generated: rebuild, don't hand-edit. |
| `assets/emoji/<name>.webm` | 141 animated Noto emojis (VP9 with transparency, CC BY 4.0). Generated. |
| `assets/CREDITS.md` | Sources and licenses of everything in `assets/`. |
| `sounds/sfx/<group>/`, `sounds/music/` | Private sound library (git-ignored): imported meme sounds + `catalog.json`, in Gemini's menu as `custom/<group>/<file>`; background music. |
| `packs/*.txt` | Meme packs: "search or URL \| name \| use when" lines for `import-memes`. |
| `memes/` | User's reaction meme library (git-ignored except README). Add with `python3 -m clipwatcher add-meme`. |
| `docs/` | `viral-playbook.md` (why everything is built this way), `setup-youtube.md`, `setup-meta.md`, `server.md`. |
| `tests/` | `unittest` suite, incl. a real ffmpeg end-to-end test. |

Runtime data (git-ignored, created by the code): `rec/` (rolling buffers), `clips/raw/`,
`clips/ready/`, `clips/queue/` (+ `posted/`, `expired/`), `clips/scoreboard.csv`,
`clips/auto.json`, `clips/learning.md`. Secrets (git-ignored): `config.txt`,
`client_secret.json`, `token.json`, `meta.json`.

## Common tasks: where to look
| I want to... | Edit |
|---|---|
| change when a spike counts | `capture/spike_detector.py` (+ `MIN`/`FACTOR` in settings) |
| change how the peak / clip window is chosen | `render/moment_finder.py` (+ `LENGTH`, `AFTER_PEAK`) |
| change what Gemini decides or the hook/title style | `render/copywriting.py` (`build_prompt`, fallbacks) + `docs/viral-playbook.md` |
| add or re-describe sounds | `media_kit.py` `CATEGORY_GUIDE` / `SYNTH_SOUNDS`, then `python3 -m clipwatcher build-kit sounds` |
| change the zoom/shake/flash/emoji pop | `render/video_effects.py` |
| add a new beat kind | `render/beats.py` (KINDS, limits) + `copywriting.build_prompt` + `pipeline.process_clip` |
| add a streaming platform | `capture/chat.py` (`CHAT_READERS`) + URL mapping in `scripts/watch-channel.sh` |
| change caption / hook box look | `render/subtitles.py` (`write_ass`) |
| change the layout (split/crop/fit) | `capture/clip_cutter.py` (`vertical_filter`), `capture/facecam.py` |
| change caption text or hashtags | `publish/post_text.py` |
| add an upload platform | new `publish/<platform>.py`, then `PLATFORMS` + `post_clip()` + `usable_targets()` in `publish/poster.py` |
| change posting schedule logic | `publish/scheduler.py` |
| add a setting | `clipwatcher/settings.py` + `config.example.txt` (+ `scripts/configure.sh` if it should be asked) |
| add a manual command | `clipwatcher/__main__.py` |

## Check your change
```bash
python3 -m unittest discover -s tests -t .      # all tests, ~5 s, no extra packages needed
python3 -m clipwatcher settings                  # effective settings
bash -n scripts/*.sh start.sh run.sh             # shell syntax
```
A real stream test needs the venv (`./scripts/install.sh`) and a live channel:
`./scripts/watch-channel.sh <channel>`, then press Enter to force a clip.

## Gotchas
- Scripts and the service run with the repo root as working directory; Python code still uses
  absolute paths from `paths.py`.
- `render/video_effects.burn_captions` runs ffmpeg **inside** the output folder because the
  `subtitles` filter gets a relative `.style.ass` name (avoids escaping problems).
- Queue items store `final` relative to the repo root; use `poster.resolve_path()` to open it.
- The raw cut is deleted after rendering, so `rerender` only works while the raw cut still exists.
- Gemini's choices are validated against the menus (invented names are dropped) and against the evidence (a beat whose quoted words or chat line don't occur at that time is dropped). Every clip writes `clips/ready/<clip>.edit.json` with the reasons.
- Emoji WebMs must be decoded with `-c:v libvpx-vp9` (set before `-i`), or the transparency is lost.
- Never add ripped meme audio or songs to the kit (Content ID claims). Kit sources must be CC0 / free licenses.
- YouTube blocks recording/chat from many cloud IPs; Twitch/Kick work on servers.
- Never call real upload APIs in tests; mock `post_clip` / the uploader functions.
