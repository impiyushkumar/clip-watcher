# YouTube Shorts auto-upload (one-time setup, free)

1. Go to https://console.cloud.google.com/, create a project, and enable **YouTube Data API v3**.
2. Go to **APIs & Services → OAuth consent screen**: choose External, fill in the app name and
   your email, and add yourself under **Test users**.
3. Go to **Credentials → Create credentials → OAuth client ID → Desktop app**, download the JSON
   and save it in the repo root as `client_secret.json`.
4. Run `python3 -m clipwatcher youtube-login` (or just start `start.sh`) and log in to the channel
   the clips should go to. `token.json` is saved, and every clip after that uploads automatically.
5. Put `youtube` in `UPLOAD` in `config.txt`.

**Important:** Google locks uploads from new, unaudited API projects to **private**. Until your
project passes Google's free [API audit](https://support.google.com/youtube/contact/yt_api_form),
the clips upload as private and you switch them to public in YouTube Studio (one tap on the phone
app). The free quota allows about 6 uploads a day, so keep `youtube=6` or lower in `POSTS_PER_DAY`.

On a server, see [server.md](server.md) step 3 for logging in through an SSH tunnel.

## Tracking what works
```bash
python3 -m clipwatcher stats
```
This fills views, likes and comments into `clips/scoreboard.csv` and prints your top 3 clips.
The scheduler does this automatically twice a day when `AUTO_LEARN=1`.
