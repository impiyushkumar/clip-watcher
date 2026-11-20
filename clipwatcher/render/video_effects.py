"""ffmpeg passes that change the picture.

edit_video(): ONE encode that trims the raw clip to the chosen window and adds
    colour boost + sharpen -> zoom punch + shake + flash at every zoom beat -> animated
    emojis and meme stickers at their beats -> hook box + captions + source credit.
insert_cutaway(): cut away to a meme (letterboxed, own audio) or a text card for its
    duration, then back to the clip.
"""
import os
import subprocess

from clipwatcher import paths, settings
from clipwatcher.render.subtitles import write_ass

ZOOM_PEAK = 1.18             # zoom at the moment of impact, eases back to 1.0
ZOOM_DURATION_S = 0.7
SHAKE_DURATION_S = 0.35
SHAKE_STRENGTH = 0.012       # share of the frame width
FLASH_DURATION_S = 0.07
FPS = 30
EMOJI_SIZE_SHARE = 0.24      # of the frame width
STICKER_SIZE_SHARE = 0.46


def even(value):
    return int(value) // 2 * 2


def any_window(times_s, duration_s, variable):
    """ffmpeg expression: 1 while `variable` is inside any [t, t + duration_s]."""
    return "+".join(f"between({variable},{time_s:.2f},{time_s + duration_s:.2f})" for time_s in times_s)


def effects_filter(zoom_times_s, width, height):
    """Colour boost, then zoom punch + shake + flash at every time in zoom_times_s."""
    filters = []
    if settings.COLOR_BOOST:
        filters.append("eq=saturation=1.18:contrast=1.06,unsharp=5:5:0.5")
    if zoom_times_s and (settings.ZOOM_PUNCH or settings.SHAKE):
        if settings.ZOOM_PUNCH:
            # eased punch: jumps to ZOOM_PEAK at each beat and slides back to 1.0
            zoom_terms = "+".join(
                f"between(in_time,{time_s:.2f},{time_s + ZOOM_DURATION_S:.2f})*"
                f"({ZOOM_PEAK - 1:.2f}-{ZOOM_PEAK - 1:.2f}*(in_time-{time_s:.2f})/{ZOOM_DURATION_S})"
                for time_s in zoom_times_s)
            zoom = f"1+max(0,{zoom_terms})"
        else:
            zoom = f"1+0.05*min(1,{any_window(zoom_times_s, SHAKE_DURATION_S, 'in_time')})"
        in_shake = f"min(1,{any_window(zoom_times_s, SHAKE_DURATION_S, 'in_time')})"
        shake_x = f"{in_shake}*sin(in_time*95)*iw*{SHAKE_STRENGTH}" if settings.SHAKE else "0"
        shake_y = f"{in_shake}*cos(in_time*80)*ih*{SHAKE_STRENGTH}" if settings.SHAKE else "0"
        filters.append(f"zoompan=z='{zoom}':d=1:x='iw/2-(iw/zoom/2)+{shake_x}':"
                       f"y='ih/2-(ih/zoom/2)+{shake_y}':s={width}x{height}:fps={FPS}")
    if zoom_times_s and settings.FLASH:
        filters.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.55:t=fill:"
                       f"enable='{any_window(zoom_times_s, FLASH_DURATION_S, 't')}'")
    return filters


KEY_SIMILARITY = {"black": "0.12:0.06", "color": "0.22:0.08"}   # chromakey similarity:blend


def key_filter(key_color):
    """ffmpeg filter that removes a flat background colour (green screen or black)."""
    similarity = KEY_SIMILARITY["black"] if key_color == "0x000000" or int(key_color, 16) < 0x202020 \
        else KEY_SIMILARITY["color"]
    return f"chromakey={key_color}:{similarity}"


def overlay_box(kind, index, width, height, seam_y):
    """(size, x, y) for the index-th overlay; emojis alternate sides so they don't stack.
    "keyed" = a green-screen meme over the gameplay: full width, standing on the bottom edge."""
    if kind == "keyed":
        return width, 0, None
    if kind == "sticker":
        size = even(width * STICKER_SIZE_SHARE)
        x = (width - size) // 2
        y = (seam_y or int(height * 0.3)) + int(height * 0.04)
        return size, x, y
    size = even(width * EMOJI_SIZE_SHARE)
    right = index % 2 == 0
    x = width - size - int(width * 0.05) if right else int(width * 0.05)
    y = (seam_y + int(height * 0.05)) if seam_y else int(height * 0.24)
    return size, x, y


def edit_video(raw_path, output_path, start_s, length_s, chunks, hook, emphasis="", seam_y=None,
               peak_s=None, zoom_times_s=(), overlays=(), credit="", hold_end_s=0.0):
    """Trim [start_s, start_s + length_s] of raw_path and apply effects, overlays and text.
    overlays: [(kind "emoji"|"sticker"|"keyed", file path, at_s, duration_s[, key_color])]. All times are relative
    to the trimmed clip. Returns success."""
    output_dir = os.path.dirname(os.path.abspath(output_path))
    ass_path = os.path.join(output_dir, ".style.ass")
    width, height = settings.output_size()
    write_ass(ass_path, chunks, hook, width, height, emphasis=emphasis, seam_y=seam_y, peak_s=peak_s,
              credit=credit)
    # the subtitles filter is given a relative name, so ffmpeg runs inside output_dir
    subtitles = f"subtitles=.style.ass:fontsdir='{paths.FONTS_DIR}'"
    inputs = ["-ss", f"{start_s:.2f}", "-t", f"{length_s:.2f}", "-i", os.path.abspath(raw_path)]
    hold_end_s = max(0.0, hold_end_s)
    hold = [f"tpad=stop_mode=clone:stop_duration={hold_end_s:.2f}"] if hold_end_s > 0.05 else []
    output_length_s = length_s + (hold_end_s if hold else 0.0)
    graph = [f"[0:v]{','.join((effects_filter(list(zoom_times_s), width, height) or ['null']) + hold)}[layer0]",
             f"[0:a]apad=pad_dur={hold_end_s:.2f}[audio]" if hold else "[0:a]anull[audio]"]
    counts = {"emoji": 0, "sticker": 0, "keyed": 0}
    for input_index, overlay in enumerate(overlays, start=1):
        kind, file_path, at_s, duration_s = overlay[:4]
        key_color = overlay[4] if len(overlay) > 4 else None
        size, x, y = overlay_box(kind, counts[kind], width, height, seam_y)
        counts[kind] += 1
        decoder = ["-c:v", "libvpx-vp9"] if file_path.endswith(".webm") else []  # keeps emoji transparency
        inputs += ["-stream_loop", "-1", *decoder, "-i", os.path.abspath(file_path)]
        prepare = f"format=yuva420p,{key_filter(key_color)}," if kind == "keyed" and key_color else ""
        border = ",pad=iw+12:ih+12:6:6:white" if kind == "sticker" else ""
        graph.append(f"[{input_index}:v]{prepare}scale={size}:-2,format=yuva420p{border},"
                     f"setpts=PTS-STARTPTS+{at_s:.2f}/TB[overlay{input_index}]")
        until_s = min(output_length_s, at_s + duration_s)
        position_y = y if y is not None else "main_h-overlay_h"
        graph.append(f"[layer{input_index - 1}][overlay{input_index}]overlay={x}:{position_y}:eof_action=pass:"
                     f"enable='between(t,{at_s:.2f},{until_s:.2f})'[layer{input_index}]")
    graph.append(f"[layer{len(overlays)}]{subtitles}[video]")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
               "-filter_complex", ";".join(graph), "-map", "[video]", "-map", "[audio]", "-t", f"{output_length_s:.2f}",
               "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
               "-threads", settings.FFMPEG_THREADS, "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", os.path.basename(output_path)]
    succeeded = subprocess.run(command, cwd=output_dir).returncode == 0
    os.remove(ass_path)
    return succeeded


def has_audio(media_path):
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                            "stream=index", "-of", "csv=p=0", media_path],
                           capture_output=True, text=True, errors="replace")
    return probe.stdout.strip() != ""


def insert_cutaway(video_path, cutaway_path, at_s, duration_s, output_path):
    """Play `cutaway_path` (meme or text card) for duration_s at `at_s`, then continue the
    clip. Memes are letterboxed (black bars, nothing cropped). Returns success."""
    width, height = settings.output_size()
    letterbox = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                 f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={FPS},setsar=1,format=yuv420p")
    cutaway_audio = (f"[1:a]atrim=0:{duration_s},asetpts=PTS-STARTPTS,aresample=48000,"
                     f"aformat=channel_layouts=stereo,apad,atrim=0:{duration_s}[ca];"
                     if has_audio(cutaway_path) else f"anullsrc=r=48000:cl=stereo,atrim=0:{duration_s}[ca];")
    graph = (
        f"[0:v]trim=0:{at_s},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v1];"
        f"[0:a]atrim=0:{at_s},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a1];"
        f"[1:v]trim=0:{duration_s},setpts=PTS-STARTPTS,{letterbox}[cv];"
        + cutaway_audio
        + f"[0:v]trim=start={at_s},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v2];"
        f"[0:a]atrim=start={at_s},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a2];"
        f"[v1][a1][cv][ca][v2][a2]concat=n=3:v=1:a=1[v][a]")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video_path,
               "-stream_loop", "-1" if cutaway_path.lower().endswith(".gif") else "0", "-i", cutaway_path,
               "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-threads", settings.FFMPEG_THREADS,
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", output_path]
    return subprocess.run(command).returncode == 0
