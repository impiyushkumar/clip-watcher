"""Stage 3 - publish: caption text, uploads, posting schedule, disk cleanup.

    post_text.py   caption text + hashtags per platform (creator aliases, game tags)
    scoreboard.py  clips/scoreboard.csv: one row per clip (links, views)
    youtube.py     YouTube Shorts upload + view stats (OAuth, token.json)
    meta_graph.py  Instagram Reels + Facebook Page Reels (Graph API, meta.json)
    poster.py      post one clip to the given platforms now; which platforms are set up
    scheduler.py   long-running loop: each platform posts the best queued clip on its clock
    cleanup.py     delete posted/old clips, drop the weakest when the disk is full
"""
