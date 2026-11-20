"""Caption timing and the styled subtitle file. Pure text logic (no ffmpeg), easy to test.

A "chunk" is (start_s, end_s, TEXT): CAPTION_WORDS words shown on screen together.

Look (matches viral streamer clips):
  * hook   = black text in a white box; split layout: on the seam between facecam and
             gameplay; otherwise near the top. One emphasised word in red.
  * captions = 1-2 big white words with a thick black outline that pop in, over the
             gameplay; the words on the peak are yellow and bigger.
"""
import re
import textwrap

from clipwatcher import settings

CHUNK_BREAK_CHARS = ".?!,"
MIN_WORD_PROBABILITY = 0.35        # Whisper's confidence; below this the word is usually wrong
# ASS colours are &HAABBGGRR
WHITE, BLACK, YELLOW, RED = "&H00FFFFFF", "&H00000000", "&H0000E5FF", "&H002020E8"
PEAK_HIGHLIGHT_S = 0.7             # captions this close to the peak are highlighted
CENSORED = {"fuck": "f*ck", "fucking": "f*cking", "shit": "sh*t", "bitch": "b*tch",
            "nigga": "n***a", "nigger": "n****r"}


def censor(text):
    def replace(match):
        word = match.group(0)
        clean = CENSORED.get(word.lower())
        return clean.upper() if clean and word.isupper() else (clean or word)
    return re.sub(r"[A-Za-z]+", replace, text)


def confident_words(transcript):
    words = []
    for segment in transcript.get("segments", []):
        for word in segment.get("words", []):
            if word.get("probability", 1.0) >= MIN_WORD_PROBABILITY:
                words.append(word)
    return words


def group_words(transcript, max_words, max_chars):
    """Split confident Whisper words into groups of up to max_words / max_chars,
    breaking after punctuation."""
    groups, current = [], []
    for word in confident_words(transcript):
        current.append(word)
        text = "".join(item["word"] for item in current).strip()
        if len(current) >= max_words or len(text) >= max_chars or text[-1:] in CHUNK_BREAK_CHARS:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def caption_chunks(transcript, max_words=None, max_chars=14):
    """Chunks for the burned-in captions: [(start_s, end_s, "UPPER TEXT")]."""
    max_words = max_words or settings.CAPTION_WORDS
    chunks = []
    for group in group_words(transcript, max_words, max_chars):
        text = censor("".join(word["word"] for word in group).strip().upper().strip(",."))
        if text:
            chunks.append((group[0]["start"], group[-1]["end"], text))
    return chunks


def srt_time(seconds):
    milliseconds = int(round(seconds * 1000))
    return (f"{milliseconds // 3600000:02}:{milliseconds // 60000 % 60:02}:"
            f"{milliseconds // 1000 % 60:02},{milliseconds % 1000:03}")


def write_srt(transcript, srt_path, max_words=3, max_chars=18):
    """Write a plain .srt next to the clip (for platforms that take caption files)."""
    groups = group_words(transcript, max_words, max_chars)
    with open(srt_path, "w", encoding="utf-8") as srt_file:
        for number, group in enumerate(groups, 1):
            text = censor("".join(word["word"] for word in group).strip())
            srt_file.write(f"{number}\n{srt_time(group[0]['start'])} --> {srt_time(group[-1]['end'])}\n{text}\n\n")
    return len(groups)


def ass_time(seconds):
    centiseconds = int(round(max(0.0, seconds) * 100))
    return (f"{centiseconds // 360000}:{centiseconds // 6000 % 60:02}:"
            f"{centiseconds // 100 % 60:02}.{centiseconds % 100:02}")


def hook_markup(hook, emphasis, max_line_chars=18):
    """Wrapped hook lines (max 3) with the emphasised word in red."""
    lines = textwrap.wrap(hook, max_line_chars)[:3]
    marked = []
    for line in lines:
        words = [f"{{\\c{RED}&}}{word}{{\\c{BLACK}&}}" if emphasis and word.strip("!?.,") == emphasis else word
                 for word in line.split(" ")]
        marked.append(" ".join(words))
    return "\\N".join(marked)


def write_ass(ass_path, chunks, hook, width=1080, height=1920, emphasis="", seam_y=None, peak_s=None,
              credit=""):
    """Write the styled .ass file. seam_y = y of the facecam/gameplay seam (split layout);
    credit = small "SOURCE: ..." label (clipping campaigns usually require one)."""
    font = settings.FONT_NAME
    scale = width / 1080
    if seam_y:
        hook_position = f"\\an5\\pos({width // 2},{seam_y})"
        caption_y = seam_y + int((height - seam_y) * 0.58)
    else:
        hook_position = f"\\an8\\pos({width // 2},{int(170 * scale)})"
        caption_y = int(height * 0.68)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,{font},{int(86 * scale)},{BLACK},{BLACK},{WHITE},&H70000000,0,0,0,0,100,100,1,0,3,{int(20 * scale)},0,5,40,40,0,1
Style: Cap,{font},{int(124 * scale)},{WHITE},{WHITE},{BLACK},&H90000000,0,0,0,0,100,100,2,0,1,{int(10 * scale)},{int(4 * scale)},5,40,40,0,1
Style: Credit,{font},{int(34 * scale)},{WHITE},{WHITE},{BLACK},&H80000000,0,0,0,0,100,100,1,0,1,{int(3 * scale)},0,7,30,30,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    if settings.SHOW_HOOK and hook:
        events.append(f"Dialogue: 2,0:00:00.00,9:00:00.00,Hook,,0,0,0,,"
                      f"{{{hook_position}\\fad(120,0)}}{hook_markup(hook, emphasis)}")
    if credit:
        credit_y = int(height * 0.012)  # top-left corner, clear of the hook box
        events.append(f"Dialogue: 0,0:00:00.00,9:00:00.00,Credit,,0,0,0,,"
                      f"{{\\an7\\pos({int(width * 0.03)},{credit_y})}}{credit}")
    for start_s, end_s, text in chunks:
        on_peak = peak_s is not None and start_s - PEAK_HIGHLIGHT_S <= peak_s <= end_s + PEAK_HIGHLIGHT_S
        colour, size = (YELLOW, 118) if on_peak else (WHITE, 100)
        pop_in = (f"{{\\an5\\pos({width // 2},{caption_y})\\c{colour}&\\fscx72\\fscy72"
                  f"\\t(0,80,\\fscx{size + 10}\\fscy{size + 10})\\t(80,150,\\fscx{size}\\fscy{size})}}")
        events.append(f"Dialogue: 1,{ass_time(start_s)},{ass_time(max(end_s, start_s + 0.3))},"
                      f"Cap,,0,0,0,,{pop_in}{text}")
    with open(ass_path, "w", encoding="utf-8") as ass_file:
        ass_file.write(header + "\n".join(events) + "\n")
