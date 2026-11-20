"""Whisper transcription. The model is loaded once per process (it is slow to load)."""
import os
import subprocess

from clipwatcher import settings
from clipwatcher.log import log

_loaded_model = None


def extract_audio(video_path, wav_path, start_s, length_s):
    """16 kHz mono wav of [start_s, start_s + length_s]: all Whisper needs, and fast."""
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start_s:.2f}",
                    "-t", f"{length_s:.2f}", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", wav_path],
                   check=True)


def transcribe(media_path, model_name, vocabulary_hint=""):
    """Whisper result dict: {"text": ..., "segments": [{"words": [{"word", "start", "end",
    "probability"}]}]}. vocabulary_hint (names, game terms) makes those words come out right."""
    global _loaded_model
    import whisper
    if _loaded_model is None:
        log(f"loading whisper model '{model_name}' (first time only)...")
        import torch
        thread_count = int(settings.FFMPEG_THREADS or 0)
        if thread_count > 0:
            torch.set_num_threads(thread_count)
        _loaded_model = whisper.load_model(model_name)
    return _loaded_model.transcribe(media_path, word_timestamps=True, fp16=False, verbose=None,
                                    language="en", condition_on_previous_text=False,
                                    initial_prompt=vocabulary_hint or None)


def transcribe_window(video_path, model_name, start_s, length_s, vocabulary_hint=""):
    """Transcribe only the final clip window; times in the result start at 0."""
    wav_path = os.path.splitext(video_path)[0] + ".window.wav"
    try:
        extract_audio(video_path, wav_path, start_s, length_s)
        return transcribe(wav_path, model_name, vocabulary_hint)
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)
