"""Instagram Reels + Facebook Page Reels upload (official Meta Graph API, free).

One-time setup (docs/setup-meta.md):   python3 -m clipwatcher meta-setup
Test an upload:                         python3 -m clipwatcher meta-test clips/ready/<clip>.mp4
"""
import json
import os
import sys
import time

from clipwatcher import paths

GRAPH_API_VERSION = "v21.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
REQUIRED_PERMISSIONS = ("pages_show_list, pages_read_engagement, pages_manage_posts,\n"
                        "  instagram_basic, instagram_content_publish, business_management")


def is_configured():
    return os.path.exists(paths.META_CONFIG_FILE)


def load_meta_config():
    if not is_configured():
        raise RuntimeError("meta.json missing - run: python3 -m clipwatcher meta-setup")
    with open(paths.META_CONFIG_FILE) as config_file:
        return json.load(config_file)


def checked_json(response):
    """Response JSON, or raise with Meta's error message."""
    try:
        data = response.json()
    except ValueError:
        response.raise_for_status()
        raise
    if response.status_code >= 400 or "error" in data:
        raise RuntimeError(data.get("error", {}).get("message", response.text))
    return data


def resumable_upload(upload_url, access_token, video_path):
    import requests
    with open(video_path, "rb") as video_file:
        response = requests.post(upload_url, data=video_file, timeout=600, headers={
            "Authorization": f"OAuth {access_token}", "offset": "0",
            "file_size": str(os.path.getsize(video_path))})
    return checked_json(response)


def upload_instagram_reel(video_path, caption):
    """Upload, wait for Instagram's processing, publish. Returns the permalink."""
    import requests
    config = load_meta_config()
    access_token, instagram_user_id = config["page_token"], config["ig_user_id"]
    container = checked_json(requests.post(f"{GRAPH_URL}/{instagram_user_id}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200],
        "share_to_feed": "true", "access_token": access_token}, timeout=60))
    resumable_upload(f"https://rupload.facebook.com/ig-api-upload/{GRAPH_API_VERSION}/{container['id']}",
                     access_token, video_path)
    for _attempt in range(60):  # up to 10 minutes of processing
        status = checked_json(requests.get(f"{GRAPH_URL}/{container['id']}", params={
            "fields": "status_code,status", "access_token": access_token}, timeout=30))
        if status.get("status_code") == "FINISHED":
            break
        if status.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing failed: {status.get('status')}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram processing timed out")
    media = checked_json(requests.post(f"{GRAPH_URL}/{instagram_user_id}/media_publish", data={
        "creation_id": container["id"], "access_token": access_token}, timeout=60))
    link = checked_json(requests.get(f"{GRAPH_URL}/{media['id']}", params={
        "fields": "permalink", "access_token": access_token}, timeout=30))
    return link.get("permalink", f"instagram media {media['id']}")


def upload_facebook_reel(video_path, caption):
    """Upload and publish a Page Reel. Returns its URL."""
    import requests
    config = load_meta_config()
    access_token, page_id = config["page_token"], config["page_id"]
    start = checked_json(requests.post(f"{GRAPH_URL}/{page_id}/video_reels", data={
        "upload_phase": "start", "access_token": access_token}, timeout=60))
    video_id = start["video_id"]
    resumable_upload(f"https://rupload.facebook.com/video-upload/{GRAPH_API_VERSION}/{video_id}",
                     access_token, video_path)
    checked_json(requests.post(f"{GRAPH_URL}/{page_id}/video_reels", data={
        "upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED",
        "description": caption[:5000], "access_token": access_token}, timeout=60))
    return f"https://www.facebook.com/reel/{video_id}"


def interactive_setup():
    """Exchange a short-lived token for a long-lived Page token and save meta.json."""
    import requests
    print(__doc__)
    print("You need: Meta app ID + app secret, and a short-lived user token from the\n"
          f"Graph API Explorer with these permissions:\n  {REQUIRED_PERMISSIONS}\n")
    app_id = input("App ID: ").strip()
    app_secret = input("App secret: ").strip()
    short_lived_token = input("User token from Graph API Explorer: ").strip()
    long_lived_token = checked_json(requests.get(f"{GRAPH_URL}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id,
        "client_secret": app_secret, "fb_exchange_token": short_lived_token}, timeout=30))["access_token"]
    pages = checked_json(requests.get(f"{GRAPH_URL}/me/accounts", params={
        "access_token": long_lived_token, "fields": "id,name,access_token"}, timeout=30))["data"]
    if not pages:
        sys.exit("No Facebook Pages found for this account - create a Page first.")
    for number, page in enumerate(pages, 1):
        print(f"  {number}. {page['name']} ({page['id']})")
    page = pages[int(input("Which Page should clips go to? [1]: ") or 1) - 1]
    instagram_account = checked_json(requests.get(f"{GRAPH_URL}/{page['id']}", params={
        "fields": "instagram_business_account{id,username}",
        "access_token": page["access_token"]}, timeout=30)).get("instagram_business_account")
    config = {"page_id": page["id"], "page_name": page["name"], "page_token": page["access_token"],
              "ig_user_id": instagram_account["id"] if instagram_account else "",
              "ig_username": instagram_account.get("username", "") if instagram_account else ""}
    with open(paths.META_CONFIG_FILE, "w") as config_file:
        json.dump(config, config_file, indent=2)
    os.chmod(paths.META_CONFIG_FILE, 0o600)
    print(f"\nSaved meta.json. Facebook Page: {page['name']}")
    if instagram_account:
        print(f"Instagram: @{config['ig_username']}")
    else:
        print("No Instagram Business/Creator account is linked to this Page - "
              "Instagram upload will not work until you link one (Page settings > Linked accounts).")


def test_upload(video_path):
    caption = "clip-watcher test upload"
    print("Instagram:", upload_instagram_reel(video_path, caption))
    print("Facebook:", upload_facebook_reel(video_path, caption))
