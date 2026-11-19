# Instagram + Facebook Reels auto-upload (one-time setup, free)

One Meta app posts every clip as an **Instagram Reel** and a **Facebook Page Reel**.

1. On Instagram, switch your clipping account to **Professional (Creator or Business)**.
2. Create a **Facebook Page** for the clipping page and link the Instagram account to it
   (Page settings → Linked accounts → Instagram).
3. Go to https://developers.facebook.com/apps, then **Create app** → type **Business**. Add the
   products **Facebook Login for Business** and **Instagram** (Instagram API with Facebook Login).
4. In **App settings → Basic**, copy the **App ID** and **App secret**.
5. Open the [Graph API Explorer](https://developers.facebook.com/tools/explorer/), select your app,
   and add the permissions `pages_show_list, pages_read_engagement, pages_manage_posts,
   instagram_basic, instagram_content_publish, business_management`. Click **Generate Access
   Token** and approve it.
6. Run `python3 -m clipwatcher meta-setup`, paste the App ID, App secret and token, and pick your
   Page. It saves `meta.json` with a long-lived Page token, so you don't need to log in again.
7. Put `instagram,facebook` in `UPLOAD` in `config.txt` (e.g. `UPLOAD='youtube,instagram,facebook'`).

The app can stay in **development mode**: it may post to accounts that you own and have a role
on in the app, so no app review is needed for your own pages. Test with
`python3 -m clipwatcher meta-test clips/ready/<clip>.mp4`.

**TikTok / X:** their APIs need paid plans or app approval, so take the file from `clips/ready/`
and the text from the matching `.txt`. Syncing `clips/ready/` to Google Drive (`CW_RCLONE_DEST`)
lets you post from your phone in seconds.
