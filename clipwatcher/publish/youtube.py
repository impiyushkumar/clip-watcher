"""YouTube Shorts upload and view stats (free YouTube Data API v3).

One-time setup: save your Google OAuth client as client_secret.json in the repo root
(docs/setup-youtube.md), then:  python3 -m clipwatcher youtube-login
"""
import os
import sys
import time

from clipwatcher import paths
from clipwatcher.publish import scoreboard

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
LOGIN_PORT = 8765
GAMING_CATEGORY_ID = "20"


def is_logged_in():
    return os.path.exists(paths.YOUTUBE_TOKEN_FILE)


def get_service(interactive=False):
    """Authorized YouTube API client. interactive=True opens the browser login if needed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = (Credentials.from_authorized_user_file(paths.YOUTUBE_TOKEN_FILE, SCOPES)
                   if is_logged_in() else None)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        if not interactive:
            raise RuntimeError("not logged in - run: python3 -m clipwatcher youtube-login")
        if not os.path.exists(paths.YOUTUBE_CLIENT_SECRET_FILE):
            raise RuntimeError(f"missing {paths.YOUTUBE_CLIENT_SECRET_FILE} - see docs/setup-youtube.md")
        from google_auth_oauthlib.flow import InstalledAppFlow
        headless = sys.platform.startswith("linux") and not os.environ.get("DISPLAY")
        if headless:
            print(f"Server mode: on your PC run  gcloud compute ssh <vm> -- -L {LOGIN_PORT}:localhost:{LOGIN_PORT}")
            print("then open the link below in your PC's browser.")
        flow = InstalledAppFlow.from_client_secrets_file(paths.YOUTUBE_CLIENT_SECRET_FILE, SCOPES)
        credentials = flow.run_local_server(port=LOGIN_PORT, open_browser=not headless)
    with open(paths.YOUTUBE_TOKEN_FILE, "w") as token_file:
        token_file.write(credentials.to_json())
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def upload_short(video_path, title, description, hashtags, privacy="public"):
    """Upload and return the Shorts URL."""
    from googleapiclient.http import MediaFileUpload
    youtube = get_service()
    body = {
        "snippet": {"title": title[:100], "description": description[:4900],
                    "tags": [tag.lstrip("#") for tag in hashtags.split() if tag.startswith("#")][:15],
                    "categoryId": GAMING_CATEGORY_ID},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    request = youtube.videos().insert(part="snippet,status", body=body,
                                      media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True))
    response = None
    while response is None:
        _status, response = request.next_chunk()
    return f"https://youtube.com/shorts/{response['id']}"


def refresh_stats(scoreboard_path=None):
    """Fill views/likes/comments into the scoreboard and print the top 3 clips."""
    rows = scoreboard.read_rows(scoreboard_path)
    if not rows:
        print("no posts in scoreboard yet")
        return
    rows_by_video_id = {row["youtube_url"].rsplit("/", 1)[-1]: row for row in rows if row.get("youtube_url")}
    youtube = get_service()
    video_ids = list(rows_by_video_id)
    for batch_start in range(0, len(video_ids), 50):  # API limit: 50 ids per call
        response = youtube.videos().list(part="statistics",
                                         id=",".join(video_ids[batch_start:batch_start + 50])).execute()
        for video in response.get("items", []):
            stats, row = video["statistics"], rows_by_video_id[video["id"]]
            row["views"], row["likes"] = stats.get("viewCount", ""), stats.get("likeCount", "")
            row["comments"] = stats.get("commentCount", "")
            row["stats_updated"] = time.strftime("%Y-%m-%d %H:%M")
    scoreboard.write_rows(rows, scoreboard_path)
    print("Top clips:")
    for row in sorted(rows, key=lambda row: int(row.get("views") or 0), reverse=True)[:3]:
        print(f"  {row.get('views') or 0:>8} views  {row['hook']}  {row['youtube_url']}")
