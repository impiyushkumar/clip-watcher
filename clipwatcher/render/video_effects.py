"""ffmpeg passes that change the picture.

edit_video(): ONE encode that trims the raw clip to the chosen window and adds
    colour boost + sharpen -> zoom punch (eased) + camera shake + white flash on the peak
    -> animated emoji pop-up on the peak -> hook box + captions + source credit.
insert_meme(): cut to a meme for MEME_SECONDS, then back to the clip.
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


def peak_effects_filter(onset_s, width, height):
    """Colour, zoom punch, shake and flash around onset_s (seconds into the final clip)."""
    filters = []
    if settings.COLOR_BOOST:
        filters.append("eq=saturation=1.18:contrast=1.06,unsharp=5:5:0.5")
    if onset_s is not None and (settings.ZOOM_PUNCH or settings.SHAKE):
        zoom_end_s = onset_s + ZOOM_DURATION_S
        shake_end_s = onset_s + SHAKE_DURATION_S
        in_zoom = f"between(in_time,{onset_s:.2f},{zoom_end_s:.2f})"
        in_shake = f"between(in_time,{onset_s:.2f},{shake_end_s:.2f})"
        if settings.ZOOM_PUNCH:
            zoom = f"if({in_zoom},{ZOOM_PEAK}-{ZOOM_PEAK - 1:.2f}*(in_time-{onset_s:.2f})/{ZOOM_DURATION_S},1)"
        else:
            zoom = f"if({in_shake},1.05,1)"  # a little zoom gives the shake room to move
        shake_x = f"if({in_shake},sin(in_time*95)*iw*{SHAKE_STRENGTH},0)" if settings.SHAKE else "0"
        shake_y = f"if({in_shake},cos(in_time*80)*ih*{SHAKE_STRENGTH},0)" if settings.SHAKE else "0"
        filters.append(f"zoompan=z='{zoom}':d=1:x='iw/2-(iw/zoom/2)+{shake_x}':"
                       f"y='ih/2-(ih/zoom/2)+{shake_y}':s={width}x{height}:fps={FPS}")
    if onset_s is not None and settings.FLASH:
        filters.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.55:t=fill:"
                       f"enable='between(t,{onset_s:.2f},{onset_s + FLASH_DURATION_S:.2f})'")
    return filters


EMOJI_SHOW_S = 1.8          # how long the emoji stays up after the peak
EMOJI_SIZE_SHARE = 0.24     # of the frame width


def emoji_position(width, height, seam_y):
    """Top-left corner for the emoji: just under the seam on the right (split layout),
    otherwise upper right under the hook."""
    size = int(width * EMOJI_SIZE_SHARE)
    if seam_y:
        return width - size - int(width * 0.05), seam_y + int(height * 0.05)
    return width - size - int(width * 0.06), int(height * 0.24)


def edit_video(raw_path, output_path, start_s, length_s, chunks, hook, emphasis="",
               seam_y=None, peak_s=None, onset_s=None, emoji_file=None, credit=""):
    """Trim [start_s, start_s + length_s] of raw_path and apply effects, the emoji pop-up and
    text. Times in chunks, peak_s and onset_s are relative to the trimmed clip. Returns success."""
    output_dir = os.path.dirname(os.path.abspath(output_path))
    ass_path = os.path.join(output_dir, ".style.ass")
    width, height = settings.output_size()
    write_ass(ass_path, chunks, hook, width, height, emphasis=emphasis, seam_y=seam_y, peak_s=peak_s,
              credit=credit)
    base_filters = peak_effects_filter(onset_s, width, height) or ["null"]
    # the subtitles filter is given a relative name, so ffmpeg runs inside output_dir
    subtitles = f"subtitles=.style.ass:fontsdir='{paths.FONTS_DIR}'"
    inputs = ["-ss", f"{start_s:.2f}", "-t", f"{length_s:.2f}", "-i", os.path.abspath(raw_path)]
    if emoji_file and onset_s is not None:
        emoji_size = even(width * EMOJI_SIZE_SHARE)
        emoji_x, emoji_y = emoji_position(width, height, seam_y)
        show_until_s = min(length_s, onset_s + EMOJI_SHOW_S)
        inputs += ["-stream_loop", "-1", "-c:v", "libvpx-vp9", "-i", os.path.abspath(emoji_file)]
        graph = (f"[0:v]{','.join(base_filters)}[base];"
                 f"[1:v]scale={emoji_size}:-1,format=yuva420p,setpts=PTS-STARTPTS+{onset_s:.2f}/TB[emoji];"
                 f"[base][emoji]overlay={emoji_x}:{emoji_y}:eof_action=pass:"
                 f"enable='between(t,{onset_s:.2f},{show_until_s:.2f})',{subtitles}[video]")
    else:
        graph = f"[0:v]{','.join(base_filters + [subtitles])}[video]"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
               "-filter_complex", graph, "-map", "[video]", "-map", "0:a?", "-t", f"{length_s:.2f}",
               "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
               "-threads", settings.FFMPEG_THREADS, "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", os.path.basename(output_path)]
    succeeded = subprocess.run(command, cwd=output_dir).returncode == 0
    os.remove(ass_path)
    return succeeded


def even(value):
    return int(value) // 2 * 2


def has_audio(media_path):
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                            "stream=index", "-of", "csv=p=0", media_path],
                           capture_output=True, text=True)
    return probe.stdout.strip() != ""


def insert_meme(video_path, meme_name, at_s, output_path):
    """Cut to the meme for up to MEME_SECONDS at `at_s`, then back to the clip. Returns success."""
    width, height = settings.output_size()
    meme_s = settings.MEME_SECONDS
    meme_path = os.path.join(paths.MEMES_DIR, meme_name)
    normalize = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={FPS},setsar=1,format=yuv420p"
    meme_audio = (f"[1:a]atrim=0:{meme_s},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[ma];"
                  if has_audio(meme_path) else f"anullsrc=r=48000:cl=stereo,atrim=0:{meme_s}[ma];")
    filter_graph = (
        f"[0:v]trim=0:{at_s},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v1];"
        f"[0:a]atrim=0:{at_s},asetpts=PTS-STARTPTS,aresample=48000[a1];"
        f"[1:v]trim=0:{meme_s},setpts=PTS-STARTPTS,{normalize}[mv];"
        + meme_audio
        + f"[0:v]trim=start={at_s},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[v2];"
        f"[0:a]atrim=start={at_s},asetpts=PTS-STARTPTS,aresample=48000[a2];"
        f"[a1]aformat=channel_layouts=stereo[a1s];[a2]aformat=channel_layouts=stereo[a2s];"
        f"[v1][a1s][mv][ma][v2][a2s]concat=n=3:v=1:a=1[v][a]")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video_path,
               "-stream_loop", "-1" if meme_name.lower().endswith(".gif") else "0", "-i", meme_path,
               "-filter_complex", filter_graph, "-map", "[v]", "-map", "[a]",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-threads", settings.FFMPEG_THREADS,
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", output_path]
    return subprocess.run(command).returncode == 0
