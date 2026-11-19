# AGENTS.md: map of the repo for AI agents

Read this first. It tells you what the project does, where every piece lives, and how to
check your change. Naming and structure rules are in **[CONVENTIONS.md](CONVENTIONS.md)**;
follow them.

## What it does
clip-watcher records a live **Twitch / YouTube / Kick** stream, watches chat for hype spikes,
and turns each spike into a vertical Short (captions, hook text, meme cutaway) that it posts
to **YouTube Shorts / Instagram Reels / Facebook Reels** on a schedule. It also learns from
view counts which clip length, posting hours and hook style work best.

## Data flow
```
scripts/run.sh  (one per machine; systemd runs it on servers)
 ├─ publish/scheduler.py ........ posts queued clips on each platform's clock, cleans disk, relearns
 └─ for each channel: scripts/watch-channel.sh <channel>
       ├─ streamlink | ffmpeg  -> rec/<platform>_<channel>_<time>/seg_*.ts + list.csv  (rolling buffer)
       └─ capture/channel_watcher.py
            chat.py -> spike_detector.py -> clip_cutter.py  -> clips/raw/<clip>.mp4
            render/pipeline.py: transcriber -> subtitles + hook -> video_effects (+ memes)
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
| `clipwatcher/gemini.py` | Optional Gemini JSON calls (retries, backup models). Returns None without a key. |
| `clipwatcher/learner.py` | Self-learning from `clips/scoreboard.csv` -> `clips/auto.json` + `clips/learning.md`. |
| `clipwatcher/rerender.py` | Rebuild queued clips in the current style. |
| **`clipwatcher/capture/`** | **Stage 1**: chat + recording -> raw clips. |
| `capture/channel_watcher.py` | Entry point for one channel: wires chat, detector, cutter, render worker; exits when the stream ends and clips are done. |
| `capture/chat.py` | Anonymous chat readers: Twitch IRC, YouTube (chat-downloader), Kick (Pusher websocket). |
| `capture/spike_detector.py` | `SpikeDetector`: 10 s buckets vs 3-min median. Pure logic. |
| `capture/recording_buffer.py` | Reads `list.csv` of the rolling buffer, waits for the first piece, deletes old pieces. |
| `capture/clip_cutter.py` | ffmpeg cut + 9:16 crop/fit -> `clips/raw/`. |
| **`clipwatcher/render/`** | **Stage 2**: raw clip -> finished Short. |
| `render/pipeline.py` | `ClipJob` + `process_clip()`: runs every render step, writes the queue item (format documented there). |
| `render/transcriber.py` | Whisper with word timestamps. |
| `render/subtitles.py` | Word chunks, `.srt`, styled `.ass` (hook + pop-in captions). Pure logic. |
| `render/hook.py` | Hook text: Gemini, else first words of transcript, else fallback. |
| `render/memes.py` | Picks a meme from `memes/` (Gemini or keyword match). |
| `render/video_effects.py` | ffmpeg: burn subtitles + zoom punch; splice meme in. |
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
| `assets/fonts/` | Bundled Anton font (OFL). |
| `memes/` | User-supplied reaction memes (named by what they show). |
| `docs/` | User guides: `setup-youtube.md`, `setup-meta.md`, `server.md`. |
| `tests/` | `unittest` suite, incl. a real ffmpeg end-to-end test. |

Runtime data (git-ignored, created by the code): `rec/` (rolling buffers), `clips/raw/`,
`clips/ready/`, `clips/queue/` (+ `posted/`, `expired/`), `clips/scoreboard.csv`,
`clips/auto.json`, `clips/learning.md`. Secrets (git-ignored): `config.txt`,
`client_secret.json`, `token.json`, `meta.json`.

## Common tasks: where to look
| I want to... | Edit |
|---|---|
| change when a spike counts | `capture/spike_detector.py` (+ `MIN`/`FACTOR` in settings) |
| add a streaming platform | `capture/chat.py` (`CHAT_READERS`) + URL mapping in `scripts/watch-channel.sh` |
| change caption look / fonts | `render/subtitles.py` (`write_ass`) |
| change the hook | `render/hook.py` |
| change crop/fit/zoom | `capture/clip_cutter.py` (`vertical_filter`), `render/video_effects.py` |
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
- YouTube blocks recording/chat from many cloud IPs; Twitch/Kick work on servers.
- Never call real upload APIs in tests; mock `post_clip` / the uploader functions.
