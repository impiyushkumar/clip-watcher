"""Timestamped logging to stdout (systemd/journalctl and the terminal both read stdout)."""
import time


def log(*parts):
    print(time.strftime("[%H:%M:%S]"), *parts, flush=True)
