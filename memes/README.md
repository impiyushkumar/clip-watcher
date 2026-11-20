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

Everything in this folder except this README is git-ignored: your library stays private and
is not published with the repo. Only add clips you have the right to use. Copyrighted movie,
TV or music clips can get Shorts claimed, muted or removed, and campaigns reject those views.
Good sources: clips you film yourself, public-domain footage, and meme templates whose
creators allow reuse.
