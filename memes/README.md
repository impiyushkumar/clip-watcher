# memes/ (your reaction memes)

The beat sheet cuts to these (full-screen, letterboxed, with their own sound) or shows
them as a small picture-in-picture sticker, right where they fit the moment. Gemini reads
`catalog.json` to know what each meme is and when to use it.

Add memes with the importer: it trims to max 4 s, normalizes the video, and (with a Gemini
key) watches the clip and writes the "use when" description for you:

    python3 -m clipwatcher add-meme path/to/clip.mp4
    python3 -m clipwatcher add-meme <URL> --start 3.5 --end 6     # URLs need: pip install yt-dlp
    python3 -m clipwatcher add-meme clip.mp4 --name crying-guy --use-when "someone fails badly"
    python3 -m clipwatcher memes                                    # list what's in the library

A starter pack of ~30 popular reaction memes (vine boom stare, surprised Pikachu, coffin
dance, to be continued, GTA wasted, CJ "here we go again"…):

    python3 -m clipwatcher import-memes packs/reaction-memes.txt

YouTube blocks cloud servers, so run that on your own PC and copy `memes/` to the server, or
set `YTDLP_COOKIES` to a cookies.txt exported from your browser.

Everything in this folder except this README is git-ignored. These are third-party clips, so
using them is your call: short reaction memes are rarely claimed, but movie scenes and
songs can get a Short muted or claimed.
