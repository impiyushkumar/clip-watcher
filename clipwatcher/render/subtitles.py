"""Caption timing and subtitle files. Pure text logic (no ffmpeg) so it is easy to test.

A "chunk" is (start_s, end_s, TEXT): 1-3 words shown on screen together.
"""
import textwrap

from clipwatcher import settings

CHUNK_BREAK_CHARS = ".?!,"
YELLOW, WHITE = "&H0000F0FF&", "&H00FFFFFF&"  # ASS colours are &HBBGGRR&


def group_words(transcript, max_words, max_chars):
    """Split Whisper words into groups of up to max_words / max_chars, breaking after punctuation."""
    groups, current = [], []
    for segment in transcript.get("segments", []):
        for word in segment.get("words", []):
            current.append(word)
            text = "".join(item["word"] for item in current).strip()
            if len(current) >= max_words or len(text) >= max_chars or text[-1:] in CHUNK_BREAK_CHARS:
                groups.append(current)
                current = []
    if current:
        groups.append(current)
    return groups


def caption_chunks(transcript, max_words=3, max_chars=16):
    """Chunks for the burned-in captions: [(start_s, end_s, "UPPER TEXT")]."""
    return [(group[0]["start"], group[-1]["end"],
             "".join(word["word"] for word in group).strip().upper().rstrip(","))
            for group in group_words(transcript, max_words, max_chars)]


def srt_time(seconds):
    milliseconds = int(round(seconds * 1000))
    return (f"{milliseconds // 3600000:02}:{milliseconds // 60000 % 60:02}:"
            f"{milliseconds // 1000 % 60:02},{milliseconds % 1000:03}")


def write_srt(transcript, srt_path, max_words=3, max_chars=18):
    """Write a short-form .srt (1-3 words per line) next to the clip. Returns the line count."""
    groups = group_words(transcript, max_words, max_chars)
    with open(srt_path, "w", encoding="utf-8") as srt_file:
        for number, group in enumerate(groups, 1):
            text = "".join(word["word"] for word in group).strip().upper()
            srt_file.write(f"{number}\n{srt_time(group[0]['start'])} --> {srt_time(group[-1]['end'])}\n{text}\n\n")
    return len(groups)


def ass_time(seconds):
    centiseconds = int(round(seconds * 100))
    return (f"{centiseconds // 360000}:{centiseconds // 6000 % 60:02}:"
            f"{centiseconds // 100 % 60:02}.{centiseconds % 100:02}")


def write_ass(ass_path, chunks, hook, width=1080, height=1920):
    """Clip-page style: big hook at the top (no box), captions that pop in word by word,
    alternating white / yellow, thick black outline. Sizes are for a 1080x1920 canvas
    (PlayRes scales them to other sizes)."""
    font = settings.FONT_NAME
    hook_lines = "\\N".join(textwrap.wrap(hook, 16)[:3])
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,{font},104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,7,3,8,60,60,230,1
Style: Cap,{font},128,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,2,0,1,8,4,2,60,60,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    if settings.SHOW_HOOK:
        events.append(f"Dialogue: 1,0:00:00.00,9:00:00.00,Hook,,0,0,0,,{{\\fad(150,0)}}{hook_lines}")
    for index, (start_s, end_s, text) in enumerate(chunks):
        colour = YELLOW if index % 2 else WHITE
        pop_in = "{\\fscx70\\fscy70\\t(0,90,\\fscx108\\fscy108)\\t(90,160,\\fscx100\\fscy100)\\c" + colour + "}"
        events.append(f"Dialogue: 0,{ass_time(start_s)},{ass_time(max(end_s, start_s + 0.25))},"
                      f"Cap,,0,0,0,,{pop_in}{text}")
    with open(ass_path, "w", encoding="utf-8") as ass_file:
        ass_file.write(header + "\n".join(events) + "\n")
