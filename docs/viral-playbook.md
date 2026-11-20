# Viral playbook: GTA 6 streamer clips

Researched with vidIQ on 2026-11-19 (GTA 6 launch week): breakout Shorts were found with
`vidiq_outliers`, and the top ones were watched frame by frame. This file is the "why";
the code applies it automatically. Keep it updated when the research changes.

## What's working right now (evidence)

| Clip | Result | What it does |
|---|---|---|
| N3on "accidently LEAKING GTA 6 early access" (RSCLIPS65, 22K subs) | **8.5M views in 3 days, 151× breakout** | 15 s, starts mid-sentence on the action, CONTEXT hook box "N3on REALLY MESSED UP after he LEAKED GTA VI early access LIVE ON STREAM", 1–2 word captions, no music, ends on the reaction and loops |
| "When you Finally Drive over a NPC in GTA 6 😭✌️" (350 subs) | **2,031× breakout** | 10 s, POV hook, gameplay + reaction meme, a scream lands exactly on the crash, instant loop |
| "POV: it's your first 10 seconds playing GTA6 😭💀" (xQc fan page) | 94K views in 1 day, 19× | 8 s, facecam on top / gameplay below, hook in the seam band, hard cut right after the punchline ("strip club where?") |
| "Peak GTA 6 NPC Moment😂" | 12.3K views/hour | red "PEAK GTA 6 NPC Moment" banner, "Source: TheBurntPeanut" credit, word-by-word captions, a wheeze-laugh SFX on the payoff |
| "Ranking the funniest ishowspeed moments" | 820K views, 24× | 60 s ranking compilation: 5 moments, #1 last, rank labels on the side |

**Why your old clips got 0 views** (vidIQ review of `mKuruU5uURQ`): 8 s of dead walking before
anything happened, gibberish transcript fragments as the hook and the title ("1 AND TIME 4 AND
AM AGO..."), blurred "fit" layout with the gameplay under 35% of the screen and a tiny facecam,
wrong captions, and no sound design.

## Meme-dense edits (the "hooky" style)
A reference edit the owner shared (a cooking vlog, 41 s) had **about 15 meme beats**: a cutaway
every 1–2 s, each one synced to a word or an action, escalating to the payoff:
- **match cuts:** juggling ingredients → clown juggling, hands on hips → lion in the same pose,
  holding up a board → soldier holding a shield
- **white text cards** for ~1 s: "I need help.", "who cares?", "Emotionally cooked", "nobody cares"
- **picture-in-picture stickers** and small labels ("Cooking Vlog", "UNDER PRESSURE")
- **reaction memes with their own audio** (screams, a disgusted face, an explosion) right after the line they react to
- VFX overlays (fire, smoke) on dramatic moments

clip-watcher turns this into a **beat sheet** (`render/beats.py`). Gemini **watches and
listens to the clip itself** (a small copy with sound), reads the word-timed transcript and the
**live chat** during the clip (chat tells it what viewers found funny), then plans beats across
the clip (sound, emoji, zoom, text_card, meme, sticker) from the full kit and the meme library.
**Nothing is placed by guessing:** every beat needs a reason plus evidence: the words spoken at
that moment, a chat message reacting to it, or the visible action. Quotes and chat lines are
checked against the transcript and chat at that time, and beats that fail are dropped. Every
clip gets `clips/ready/<clip>.edit.json`, which says what Gemini understood and why each beat
is there. Without a Gemini key there are no memes at all, only the peak zoom and sound.
Text cards are generated. Meme sounds (1,000+ from MyInstants) and reaction videos (starter
pack in `packs/reaction-memes.txt`) fill the private library: `import-sounds`, `import-memes`.

## The formula (all automated)

| # | Rule | Where in the code |
|---|---|---|
| 1 | **8–20 s** (default 15). Start ON the action, hard-cut ~2.5 s after the peak so it loops | `LENGTH`, `AFTER_PEAK`, `render/moment_finder.py` |
| 2 | The peak is the loudest reaction in the audio, not the chat spike (chat lags 3–10 s) | `moment_finder.find_peak_s` |
| 3 | **Split layout**: streamer's face big on top, gameplay below | `LAYOUT=split`, `capture/facecam.py` (Gemini finds the webcam) |
| 4 | **Hook box** = context, not a quote. CONTEXT / POV / PEAK formats, names streamer + "GTA 6", one red word | `render/copywriting.py` |
| 5 | **Title** = streamer + what happened + "GTA 6" + 1–2 emojis (😭 💀 😳 ✌️) | `copywriting.py`, `publish/post_text.py` |
| 6 | **1–2 word captions**, bold, the words on the peak in yellow and bigger, swearing censored (monetization) | `render/subtitles.py` |
| 7 | **Hit the peak frame**: zoom punch + shake + white flash + a sound that fits + an animated emoji (always, even without Gemini) | `render/video_effects.py`, `pipeline.complete_beats` |
| 8 | **The sound must fit the moment** (punch for a hit, siren for cops, "mission failed" for a death). Gemini watches frames and picks from the whole kit | `assets/sound_kit/catalog.json`, `copywriting.build_prompt` |
| 9 | Beats across the whole clip (sounds, emojis, zooms, text cards, memes, stickers), each synced to a word or action | `render/beats.py`, `copywriting.build_prompt`, `pipeline.process_clip` |
| 10 | No background music: only memes, meme sounds and the stream audio (music can be turned on with `MUSIC_VOLUME`) | `MUSIC_VOLUME=0` |
| 11 | Loudness −14 LUFS (what Shorts/TikTok normalize to; quieter clips sound weak) | `LOUDNESS` |
| 12 | "SOURCE: TWITCH.TV/XQC" credit on screen (campaigns require it, and it builds trust) | `pipeline.source_credit` |
| 13 | Colour boost + sharpen (stream rips look flat on phones) | `COLOR_BOOST` |

## Timing rules from practitioner research (Nov 2026)
Mostly editor and vendor guides, not controlled studies, so treat them as strong defaults:
- **The first 2–3 s decide "viewed vs. swiped away"**, the main signal YouTube exposes for Shorts. → a justified beat early, plus an opening punch-in when nothing happens before 1.5 s (`pipeline.complete_beats`).
- **Something changes every 1.5–3 s** (cut, zoom, caption pop, sound, insert). → prompt pacing rule.
- **One sound per joke, with the sound's *peak* on the frame that carries the joke.** → `sound_design.sound_peak_offset_s` starts each sound early by its build-up.
- **It must work muted:** captions, the hook box and text cards carry the joke without sound.
- **Loop the ending** back into the start (hard cut ~2.5 s after the peak).

Sources: [YouTube Shorts editing guide](https://videoeditingtips.pro/youtube-video-editing-guide/youtube-shorts-editing-guide/), [funny SFX timing](https://dubbingai.io/articles/en/collection/funny-sfx-sound-effects-video-editing), [vidIQ: Shorts algorithm 2026](https://vidiq.com/blog/post/youtube-shorts-algorithm/), [Shorts algorithm in YouTube's words](https://outlierkit.com/resources/youtube-shorts-algorithm/), [editing effects for Shorts](https://clipcreator.ai/blog/video-editing-effects).

## Distribution

**Timing matters more than polish during a launch window.** GTA 6 just released: every big
streamer is playing it and search demand is at its peak. A clip posted 2 hours after the moment
beats a better one posted the next day.

- **Freshness ranking:** the scheduler multiplies chat score by `0.5^(age/6h)`; manual picks still go first. → `publish/scheduler.py`
- **Volume:** post as much as the APIs allow. YouTube's free quota is about 6 uploads a day, so ask Google for a quota increase (free form) once the channel has traction. Instagram and Facebook allow more (`POSTS_PER_DAY`).
- **Cross-post everything:** the same clip goes to YouTube Shorts, Instagram Reels and Facebook Reels (`UPLOAD`). TikTok has no free posting API; upload the `clips/ready/*.mp4` + `.txt` from your phone (or connect TikTok in vidIQ and post from there).
- **Posting hours:** `learner.py` learns your best hours from your own views after 8+ posts. Until then, US afternoon and evening (14:00–23:00 ET) is when most English gaming viewers scroll.
- **Hashtags:** YouTube shows the first 3: `#gta6 #gtavi #<streamer>`. Instagram gets 5. More looks spammy. → `post_text.MAX_HASHTAGS`
- **Hidden tags:** streamer name, "gta 6 funny moments", "gta 6 clips", "vice city" … → `post_text.search_phrases`
- **Language:** the video and audio language are set to English, which helps YouTube recommend it to the right viewers.
- **First comment:** a question to start replies ("Would you have done the same? 😭"), posted automatically after each YouTube upload. Needs one re-login: `python3 -m clipwatcher youtube-login`.
- **First hour by hand (biggest boost you can add):** reply to every comment in the first hour, and heart the good ones. Early engagement decides how far the algorithm pushes a Short.
- **Never** delete and re-upload a weak Short (it can hurt the channel). Post the next one instead.

### Who to clip (GTA 6 launch week)
Breakouts this week came from: **N3on, xQc, Clix, Kai Cenat, Adin Ross, Asmongold, TheBurntPeanut,
LosPollosTV, ohnePixel, IShowSpeed**. Start with streamers who are live on Twitch/Kick
(YouTube blocks cloud servers):
```
CHANNELS='xqc,kaicenat,kick:n3on,kick:adinross,clix'
```
Check that each streamer allows clipping, or join their clipping campaign (Whop Content Rewards etc.):
campaigns pay per verified view and each has rules (required tags, minimum length, credit).
Match `TAGS`, `LENGTH` and the source credit to the campaign.

### Copyright (the owner's call)
- **Streamer footage:** covered by the clipping-campaign agreements the owner signs. Always keep the credit.
- **Bundled kit** (`assets/`): CC0 sounds, CC BY emojis. Safe to publish with the repo.
- **Private library** (`sounds/sfx/`, `memes/`): third-party meme sounds and clips, downloaded by `import-sounds` / `import-memes`. Git-ignored so the public repo never republishes them. Using them in videos is the owner's decision. Short meme SFX are rarely claimed. Songs and long movie scenes are the usual Content ID triggers.

## What's still manual / next ideas
- **Ranking compilations** ("Ranking the funniest GTA 6 moments", 5 clips, #1 last): 820K-view format, not built yet.
- **A Gemini key is the single biggest quality jump:** without it, hooks and titles come from templates and the facecam must be set by hand (`FACECAMS`). Get a free key at https://aistudio.google.com/apikey.
- Replying to comments in the first hour (see above).
