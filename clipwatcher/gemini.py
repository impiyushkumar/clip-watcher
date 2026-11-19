"""Optional Gemini calls (needs GEMINI_API_KEY). Every caller must work when this returns None."""
import json
import time

from clipwatcher import settings
from clipwatcher.log import log

BUSY_STATUS_CODES = (429, 500, 502, 503, 504)
BACKUP_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]


MAX_INLINE_MEDIA_BYTES = 18 * 1024 * 1024   # Gemini's inline request limit is 20 MB


def ask_gemini_json(prompt, temperature=0.9, image_jpeg=None, media=()):
    """Send `prompt` with an optional JPEG and optional media [(mime_type, bytes)], e.g. the
    clip itself as ("video/mp4", ...) so Gemini can watch AND hear it. Returns the parsed
    JSON reply, or None.

    Busy errors (429/5xx) are retried, and an unavailable model falls back to the
    backup models, because a busy model is common at peak times."""
    if not settings.GEMINI_API_KEY:
        return None
    import base64
    import requests

    parts = [{"text": prompt}]
    attachments = ([("image/jpeg", image_jpeg)] if image_jpeg else []) + list(media)
    for mime_type, data in attachments:
        if data and len(data) <= MAX_INLINE_MEDIA_BYTES:
            parts.append({"inline_data": {"mime_type": mime_type, "data": base64.b64encode(data).decode()}})
    models = list(dict.fromkeys([settings.GEMINI_MODEL] + BACKUP_MODELS))  # unique, in order
    last_error = ""
    for model in models:
        for attempt in range(3):
            try:
                response = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": settings.GEMINI_API_KEY,
                             "Content-Type": "application/json"},
                    json={"contents": [{"parts": parts}],
                          "generationConfig": {"responseMimeType": "application/json",
                                               "temperature": temperature}},
                    timeout=120)
                if response.status_code in BUSY_STATUS_CODES:
                    last_error = f"{model}: {response.status_code}"
                    time.sleep(2 * (attempt + 1))
                    continue
                if response.status_code == 404:  # model name not available -> next model
                    last_error = f"{model}: not found"
                    break
                response.raise_for_status()
                reply_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(reply_text)
            except Exception as error:
                last_error = f"{model}: {error}"
                time.sleep(2)
    log(f"Gemini unavailable ({last_error}) - using the normal hook")
    return None
