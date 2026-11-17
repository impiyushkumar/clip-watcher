# clip-watcher

Records a live Twitch stream, watches chat for hype spikes, and turns each spike into a vertical 9:16 clip with Whisper subtitles.

## One-click start
| OS | Double-click |
|---|---|
| macOS | `start.command` |
| Linux | `clip-watcher.desktop` (or `start.sh`) |
| Windows | `start.bat` (needs WSL: `wsl --install`) |

On the first run it installs everything (ffmpeg, plus a `.venv` with `streamlink` and `openai-whisper`), asks for the channel name, and saves it to `config.txt`. After that, double-clicking starts it straight away. To change the channel, edit or delete `config.txt`.

## Command line
```bash
./install.sh
./watch.sh <twitch_channel> [--min 10] [--factor 2.5] [--model base]
```

## How it works
1. `streamlink` records the stream to `rec/<channel>_<time>.ts`. If the channel is offline it waits and retries.
2. Chat is read anonymously over IRC (`irc.chat.twitch.tv:6667`, nick `justinfanNNNNN`, no token needed).
3. Messages are counted in 10 s buckets. A bucket is a **spike** when it has at least `2.5 × median(last 3 min)` messages **and** at least `--min` messages. Detection starts after 1 minute of baseline.
4. For each spike, ffmpeg cuts **20 s before and 10 s after** the spike into `clips/`, center-cropped to 9:16 at 1080×1920.
5. Whisper writes `clips/<clip>.srt` next to each clip.

Ctrl+C stops everything. Set `CW_DEBUG=1` to print every bucket's count.

Note: chat usually runs a few seconds behind the video, so the 20 s pre-roll covers the moment people are reacting to.
