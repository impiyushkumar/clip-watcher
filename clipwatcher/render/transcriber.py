"""Whisper transcription. The model is loaded once per process (it is slow to load)."""
from clipwatcher import settings
from clipwatcher.log import log

_loaded_model = None


def transcribe(video_path, model_name):
    """Whisper result dict: {"text": ..., "segments": [{"words": [{"word", "start", "end"}]}]}."""
    global _loaded_model
    import whisper
    if _loaded_model is None:
        log(f"loading whisper model '{model_name}' (first time only)...")
        import torch
        thread_count = int(settings.FFMPEG_THREADS or 0)
        if thread_count > 0:
            torch.set_num_threads(thread_count)
        _loaded_model = whisper.load_model(model_name)
    return _loaded_model.transcribe(video_path, word_timestamps=True, fp16=False, verbose=None)
