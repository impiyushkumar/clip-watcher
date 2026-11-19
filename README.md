# clip-watcher

Records a live **Twitch, YouTube or Kick** stream, watches chat for hype spikes, and turns each
spike into a **post-ready vertical Short**: burned-in captions, a hook line on top, an optional
meme cutaway, a caption file with credit and hashtags, and **automatic posting** to YouTube
Shorts, Instagram Reels and Facebook Reels on your schedule. It learns from your view counts
which clip length, posting hours and hook style work best.

```
chat spike / you press Enter -> 9:16 clip -> Whisper captions + hook (+ meme)
   -> clips/ready/<clip>.mp4 + .txt caption -> queue -> YouTube / Instagram / Facebook
   -> clips/scoreboard.csv (links + views) -> self-learning
```

> Working on the code (human or AI)? Start with **[AGENTS.md](AGENTS.md)** (repo map) and
> **[CONVENTIONS.md](CONVENTIONS.md)** (naming and structure rules).

## One-click start
| OS | Double-click |
|---|---|
| macOS | `start.command` |
| Linux | `clip-watcher.desktop` (or `start.sh`) |
| Windows | `start.bat` (needs WSL: `wsl --install`) |

On the first run it installs everything, asks a few questions (channels, clip length, hashtags,
upload targets) and saves the answers to `config.txt`. After that, double-clicking starts it
straight away. Every setting is explained in **[config.example.txt](config.example.txt)**.

## Command line
```bash
./scripts/install.sh                     # once
./scripts/configure.sh                   # setup questions -> config.txt
./scripts/run.sh                         # watch every channel in CHANNELS + post on schedule
./scripts/watch-channel.sh <channel> [--min 10] [--length 30] [--upload youtube]   # one channel, by hand
```

| Platform | Channel argument | Chat source |
|---|---|---|
| Twitch | `xqc` or `twitch:xqc` | anonymous IRC (`justinfan`) |
| YouTube | `youtube:@handle`, `youtube:UC...` or `youtube:<live video URL>` | `chat-downloader` |
| Kick | `kick:name` | public Pusher websocket |

Manual tasks (run from the repo folder; on a server use `.venv/bin/python`):

| Command | Does |
|---|---|
| `python3 -m clipwatcher settings` | show every effective setting |
| `python3 -m clipwatcher targets` | show which upload platforms are set up |
| `python3 -m clipwatcher youtube-login` | one-time YouTube login |
| `python3 -m clipwatcher meta-setup` | one-time Instagram/Facebook setup |
| `python3 -m clipwatcher stats` | pull views into `clips/scoreboard.csv`, print top clips |
| `python3 -m clipwatcher learn` | relearn now, print `clips/learning.md` |
| `python3 -m clipwatcher post-now` | post the best queued clip everywhere, once |
| `python3 -m clipwatcher rerender` | re-render queued clips in the current style |
| `python3 -m clipwatcher build-kit` | rebuild the bundled sound + emoji kit |

## How it works
1. `streamlink` records the stream as 10 s pieces in `rec/`. Only the last `KEEP_MINUTES`
   (default 10) are kept, so a channel uses ~0.5 GB of disk. If the channel is offline it waits.
2. Chat is read without logging in and counted in 10 s buckets. A bucket is a **spike** when it
   has at least `FACTOR × median(last 3 min)` messages **and** at least `MIN` messages.
   **Press Enter** in the window to clip a moment yourself.
3. ffmpeg cuts the clip (`LENGTH`, default 30 s: 2/3 before the spike, 1/3 after) to 9:16.
4. Whisper transcribes it. Captions are burned in 1-3 words at a time; the hook goes on top.
   The result goes to `clips/ready/` with a `.srt` and a `.txt` caption.
5. The clip waits in `clips/queue/`. Each platform posts on its own clock (`POSTS_PER_DAY`), and
   always gets the best clip it hasn't posted yet (your Enter-key picks first, then the biggest spike).

## Setup guides
- [YouTube Shorts upload](docs/setup-youtube.md)
- [Instagram + Facebook Reels upload](docs/setup-meta.md)
- [Run 24/7 on a server](docs/server.md) (Google Cloud / any Ubuntu VPS, small-server tuning)
- **[Viral playbook](docs/viral-playbook.md): why clips go viral, distribution, who to clip, copyright**

## Watch several streamers at once
```
CHANNELS='kaicenat,ohnepixel,kick:n3on'
```
Each channel is watched in parallel and all clips go into one queue. A 2-CPU server handles about
3 channels. Restart after changing: `sudo systemctl restart clip-watcher`.

## Clip style (built from vidIQ research on viral GTA 6 clips, see [docs/viral-playbook.md](docs/viral-playbook.md))
- **Length and timing:** 15 s (`LENGTH`). The editor finds the loudest reaction in the audio, starts right on the action and hard-cuts 2.5 s after the peak so the clip loops.
- **Layout:** the streamer's facecam big on top, gameplay below (`LAYOUT=split`). Gemini finds the webcam automatically, or you set it with `FACECAMS`.
- **Hook box:** black text in a white box on the seam, with one word in red. It gives context ("N3ON REALLY MESSED UP AFTER HE LEAKED GTA 6 LIVE"), a POV, or "PEAK GTA 6 MOMENT", never transcript gibberish.
- **Captions:** 1–2 words at a time. The words on the peak are yellow and bigger, and swearing is censored.
- **On the peak:** zoom punch, camera shake, white flash, an animated emoji (😭 💀 😳…) and a sound that fits the moment.
- **Sound kit:** 443 CC0 sounds in `assets/sound_kit/`, grouped by when to use them: impact, fail ("mission failed", sad trombone), win, hype (airhorn, "fight!"), danger (siren), comedy (record scratch, sexy sax), transition and money. Add your own in `sounds/sfx/`, plus music in `sounds/music/` (ducked under the voice). Final loudness is −14 LUFS.
- **Gemini watches every clip** (frames + transcript) and picks the hook, title, peak sound, reaction sound, emoji, meme and a first comment from the whole kit. Add `GEMINI_API_KEY='...'` to `config.txt` (free at https://aistudio.google.com/apikey). It's the single biggest quality jump. Without it, clean templates are used. Never commit the key.
- **Beat sheet (meme-dense edits):** Gemini plans 4–10 beats across each clip, every one synced to a word or action: sound hits, emoji pops, zooms, white text cards ("nobody cares", "he's cooked"), reaction-meme cutaways and stickers.
- **Meme library:** `python3 -m clipwatcher add-meme <file or URL>` trims and normalizes a clip, and Gemini describes when to use it. The library stays private in `memes/` (see [memes/README.md](memes/README.md)).
- **Credit:** "SOURCE: TWITCH.TV/XQC" in the corner (clipping campaigns require one).
- **Re-render old clips** in the current style: `sudo systemctl stop clip-watcher && .venv/bin/python -m clipwatcher rerender && sudo systemctl start clip-watcher`
- **Rebuild the kit:** `python3 -m clipwatcher build-kit`

## Disk use
Raw cuts are deleted as soon as the finished clip is made. Every clip stays in the queue **until
it has been posted** (`MAX_AGE_H=0`). Finished clips are deleted once they're posted everywhere
and older than `KEEP_CLIP_DAYS` (default 2). If the disk goes above `DISK_LIMIT` (default 80%),
the **weakest** unposted clips are dropped. `clips/scoreboard.csv` keeps every post link.

## Self-learning (automatic)
With `AUTO_LEARN=1` (the default), twice a day it pulls views for every posted clip (YouTube API).
After 8+ posts are at least 24 h old it compares median views by **clip length**, **posting hour**
and **hook length**, then uses the best length, posts at your best hours, and keeps testing a
different length on about 1 in 5 streams. Read what it learned in `clips/learning.md`.

## Earning from clipping
Many streamers and brands **pay clippers per view** through clipping campaigns (e.g. Whop's
Content Rewards). Rates are usually around **$1 per 1,000 views** (often $0.20–$5), paid on
approved views while the budget lasts. Match `CHANNELS`, `TAGS` and `LENGTH` to the campaign's rules.

## Rules that keep the channel alive
- Clip **your own** stream, or creators who allow clipping. Always keep the credit line.
- Don't post leaks or fake "confirmed" news. Only use memes you have the right to post.

Ctrl+C stops everything. Set `CW_DEBUG=1` to print every bucket's count.
