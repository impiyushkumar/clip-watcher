"""Stage 2 - render: raw search-window clip -> post-ready Short in clips/ready/.

    moment_finder.py  loudest peak in the audio -> which LENGTH window to keep
    transcriber.py    Whisper speech-to-text with word timings (just that window)
    copywriting.py    Gemini watches frames and picks hook/title/sounds/emoji/meme/comment
    subtitles.py      1-2 word caption chunks, .srt and the styled .ass (hook box, credit)
    video_effects.py  ffmpeg: trim + colour + zoom/shake/flash + emoji + text; meme splice
    sound_design.py   sound menu (assets/sound_kit + sounds/), mix, ducked music, -14 LUFS
    emojis.py         assets/emoji/*.webm
    memes.py          memes/
    pipeline.py       process_clip(): runs all of the above, then queues or posts
"""
