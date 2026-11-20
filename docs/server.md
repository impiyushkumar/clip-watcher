# Run 24/7 on a server (Google Cloud / any Ubuntu VPS)

1. Create the VM: in [Cloud Shell](https://shell.cloud.google.com) run
   ```bash
   gcloud compute instances create clip-watcher --zone=us-central1-a --machine-type=e2-standard-2 --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud --boot-disk-size=50GB --boot-disk-type=pd-balanced
   ```
2. SSH in with `gcloud compute ssh clip-watcher --zone=us-central1-a`, then:
   ```bash
   git clone https://github.com/impiyushkumar/clip-watcher && cd clip-watcher && ./scripts/setup-server.sh
   ```
   This installs everything (a CPU-only build, about 1.5 GB), asks the setup questions and
   installs a **systemd service**. The service starts on boot, waits for the stream, records,
   clips and uploads, and gets ready for the next stream when one ends.
3. YouTube upload on a server: copy `client_secret.json` to the VM
   (`gcloud compute scp client_secret.json clip-watcher:~/clip-watcher/ --zone=us-central1-a`),
   then connect with a tunnel and log in:
   ```bash
   gcloud compute ssh clip-watcher --zone=us-central1-a -- -L 8765:localhost:8765
   cd clip-watcher && .venv/bin/python -m clipwatcher youtube-login && sudo systemctl restart clip-watcher
   ```
   Open the printed link in your PC's browser.
4. Clips on your phone (optional): run `rclone config` to add Google Drive as `gdrive`, set
   `CW_RCLONE_DEST='gdrive:clip-watcher'` in `config.txt`, then `sudo systemctl restart clip-watcher`.

| Task | Command |
|---|---|
| Live log | `journalctl -u clip-watcher -f` |
| Change settings | `./scripts/configure.sh && sudo systemctl restart clip-watcher` (or edit `config.txt`) |
| See effective settings | `.venv/bin/python -m clipwatcher settings` |
| Stop / start | `sudo systemctl stop clip-watcher` / `start` |
| Update | `git pull && sudo systemctl restart clip-watcher` |
| Re-render queued clips | `sudo systemctl stop clip-watcher && .venv/bin/python -m clipwatcher rerender && sudo systemctl start clip-watcher` |
| Download clips | `gcloud compute scp --recurse clip-watcher:~/clip-watcher/clips/ready . --zone=us-central1-a` |

**Updating from the old layout:** older installs start `run.sh` in the repo root. That file is
kept as a shim, so `git pull` keeps working. Re-running `./scripts/setup-server.sh` points the
service at `scripts/run.sh` directly.

Note: YouTube often blocks *recording/chat* from cloud IPs, so on a server use Twitch or Kick
channels. Uploading to YouTube works everywhere.

## Small server (2 CPUs) with several live channels
A 2-CPU server handles about **3 channels**. Add to `config.txt`:
```
MODEL=tiny        # ~3x faster captions
RES=720x1280      # 720p sources don't need 1080p output
THREADS=1         # one CPU thread per job
FACTOR=3          # only bigger spikes
COOLDOWN=300      # at most one clip per channel every 5 min
```
Heavy jobs (cutting and captions) also run one at a time across all channels, so the server never chokes.
