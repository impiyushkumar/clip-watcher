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
PRE, POST = 20, 10   # default clip seconds before / after the spike (see --length)


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def wait_for_recording(path):
    """Wait until streamlink has written data; that moment = t0 of the file."""
    log(f"waiting for recording {path} ...")
    while not (os.path.exists(path) and os.path.getsize(path) > 0):
        if os.path.exists(path + ".ended"):   # streamlink gave up before any video arrived
            log("no stream recorded - stopping")
            sys.exit(0)
        time.sleep(0.5)
    t0 = time.time()
    log("recording started")
    return t0


PENDING = [0]
PENDING_LOCK = threading.Lock()


def pending(delta):
    with PENDING_LOCK:
        PENDING[0] += delta


import contextlib
import fcntl


@contextlib.contextmanager
def heavy_slot():
    """Only one CPU-heavy job (cut / captions) at a time across ALL channels."""
    os.makedirs("clips", exist_ok=True)
    with open("clips/.heavy.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


RES = os.environ.get("CW_RES", "1080x1920")      # output size, e.g. 720x1280 on small servers
THREADS = os.environ.get("CW_THREADS", "0")       # ffmpeg threads (0 = auto)
LAYOUT = os.environ.get("CW_LAYOUT", "crop")      # crop = fill screen (cuts sides), fit = whole frame + blurred background


def vertical_filter():
    w, h = RES.split("x")
    if LAYOUT == "fit":   # full 16:9 picture, sharp, centered; blurred copy fills top/bottom
        return (f"split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                f"boxblur=20:2[bg];[b]scale={w}:-2:flags=lanczos[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    return f"crop='trunc(ih*9/16/2)*2':ih,scale={w}:{h}:flags=lanczos,setsar=1"


def cut_clip(rec, t0, spike_t, name, raw_dir, job_q, score=0):
    # wait until the POST seconds (+ a margin) exist in the recording
    time.sleep(max(0, spike_t + POST + 8 - time.time()))
    start = max(0.0, spike_t - t0 - PRE)
    out = os.path.join(raw_dir, name + ".mp4")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.2f}", "-i", rec, "-t", str(PRE + POST),
        "-filter_complex" if LAYOUT == "fit" else "-vf", vertical_filter(),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", THREADS,
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out,
    ]
    with heavy_slot():
        r = subprocess.run(cmd)
    if r.returncode == 0 and os.path.exists(out):
        log(f"raw clip saved: {out}")
        job_q.put((out, name, score))
    else:
        log(f"ffmpeg failed for {name}")
        pending(-1)


def post_worker(q, opts):
    """One clip at a time: captions + hook + caption text + upload + log."""
    import postprocess
    while True:
        raw, name, score = q.get()
        try:
            with heavy_slot():
                postprocess.process(raw, name, dict(opts, score=score))
        except Exception as e:
            log(f"post-processing failed for {name}: {e}")
        finally:
            pending(-1)


def twitch_chat(channel):
    """Twitch: anonymous IRC. Yields a timestamp per message, reconnecting forever."""
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


def youtube_chat(channel):
    """YouTube Live chat via chat-downloader. channel = @handle, channel id or video URL."""
    from chat_downloader import ChatDownloader
    if channel.startswith("http"):
        url = channel
    elif channel.startswith("UC") and len(channel) == 24:
        url = f"https://www.youtube.com/channel/{channel}/live"
    else:
        url = f"https://www.youtube.com/@{channel.lstrip('@')}/live"
    while True:
        try:
            log(f"connecting to YouTube chat {url}")
            for _ in ChatDownloader().get_chat(url, message_groups=["messages"]):
                yield time.time()
            log("YouTube chat ended; retrying in 30s")
        except Exception as e:
            log(f"YouTube chat error: {e}; retrying in 30s")
        time.sleep(30)


KICK_PUSHER = ("wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679"
               "?protocol=7&client=js&version=8.4.0-rc2&flash=false")


def kick_chatroom_id(slug):
    url = f"https://kick.com/api/v2/channels/{slug}"
    try:  # Kick sits behind Cloudflare; curl_cffi impersonates a real browser
        from curl_cffi import requests as creq
        return creq.get(url, impersonate="chrome", timeout=20).json()["chatroom"]["id"]
    except ImportError:
        import json
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        return json.load(urllib.request.urlopen(req, timeout=20))["chatroom"]["id"]


def kick_chat(slug):
    """Kick: public Pusher websocket, no login."""
    import json
    import websocket
    room = None
    while True:
        try:
            room = room or kick_chatroom_id(slug)
            ws = websocket.create_connection(KICK_PUSHER, timeout=120)
            ws.send(json.dumps({"event": "pusher:subscribe",
                                "data": {"auth": "", "channel": f"chatrooms.{room}.v2"}}))
            log(f"connected to Kick chat {slug} (room {room})")
            while True:
                msg = json.loads(ws.recv())
                ev = msg.get("event", "")
                if ev == "pusher:ping":
                    ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                elif ev.endswith("ChatMessageEvent"):
                    yield time.time()
        except Exception as e:
            log(f"Kick chat error: {e}; reconnecting in 5s")
            time.sleep(5)


def chat_lines(platform, channel):
    return {"twitch": twitch_chat, "youtube": youtube_chat, "kick": kick_chat}[platform](channel)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("channel")
    ap.add_argument("--platform", default="twitch", choices=["twitch", "youtube", "kick"])
    ap.add_argument("--rec", required=True, help="path of the live .ts recording")
    ap.add_argument("--min", type=int, default=10, help="min messages in a 10s bucket")
    ap.add_argument("--factor", type=float, default=2.5)
    ap.add_argument("--model", default="base", help="whisper model")
    ap.add_argument("--clips", default="clips")
    ap.add_argument("--length", type=int, default=30, help="clip length in seconds (2/3 before the spike)")
    ap.add_argument("--upload", default="none", help="none, or any of youtube,instagram,facebook (comma separated)")
    ap.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    ap.add_argument("--tags", default="#gaming #shorts #twitch")
    ap.add_argument("--cooldown", type=int, default=0, help="min seconds between clips per channel")
    ap.add_argument("--hook", default="wait for it...", help="hook text when nobody talks")
    ap.add_argument("--source-url", default="")
    ap.add_argument("--queue", default="", help="queue folder: don't post now, let poster.py post on a schedule")
    a = ap.parse_args()
    channel = a.channel if a.platform == "youtube" else a.channel.lower().lstrip("#")
    safe = "".join(c for c in channel if c.isalnum() or c in "_-")[-40:] or "clip"
    global PRE, POST
    PRE = max(3, round(a.length * 2 / 3))
    POST = max(2, a.length - PRE)
    raw_dir = os.path.join(a.clips, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    wq = queue.Queue()
    opts = {"model": a.model, "ready_dir": os.path.join(a.clips, "ready"),
            "source_url": a.source_url or f"{a.platform}: {channel}", "tags": a.tags,
            "hook_fallback": a.hook, "length": PRE + POST, "upload": a.upload,
            "privacy": a.privacy, "scoreboard": os.path.join(a.clips, "scoreboard.csv"),
            "queue_dir": a.queue}
    threading.Thread(target=post_worker, args=(wq, opts), daemon=True).start()
    log(f"clips: {PRE}s before + {POST}s after each spike; upload: {a.upload}")

    t0 = wait_for_recording(a.rec)

    def make_clip(at, score=0):
        name = f"{a.platform}_{safe}_{time.strftime('%Y%m%d_%H%M%S', time.localtime(at))}"
        log(f"clipping -> {name}")
        pending(+1)
        threading.Thread(target=cut_clip, args=(a.rec, t0, at, name, raw_dir, wq, score),
                         daemon=True).start()

    def manual_keys():
        """Press Enter in the terminal to clip the last moments yourself."""
        nonlocal last_clip
        for _ in sys.stdin:
            with lock:
                last_clip = time.time()
            log("MANUAL clip")
            make_clip(time.time(), score=10**6)  # your own picks go first
    lock = threading.Lock()
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
                if count >= thr and end - last_clip >= max(PRE + POST, a.cooldown):
                    last_clip = end
                    log(f"SPIKE {count} msgs (median {med:.1f})")
                    make_clip(end, score=count)
            history.append(count)
            if os.environ.get("CW_DEBUG"):
                log(f"bucket: {count} msgs")
            bucket_start, count = end, 0

    # a ticker so empty buckets still close when chat is silent

    def ticker():
        while True:
            time.sleep(1)
            with lock:
                close_buckets(time.time())
            # stream ended (watch.sh drops a marker) and every clip is finished -> exit
            if os.path.exists(a.rec + ".ended") and PENDING[0] <= 0:
                log("stream over and all clips finished - stopping")
                os._exit(0)
    threading.Thread(target=ticker, daemon=True).start()
    if sys.stdin.isatty():
        threading.Thread(target=manual_keys, daemon=True).start()
        log("tip: press Enter any time to clip the moment yourself")

    for ts in chat_lines(a.platform, channel):
        with lock:
            close_buckets(ts)
            count += 1


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
