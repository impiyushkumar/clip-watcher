"""Stage 1 - capture: read chat, detect spikes, cut raw 9:16 clips from the rolling buffer.

    chat.py             Twitch / YouTube / Kick chat readers (no login)
    spike_detector.py   10 s buckets vs 3-min median -> "this is a hype moment"
    recording_buffer.py the rolling 10 s stream pieces watch-channel.sh writes
    clip_cutter.py      ffmpeg: buffer pieces -> clips/raw/<name>.mp4
    channel_watcher.py  entry point for one channel; ties the above together
"""
