#!/usr/bin/env python3
"""clip-watcher: read Twitch chat anonymously, detect message spikes,
cut 9:16 clips from the live recording and transcribe them with Whisper."""
import argparse
import os
import queue
import random
import socket
import statistics
import subprocess
import sys
import threading
import time
from collections import deque

BUCKET = 10          # seconds per bucket
WINDOW = 18          # 3 min of history = 18 buckets
PRE, POST = 20, 10   # clip seconds before / after the spike


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def wait_for_recording(path):
    """Wait until streamlink has written data; that moment = t0 of the file."""
    log(f"waiting for recording {path} ...")
    while not (os.path.exists(path) and os.path.getsize(path) > 0):
        time.sleep(0.5)
    t0 = time.time()
    log("recording started")
    return t0


def cut_clip(rec, t0, spike_t, name, outdir, whisper_q):
    # wait until the POST seconds (+ a margin) exist in the recording
    time.sleep(max(0, spike_t + POST + 8 - time.time()))
    start = max(0.0, spike_t - t0 - PRE)
    out = os.path.join(outdir, name + ".mp4")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.2f}", "-i", rec, "-t", str(PRE + POST),
        "-vf", "crop='trunc(ih*9/16/2)*2':ih,scale=1080:1920,setsar=1",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out,
    ]
    r = subprocess.run(cmd)
    if r.returncode == 0 and os.path.exists(out):
        log(f"clip saved: {out}")
        whisper_q.put(out)
    else:
        log(f"ffmpeg failed for {name}")


def whisper_worker(q, model, outdir):
    while True:
        clip = q.get()
        log(f"transcribing {os.path.basename(clip)} ...")
        r = subprocess.run([
            "whisper", clip, "--model", model, "--output_format", "srt",
            "--output_dir", outdir, "--fp16", "False", "--verbose", "False",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            log(f"subtitles saved: {os.path.splitext(clip)[0]}.srt")
        else:
            log(f"whisper failed for {clip}")


def chat_lines(channel):
    """Yield (timestamp) for every chat message, reconnecting forever."""
    while True:
        try:
            s = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=300)
            nick = f"justinfan{random.randint(10000, 99999)}"
            s.sendall(f"NICK {nick}\r\nJOIN #{channel}\r\n".encode())
            log(f"connected to #{channel} chat as {nick}")
            buf = b""
            while True:
                data = s.recv(4096)
                if not data:
                    raise ConnectionError("chat disconnected")
                buf += data
                *lines, buf = buf.split(b"\r\n")
                for line in lines:
                    if line.startswith(b"PING"):
                        s.sendall(line.replace(b"PING", b"PONG", 1) + b"\r\n")
                    elif b" PRIVMSG #" in line:
                        yield time.time()
        except (OSError, ConnectionError) as e:
            log(f"chat error: {e}; reconnecting in 5s")
            time.sleep(5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("channel")
    ap.add_argument("--rec", required=True, help="path of the live .ts recording")
    ap.add_argument("--min", type=int, default=10, help="min messages in a 10s bucket")
    ap.add_argument("--factor", type=float, default=2.5)
    ap.add_argument("--model", default="base", help="whisper model")
    ap.add_argument("--clips", default="clips")
    a = ap.parse_args()
    channel = a.channel.lower().lstrip("#")
    os.makedirs(a.clips, exist_ok=True)

    wq = queue.Queue()
    threading.Thread(target=whisper_worker, args=(wq, a.model, a.clips), daemon=True).start()

    t0 = wait_for_recording(a.rec)
    history = deque(maxlen=WINDOW)
    bucket_start, count = time.time(), 0
    last_clip = 0.0

    def close_buckets(now):
        nonlocal bucket_start, count, last_clip
        while now - bucket_start >= BUCKET:
            end = bucket_start + BUCKET
            if len(history) >= 6:  # need ~1 min of baseline first
                med = statistics.median(history)
                thr = max(a.min, a.factor * med)
                if count >= thr and end - last_clip >= PRE + POST:
                    last_clip = end
                    name = f"{channel}_{time.strftime('%Y%m%d_%H%M%S', time.localtime(end))}"
                    log(f"SPIKE {count} msgs (median {med:.1f}) -> {name}")
                    threading.Thread(target=cut_clip,
                                     args=(a.rec, t0, end, name, a.clips, wq),
                                     daemon=True).start()
            history.append(count)
            if os.environ.get("CW_DEBUG"):
                log(f"bucket: {count} msgs")
            bucket_start, count = end, 0

    # a ticker so empty buckets still close when chat is silent
    lock = threading.Lock()

    def ticker():
        while True:
            time.sleep(1)
            with lock:
                close_buckets(time.time())
    threading.Thread(target=ticker, daemon=True).start()

    for ts in chat_lines(channel):
        with lock:
            close_buckets(ts)
            count += 1


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
