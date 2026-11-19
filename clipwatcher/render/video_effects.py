"""ffmpeg steps that change the picture: burn captions/hook (+ zoom punch), splice in a meme."""
import os
import subprocess

from clipwatcher import paths, settings
from clipwatcher.render.subtitles import write_ass

ZOOM_FACTOR = 1.12
ZOOM_START_BEFORE_SPIKE_S = 0.3
ZOOM_END_AFTER_SPIKE_S = 1.4


def burn_captions(raw_path, hook, final_path, chunks, spike_at_s=None):
    """raw clip -> final clip with captions, hook and (if ZOOM) a quick zoom at spike_at_s."""
    output_dir = os.path.dirname(os.path.abspath(final_path))
    ass_path = os.path.join(output_dir, ".style.ass")
    width, height = settings.output_size()
    write_ass(ass_path, chunks, hook, width, height)
    video_filter = ""
    if spike_at_s is not None and settings.ZOOM_PUNCH:
        zoom_start_s = max(0, spike_at_s - ZOOM_START_BEFORE_SPIKE_S)
        zoom_end_s = spike_at_s + ZOOM_END_AFTER_SPIKE_S
        video_filter += (f"zoompan=z='if(between(in_time,{zoom_start_s:.2f},{zoom_end_s:.2f}),{ZOOM_FACTOR},1)':d=1:"
                         f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps=30,")
    # the subtitles filter is given a relative name, so ffmpeg runs inside output_dir
    video_filter += f"subtitles=.style.ass:fontsdir='{paths.FONTS_DIR}'"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-i", os.path.abspath(raw_path), "-vf", video_filter,
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-threads", settings.FFMPEG_THREADS,
               "-c:a", "copy", "-movflags", "+faststart", os.path.basename(final_path)]
    succeeded = subprocess.run(command, cwd=output_dir).returncode == 0
    os.remove(ass_path)
    return succeeded


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
    normalize = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=30,setsar=1,format=yuv420p"
    meme_audio = (f"[1:a]atrim=0:{meme_s},asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo[ma];"
                  if has_audio(meme_path) else f"anullsrc=r=44100:cl=stereo,atrim=0:{meme_s}[ma];")
    filter_graph = (
        f"[0:v]trim=0:{at_s},setpts=PTS-STARTPTS,fps=30,format=yuv420p[v1];"
        f"[0:a]atrim=0:{at_s},asetpts=PTS-STARTPTS,aresample=44100[a1];"
        f"[1:v]trim=0:{meme_s},setpts=PTS-STARTPTS,{normalize}[mv];"
        + meme_audio
        + f"[0:v]trim=start={at_s},setpts=PTS-STARTPTS,fps=30,format=yuv420p[v2];"
        f"[0:a]atrim=start={at_s},asetpts=PTS-STARTPTS,aresample=44100[a2];"
        f"[a1]aformat=channel_layouts=stereo[a1s];[a2]aformat=channel_layouts=stereo[a2s];"
        f"[v1][a1s][mv][ma][v2][a2s]concat=n=3:v=1:a=1[v][a]")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video_path,
               "-stream_loop", "-1" if meme_name.lower().endswith(".gif") else "0", "-i", meme_path,
               "-filter_complex", filter_graph, "-map", "[v]", "-map", "[a]",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-threads", settings.FFMPEG_THREADS,
               "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", output_path]
    return subprocess.run(command).returncode == 0
