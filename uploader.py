#!/usr/bin/env python3
"""YouTube Shorts uploader (free YouTube Data API).

One-time setup: put your Google OAuth file as client_secret.json in this folder
(see README), then run:  python uploader.py --login
Update views/likes in scoreboard.csv:  python uploader.py --stats
"""
import csv
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SECRET = os.path.join(HERE, "client_secret.json")
TOKEN = os.path.join(HERE, "token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def service(interactive=False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES) if os.path.exists(TOKEN) else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not interactive:
            raise RuntimeError("not logged in - run: python uploader.py --login")
        if not os.path.exists(SECRET):
            raise RuntimeError(f"missing {SECRET} - see README 'YouTube auto-upload'")
        from google_auth_oauthlib.flow import InstalledAppFlow
        headless = sys.platform.startswith("linux") and not os.environ.get("DISPLAY")
        if headless:
            print("Server mode: on your PC run  gcloud compute ssh <vm> -- -L 8765:localhost:8765")
            print("then open the link below in your PC's browser.")
        creds = InstalledAppFlow.from_client_secrets_file(SECRET, SCOPES).run_local_server(
            port=8765, open_browser=not headless)
    with open(TOKEN, "w") as f:
        f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(path, title, description, tags, privacy="public"):
    from googleapiclient.http import MediaFileUpload
    yt = service()
    body = {
        "snippet": {"title": title[:100], "description": description[:4900],
                    "tags": [t.lstrip("#") for t in tags.split() if t.startswith("#")][:15],
                    "categoryId": "20"},  # Gaming
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(path, chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return f"https://youtube.com/shorts/{resp['id']}"


def update_stats(scoreboard=os.path.join(HERE, "clips", "scoreboard.csv")):
    rows = list(csv.DictReader(open(scoreboard, encoding="utf-8")))
    if not rows:
        print("no posts in scoreboard yet")
        return
    ids = {r["youtube_url"].rsplit("/", 1)[-1]: r for r in rows if r.get("youtube_url")}
    yt = service()
    keys = list(ids)
    for i in range(0, len(keys), 50):
        resp = yt.videos().list(part="statistics", id=",".join(keys[i:i + 50])).execute()
        for it in resp.get("items", []):
            s, r = it["statistics"], ids[it["id"]]
            r["views"], r["likes"] = s.get("viewCount", ""), s.get("likeCount", "")
            r["comments"] = s.get("commentCount", "")
            r["stats_updated"] = time.strftime("%Y-%m-%d %H:%M")
    with open(scoreboard, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    best = sorted(rows, key=lambda r: int(r.get("views") or 0), reverse=True)[:3]
    print("Top clips:")
    for r in best:
        print(f"  {r.get('views') or 0:>8} views  {r['hook']}  {r['youtube_url']}")


if __name__ == "__main__":
    if "--login" in sys.argv:
        service(interactive=True)
        print("Logged in to YouTube. token.json saved - uploads are now automatic.")
    elif "--stats" in sys.argv:
        update_stats()
    else:
        print(__doc__)
