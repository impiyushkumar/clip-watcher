#!/usr/bin/env python3
"""Instagram Reels + Facebook Page Reels uploader (official Meta Graph API, free).

One-time setup (see README 'Instagram + Facebook auto-upload'):
    python meta_uploader.py --setup
Test an upload:
    python meta_uploader.py --test clips/ready/<clip>.mp4
"""
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "meta.json")
API = "v21.0"
GRAPH = f"https://graph.facebook.com/{API}"


def _cfg():
    if not os.path.exists(CFG):
        raise RuntimeError("meta.json missing - run: python meta_uploader.py --setup")
    return json.load(open(CFG))


def _check(r):
    try:
        data = r.json()
    except ValueError:
        r.raise_for_status()
        raise
    if r.status_code >= 400 or "error" in data:
        raise RuntimeError(data.get("error", {}).get("message", r.text))
    return data


def _rupload(url, token, path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        r = requests.post(url, data=f, timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
    return _check(r)


def upload_instagram(path, caption):
    c = _cfg()
    tok, ig = c["page_token"], c["ig_user_id"]
    cont = _check(requests.post(f"{GRAPH}/{ig}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200],
        "share_to_feed": "true", "access_token": tok}, timeout=60))
    _rupload(f"https://rupload.facebook.com/ig-api-upload/{API}/{cont['id']}", tok, path)
    for _ in range(60):  # Instagram processes the video before it can be published
        st = _check(requests.get(f"{GRAPH}/{cont['id']}", params={
            "fields": "status_code,status", "access_token": tok}, timeout=30))
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing failed: {st.get('status')}")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram processing timed out")
    media = _check(requests.post(f"{GRAPH}/{ig}/media_publish", data={
        "creation_id": cont["id"], "access_token": tok}, timeout=60))
    link = _check(requests.get(f"{GRAPH}/{media['id']}", params={
        "fields": "permalink", "access_token": tok}, timeout=30))
    return link.get("permalink", f"instagram media {media['id']}")


def upload_facebook(path, caption):
    c = _cfg()
    tok, page = c["page_token"], c["page_id"]
    start = _check(requests.post(f"{GRAPH}/{page}/video_reels", data={
        "upload_phase": "start", "access_token": tok}, timeout=60))
    vid = start["video_id"]
    _rupload(f"https://rupload.facebook.com/video-upload/{API}/{vid}", tok, path)
    _check(requests.post(f"{GRAPH}/{page}/video_reels", data={
        "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
        "description": caption[:5000], "access_token": tok}, timeout=60))
    return f"https://www.facebook.com/reel/{vid}"


def setup():
    print(__doc__)
    print("You need: Meta app ID + app secret, and a short-lived user token from the\n"
          "Graph API Explorer with these permissions:\n"
          "  pages_show_list, pages_read_engagement, pages_manage_posts,\n"
          "  instagram_basic, instagram_content_publish, business_management\n")
    app_id = input("App ID: ").strip()
    secret = input("App secret: ").strip()
    short = input("User token from Graph API Explorer: ").strip()
    long_user = _check(requests.get(f"{GRAPH}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id,
        "client_secret": secret, "fb_exchange_token": short}, timeout=30))["access_token"]
    pages = _check(requests.get(f"{GRAPH}/me/accounts", params={
        "access_token": long_user, "fields": "id,name,access_token"}, timeout=30))["data"]
    if not pages:
        sys.exit("No Facebook Pages found for this account - create a Page first.")
    for i, p in enumerate(pages, 1):
        print(f"  {i}. {p['name']} ({p['id']})")
    p = pages[int(input("Which Page should clips go to? [1]: ") or 1) - 1]
    ig = _check(requests.get(f"{GRAPH}/{p['id']}", params={
        "fields": "instagram_business_account{id,username}",
        "access_token": p["access_token"]}, timeout=30)).get("instagram_business_account")
    cfg = {"page_id": p["id"], "page_name": p["name"], "page_token": p["access_token"],
           "ig_user_id": ig["id"] if ig else "", "ig_username": ig.get("username", "") if ig else ""}
    with open(CFG, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(CFG, 0o600)
    print(f"\nSaved meta.json. Facebook Page: {p['name']}")
    if ig:
        print(f"Instagram: @{cfg['ig_username']}")
    else:
        print("No Instagram Business/Creator account is linked to this Page - "
              "Instagram upload will not work until you link one (Page settings > Linked accounts).")


if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup()
    elif "--test" in sys.argv:
        f = sys.argv[sys.argv.index("--test") + 1]
        cap = "clip-watcher test upload"
        print("Instagram:", upload_instagram(f, cap))
        print("Facebook:", upload_facebook(f, cap))
    else:
        print(__doc__)
