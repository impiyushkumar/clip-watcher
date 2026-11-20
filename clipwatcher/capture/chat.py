"""Read live chat without logging in. Each reader is a generator that yields the arrival
time (unix seconds) of every chat message and reconnects forever on errors."""
import json
import random
import socket
import time

from clipwatcher.log import log

TWITCH_IRC_ADDRESS = ("irc.chat.twitch.tv", 6667)
KICK_PUSHER_URL = ("wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679"
                   "?protocol=7&client=js&version=8.4.0-rc2&flash=false")


def twitch_message_times(channel):
    """Twitch: anonymous IRC as a random justinfanNNNNN user."""
    while True:
        try:
            irc = socket.create_connection(TWITCH_IRC_ADDRESS, timeout=300)
            nick = f"justinfan{random.randint(10000, 99999)}"
            irc.sendall(f"NICK {nick}\r\nJOIN #{channel}\r\n".encode())
            log(f"connected to #{channel} chat as {nick}")
            buffer = b""
            while True:
                data = irc.recv(4096)
                if not data:
                    raise ConnectionError("chat disconnected")
                buffer += data
                *lines, buffer = buffer.split(b"\r\n")
                for line in lines:
                    if line.startswith(b"PING"):
                        irc.sendall(line.replace(b"PING", b"PONG", 1) + b"\r\n")
                    elif b" PRIVMSG #" in line:
                        yield time.time()
        except (OSError, ConnectionError) as error:
            log(f"chat error: {error}; reconnecting in 5s")
            time.sleep(5)


def youtube_live_url(channel):
    """channel = @handle, UC... channel id, or a full video URL."""
    if channel.startswith("http"):
        return channel
    if channel.startswith("UC") and len(channel) == 24:
        return f"https://www.youtube.com/channel/{channel}/live"
    return f"https://www.youtube.com/@{channel.lstrip('@')}/live"


def youtube_message_times(channel):
    """YouTube Live chat via the chat-downloader package."""
    from chat_downloader import ChatDownloader
    url = youtube_live_url(channel)
    while True:
        try:
            log(f"connecting to YouTube chat {url}")
            for _message in ChatDownloader().get_chat(url, message_groups=["messages"]):
                yield time.time()
            log("YouTube chat ended; retrying in 30s")
        except Exception as error:
            log(f"YouTube chat error: {error}; retrying in 30s")
        time.sleep(30)


def kick_chatroom_id(channel_slug):
    url = f"https://kick.com/api/v2/channels/{channel_slug}"
    try:  # Kick sits behind Cloudflare; curl_cffi impersonates a real browser
        from curl_cffi import requests as browser_requests
        return browser_requests.get(url, impersonate="chrome", timeout=20).json()["chatroom"]["id"]
    except ImportError:
        import urllib.request
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        return json.load(urllib.request.urlopen(request, timeout=20))["chatroom"]["id"]


def kick_message_times(channel_slug):
    """Kick: public Pusher websocket."""
    import websocket
    chatroom_id = None
    while True:
        try:
            chatroom_id = chatroom_id or kick_chatroom_id(channel_slug)
            socket_connection = websocket.create_connection(KICK_PUSHER_URL, timeout=120)
            socket_connection.send(json.dumps({
                "event": "pusher:subscribe",
                "data": {"auth": "", "channel": f"chatrooms.{chatroom_id}.v2"}}))
            log(f"connected to Kick chat {channel_slug} (room {chatroom_id})")
            while True:
                message = json.loads(socket_connection.recv())
                event_name = message.get("event", "")
                if event_name == "pusher:ping":
                    socket_connection.send(json.dumps({"event": "pusher:pong", "data": {}}))
                elif event_name.endswith("ChatMessageEvent"):
                    yield time.time()
        except Exception as error:
            log(f"Kick chat error: {error}; reconnecting in 5s")
            time.sleep(5)


CHAT_READERS = {"twitch": twitch_message_times,
                "youtube": youtube_message_times,
                "kick": kick_message_times}


def message_times(platform, channel):
    return CHAT_READERS[platform](channel)
