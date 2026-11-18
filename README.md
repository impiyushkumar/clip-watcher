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
