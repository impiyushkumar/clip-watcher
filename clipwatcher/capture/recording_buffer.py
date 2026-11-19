"""The rolling recording buffer.

scripts/watch-channel.sh records the stream into rec/<platform>_<channel>_<time>/ as
10 s pieces (seg_000001.ts ...) plus list.csv ("file,start_s,end_s" in stream time).
Only the last BUFFER_MINUTES of pieces are kept, so disk use stays ~0.5 GB per channel.
"""
import os
import sys
import time

from clipwatcher import paths
from clipwatcher.log import log


def list_segments(recording_dir):
    """[(piece_path, start_s, end_s)] in stream time, oldest first (deleted pieces included)."""
    segments = []
    try:
        with open(os.path.join(recording_dir, "list.csv")) as segment_list:
            for line in segment_list:
                fields = line.strip().split(",")
                if len(fields) >= 3:
                    segments.append((os.path.join(recording_dir, fields[0]),
                                     float(fields[1]), float(fields[2])))
    except OSError:
        pass
    return segments


def wait_for_first_segment(recording_dir):
    """Block until the first piece exists. Returns the wall-clock time the recording
    started, which maps wall-clock spike times to stream time."""
    log(f"waiting for recording {recording_dir}/ ...")
    while not list_segments(recording_dir):
        if os.path.exists(paths.stream_ended_marker(recording_dir)):
            log("no stream recorded - stopping")  # streamlink gave up before any video
            sys.exit(0)
        time.sleep(0.5)
    _piece, start_s, end_s = list_segments(recording_dir)[0]
    recording_start_ts = time.time() - (end_s - start_s)  # first piece just finished
    log("recording started")
    return recording_start_ts


def delete_old_segments_forever(recording_dir, keep_s):
    """Background loop: delete pieces older than keep_s seconds."""
    while True:
        time.sleep(30)
        segments = list_segments(recording_dir)
        if not segments:
            continue
        newest_end_s = segments[-1][2]
        for piece_path, _start_s, end_s in segments:
            if end_s < newest_end_s - keep_s and os.path.exists(piece_path):
                try:
                    os.remove(piece_path)
                except OSError:
                    pass
