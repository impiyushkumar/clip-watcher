# sounds/ (your private sound library)

    sounds/sfx/<group>/<name>.mp3   meme sounds, grouped like the kit: impact, fail, win, hype,
                                    danger, comedy, transition, money, reaction, quote
    sounds/sfx/catalog.json         title + "use when" per sound (Gemini reads it)
    sounds/music/                   background tracks; one random track per clip at MUSIC_VOLUME

Fill it with one command (1,000+ meme sounds from MyInstants: vine boom, bruh, fahhh,
airhorn, metal pipe, GTA wasted…), then Gemini sorts them into groups and describes them:

    python3 -m clipwatcher import-sounds --pages 40 --search "fahhh,bruh,metal pipe"
    python3 -m clipwatcher label-sounds          # re-run after adding a Gemini key

Your own files work too: drop them in `sounds/sfx/` named by what they are.
Everything here except this README is git-ignored. These are third-party sounds, so using
them is your call: popular songs get Content ID claims far more often than short meme SFX.
