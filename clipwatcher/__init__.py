"""clip-watcher: turn hype moments in live streams into posted vertical Shorts.

Pipeline (one folder per stage):
    capture/  record the stream, read chat, detect spikes, cut raw 9:16 clips
    render/   transcribe, burn captions + hook, meme cutaway -> clips/ready/
    publish/  caption text, upload to YouTube / Instagram / Facebook, schedule, clean up
See AGENTS.md at the repo root for the full map.
"""
