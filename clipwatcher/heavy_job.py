"""A machine-wide lock so only one CPU-heavy job (ffmpeg cut, Whisper, caption burn) runs
at a time across ALL channel processes. Keeps a 2-CPU server responsive."""
import contextlib
import fcntl
import os

from clipwatcher import paths


@contextlib.contextmanager
def heavy_job_slot():
    os.makedirs(os.path.dirname(paths.HEAVY_JOB_LOCK_FILE), exist_ok=True)
    with open(paths.HEAVY_JOB_LOCK_FILE, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
