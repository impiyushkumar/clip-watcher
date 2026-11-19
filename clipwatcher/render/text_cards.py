"""Meme text cards: a white full-screen card with short black text ("nobody cares",
"I need help.", "emotionally cooked") cut in for ~1 s. A staple of meme-dense edits:
original (no copyright issues) and Gemini writes them per clip."""
import hashlib
import os
import subprocess
import textwrap

from clipwatcher import paths, settings

CARD_FONTS = ("DejaVu Serif", "DejaVu Sans")   # bundled in assets/fonts/
FPS = 30


def card_font(text):
    """Stable per text, so re-renders look the same; mixes serif and sans cards."""
    return CARD_FONTS[int(hashlib.md5(text.encode()).hexdigest(), 16) % len(CARD_FONTS)]


def write_card_ass(ass_path, text, width, height, duration_s):
    scale = width / 1080
    lines = "\\N".join(textwrap.wrap(text, 14)[:4])
    with open(ass_path, "w", encoding="utf-8") as ass_file:
        ass_file.write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Card,{card_font(text)},{int(150 * scale)},&H00141414,&H00141414,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,1,0,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:{duration_s:05.2f},Card,,0,0,0,,{{\\fscx90\\fscy90\\t(0,90,\\fscx100\\fscy100)}}{lines}
""")


def make_text_card(text, output_path, duration_s, sound_path=None):
    """Render the card as an mp4 (with sound_path as its audio, or silence). Returns success."""
    width, height = settings.output_size()
    output_dir = os.path.dirname(os.path.abspath(output_path))
    ass_name = os.path.basename(output_path) + ".ass"
    write_card_ass(os.path.join(output_dir, ass_name), text, width, height, duration_s)
    audio_input = (["-i", os.path.abspath(sound_path)] if sound_path
                   else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"])
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", f"color=c=white:s={width}x{height}:r={FPS}:d={duration_s:.2f}",
               *audio_input, "-filter_complex",
               f"[0:v]subtitles={ass_name}:fontsdir='{paths.FONTS_DIR}',format=yuv420p[v];"
               f"[1:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{duration_s:.2f}[a]",
               "-map", "[v]", "-map", "[a]", "-t", f"{duration_s:.2f}",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
               os.path.basename(output_path)]
    result = subprocess.run(command, cwd=output_dir)
    os.remove(os.path.join(output_dir, ass_name))
    return result.returncode == 0
