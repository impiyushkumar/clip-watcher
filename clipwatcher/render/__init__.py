"""Stage 2 - render: raw clip -> post-ready Short in clips/ready/.

    transcriber.py    Whisper speech-to-text with word timings
    subtitles.py      words -> 1-3 word caption chunks, .srt and styled .ass files
    hook.py           the big text at the top (Gemini, or first words of the transcript)
    memes.py          choose a reaction meme from memes/
    video_effects.py  ffmpeg: burn captions + zoom punch, splice in the meme
    pipeline.py       process_clip(): runs all of the above, then queues or posts
"""
