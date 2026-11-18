# clip-watcher

Records a live **Twitch, YouTube or Kick** stream, watches chat for hype spikes, and turns each spike into a **post-ready vertical Short**: burned-in captions, a hook line on top, a caption file with credit and hashtags, and (optionally) an **automatic upload to YouTube Shorts**.

```
chat spike / you press Enter -> 9:16 clip -> Whisper captions burned in + hook text
   -> clips/ready/<clip>.mp4 + .txt caption -> YouTube Shorts upload -> clips/scoreboard.csv
```

## One-click start
| OS | Double-click |
|---|---|
| macOS | `start.command` |
| Linux | `clip-watcher.desktop` (or `start.sh`) |
| Windows | `start.bat` (needs WSL: `wsl --install`) |

On the first run it installs everything, asks a few questions (channel, clip length, hashtags, YouTube auto-upload yes/no) and saves the answers to `config.txt`. After that, double-clicking starts it straight away. To change the channel, edit or delete `config.txt`.

## Command line
```bash
./install.sh
./watch.sh <channel> [--min 10] [--length 30] [--upload youtube,instagram,facebook] [--privacy public]
            [--tags "#gaming #shorts"] [--hook "wait for it..."] [--model base]
```

| Platform | Channel argument | Chat source |
|---|---|---|
| Twitch | `xqc` or `twitch:xqc` | anonymous IRC (`justinfan`) |
| YouTube | `youtube:@handle`, `youtube:UC...` or `youtube:<live video URL>` | `chat-downloader` |
| Kick | `kick:name` | public Pusher websocket |

## How it works
1. `streamlink` records the stream to `rec/<platform>_<channel>_<time>.ts`. If the channel is offline it waits and retries.
2. Chat is read without logging in: Twitch over IRC (`irc.chat.twitch.tv:6667`), YouTube via `chat-downloader`, Kick via its public websocket.
3. Messages are counted in 10 s buckets. A bucket is a **spike** when it has at least `2.5 × median(last 3 min)` messages **and** at least `--min` messages. Detection starts after 1 minute of baseline.
4. For each spike, ffmpeg cuts the clip (`--length`, default 30 s: 2/3 before the spike, 1/3 after), center-cropped to 9:16 at 1080×1920, into `clips/raw/`. **Press Enter** in the window to clip a moment yourself, which is useful when your chat is still small.
5. Whisper transcribes it. Captions are burned in 1–3 words at a time (big, white, outlined). The first words become the **hook** at the top. The result goes to `clips/ready/` with a `.srt` and a `.txt` caption (hook, `🎥 source` credit, hashtags).
6. It is auto-posted to every target in `--upload` (YouTube Shorts, Instagram Reels, Facebook Reels), and the links are logged in `clips/scoreboard.csv`.

## YouTube auto-upload (one-time setup, free)
1. Go to https://console.cloud.google.com/, create a project, and enable **YouTube Data API v3**.
2. Go to **APIs & Services → OAuth consent screen**: choose External, fill in the app name and your email, and add yourself under **Test users**.
3. Go to **Credentials → Create credentials → OAuth client ID → Desktop app**, download the JSON and save it in this folder as `client_secret.json`.
4. Run `python3 uploader.py --login` (or just start `start.sh`) and log in to the channel the clips should go to. `token.json` is saved, and every clip after that uploads automatically.

**Important:** Google locks uploads from new, unaudited API projects to **private**. Until your project passes Google's free [API audit](https://support.google.com/youtube/contact/yt_api_form), the clips upload as private and you switch them to public in YouTube Studio (one tap on the phone app). The quota allows about 6 uploads a day by default.

## Instagram + Facebook auto-upload (one-time setup, free)
One Meta app posts every clip as an **Instagram Reel** and a **Facebook Page Reel**.
1. On Instagram, switch your clipping account to **Professional (Creator or Business)**.
2. Create a **Facebook Page** for the clipping page and link the Instagram account to it (Page settings → Linked accounts → Instagram).
3. Go to https://developers.facebook.com/apps, then **Create app** → type **Business**. Add the products **Facebook Login for Business** and **Instagram** (Instagram API with Facebook Login).
4. In **App settings → Basic**, copy the **App ID** and **App secret**.
5. Open the [Graph API Explorer](https://developers.facebook.com/tools/explorer/), select your app, and add the permissions `pages_show_list, pages_read_engagement, pages_manage_posts, instagram_basic, instagram_content_publish, business_management`. Click **Generate Access Token** and approve it.
6. Run `python3 meta_uploader.py --setup`, paste the App ID, App secret and token, and pick your Page. It saves `meta.json` with a long-lived Page token, so you don't need to log in again.
7. Put `instagram,facebook` in `UPLOAD` in `config.txt` (e.g. `UPLOAD='youtube,instagram,facebook'`).

The app can stay in **development mode**: it may post to accounts that you own and have a role on in the app, so no app review is needed for your own pages. Test with `python3 meta_uploader.py --test clips/ready/<clip>.mp4`.

**TikTok / X:** their APIs need paid plans or app approval, so take the file from `clips/ready/` and the text from the matching `.txt`. Syncing `clips/ready/` to Google Drive or iCloud lets you post from your phone in seconds.

## Watch several streamers at once
In `config.txt`:
```
CHANNELS='kaicenat,ohnepixel,kick:n3on'
```
Each channel is watched in parallel: it waits for that streamer to go live, clips their hype moments, and starts waiting again when the stream ends. All clips go into one queue, and the scheduler posts the best ones. A 2-CPU server handles about **3 channels** comfortably. Restart after changing: `sudo systemctl restart clip-watcher`.

**Small server (2 CPUs) with several live channels:** add these to `config.txt` to keep it fast:
```
MODEL=tiny        # ~3x faster captions
RES=720x1280      # 720p sources don't need 1080p output
THREADS=1         # one CPU thread per job
FACTOR=3          # only bigger spikes
COOLDOWN=300      # at most one clip per channel every 5 min
```
**Sharper clips:** record at full quality and keep the whole frame:
```
QUALITY='best'    # 1080p60 source
RES=1080x1920
LAYOUT=fit        # whole 16:9 picture sharp in the middle + blurred background (crop = fill screen, cuts the sides)
```
Heavy jobs (cutting and captions) also run one at a time across all channels, so the server never chokes.

## Clip style
- **Format:** full-screen 9:16 at 1080×1920 (`LAYOUT=crop`, `RES=1080x1920`, `QUALITY='best'`).
- **Hook:** big **Anton** text at the top with a thick outline and no box. Anton is bundled in `fonts/` (SIL Open Font License); change it with `CW_FONT`.
- **Captions:** 1–3 words at a time that pop in, alternating white and yellow.
- **Zoom punch:** a quick zoom on the hype moment. Turn it off with `ZOOM=0`.
- **AI hooks (optional):** add `GEMINI_API_KEY='...'` to `config.txt` and Gemini writes a meme-style hook from what was said. It falls back to the transcript hook if the key is missing or the call fails. Keep the key only on your server; never commit it.

## Scheduled posting (per platform)
Set how many posts a day each platform gets in `config.txt`:
```
POSTS_PER_DAY='youtube=6,instagram=10,facebook=10'
```
- **Schedule:** finished clips wait in `clips/queue/`. Each platform posts on its own clock: YouTube every 4 h and Instagram/Facebook every 2.4 h in this example.
- **Choice:** each time a platform is due, it gets the best clip it hasn't posted yet (your Enter-key picks first, then the biggest chat spike).
- **Clean-up:** a clip leaves the queue once every platform has it. Clips older than 48 h are skipped.
- **Empty queue:** if there's nothing new (streamer offline), it simply waits.
- **YouTube limit:** about 6 uploads a day on the free API quota, so keep `youtube=6` or lower.

Post the best clip everywhere right now: `python3 poster.py --once --per-day "youtube=6,instagram=10,facebook=10"`

## Self-learning (automatic)
With `AUTO_LEARN=1` (the default), clip-watcher improves itself from your own results. No outside service or AI is involved:
- **Measuring:** twice a day it pulls views for every posted clip (YouTube API) into `clips/scoreboard.csv`.
- **Judging:** after 8+ posts are at least 24 h old, it compares median views by **clip length**, **posting hour** and **hook style**.
- **Adjusting:** it switches to the best clip length automatically and posts at your best-performing hours (waiting at most one extra interval for a good hour).
- **Exploring:** about 1 in 5 streams it tests a different length, so it keeps finding better settings as your audience changes.
- **Reporting:** you can read what it learned in `clips/learning.md`; the settings it applies are in `clips/auto.json`. Run `python3 learn.py` to relearn now.

## Earning from clipping
Many streamers and brands **pay clippers per view** through clipping campaigns, e.g. on Whop's Content Rewards marketplace. Rates are usually around **$1 per 1,000 views** (often $0.20–$5) and are paid only on approved, verified views while the campaign budget lasts. Each campaign has its own rules (which streams, hashtags, tags, length), so set `CHANNEL`, `TAGS` and `LENGTH` in `config.txt` to match the campaign you joined.

## Tracking what works
```bash
python3 uploader.py --stats
```
This fills views, likes and comments into `clips/scoreboard.csv` and prints your top 3 clips. Run it after 24 h and 72 h, keep the hook styles that win, and change one thing at a time.

## Rules that keep the channel alive
- Clip **your own** stream, or creators who allow clipping. Always keep the credit line.
- Don't post leaks or fake "confirmed" news.

Ctrl+C stops everything. Set `CW_DEBUG=1` to print every bucket's count.

Note: chat usually runs a few seconds behind the video, so the 20 s pre-roll covers the moment people are reacting to.

## Run 24/7 on a server (Google Cloud / any Ubuntu VPS)
1. Create the VM: in [Cloud Shell](https://shell.cloud.google.com) run
   ```bash
   gcloud compute instances create clip-watcher --zone=us-central1-a --machine-type=e2-standard-2 --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud --boot-disk-size=50GB --boot-disk-type=pd-balanced
   ```
2. SSH in with `gcloud compute ssh clip-watcher --zone=us-central1-a`, then:
   ```bash
   git clone https://github.com/impiyushkumar/clip-watcher && cd clip-watcher && ./setup-gcp.sh
   ```
   This installs everything (a CPU-only build, about 1.5 GB), asks the setup questions and installs a **systemd service**. The service starts on boot, waits for the stream, records, clips and uploads, and gets ready for the next stream when one ends.
3. YouTube upload on a server: copy `client_secret.json` to the VM (`gcloud compute scp client_secret.json clip-watcher:~/clip-watcher/ --zone=us-central1-a`), then connect with a tunnel and log in:
   ```bash
   gcloud compute ssh clip-watcher --zone=us-central1-a -- -L 8765:localhost:8765
   cd clip-watcher && .venv/bin/python uploader.py --login && sudo systemctl restart clip-watcher
   ```
   Open the printed link in your PC's browser.
4. Clips on your phone (optional): run `rclone config` to add Google Drive as `gdrive`, set `CW_RCLONE_DEST='gdrive:clip-watcher'` in `config.txt`, then `sudo systemctl restart clip-watcher`.

| Task | Command |
|---|---|
| Live log | `journalctl -u clip-watcher -f` |
| Change settings | `./configure.sh && sudo systemctl restart clip-watcher` |
| Stop / start | `sudo systemctl stop clip-watcher` / `start` |
| Download clips | `gcloud compute scp --recurse clip-watcher:~/clip-watcher/clips/ready . --zone=us-central1-a` |

Recordings older than 1 day are deleted automatically (`KEEP_REC_DAYS`). Note: YouTube often blocks *recording/chat* from cloud IPs, so on a server use Twitch or Kick channels. Uploading to YouTube works everywhere.
