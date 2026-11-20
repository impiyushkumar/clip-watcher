"""Decides when chat is hyped. Pure logic (no I/O) so it is easy to test.

Messages are counted in 10 s buckets. A finished bucket is a spike when
    count >= max(min_messages, factor * median(last 3 min of buckets))
and the last clip was at least `min_gap_s` ago. Nothing is reported until there is
about 1 minute of baseline.
"""
import statistics
from collections import deque

from clipwatcher.log import log

BUCKET_S = 10
HISTORY_BUCKETS = 18        # 3 minutes of baseline
MIN_HISTORY_BUCKETS = 6     # need ~1 minute before judging


class SpikeDetector:
    def __init__(self, min_messages, factor, min_gap_s, start_ts, debug=False):
        self.min_messages = min_messages
        self.factor = factor
        self.min_gap_s = min_gap_s
        self.debug = debug
        self.history = deque(maxlen=HISTORY_BUCKETS)
        self.bucket_start_ts = start_ts
        self.bucket_count = 0
        self.last_clip_ts = 0.0

    def add_message(self, message_ts):
        """Count one chat message. Returns spikes from buckets that closed before it."""
        spikes = self.close_buckets(message_ts)
        self.bucket_count += 1
        return spikes

    def close_buckets(self, now_ts):
        """Close every bucket that ended by `now_ts`. Returns [(bucket_end_ts, count, median)]."""
        spikes = []
        while now_ts - self.bucket_start_ts >= BUCKET_S:
            bucket_end_ts = self.bucket_start_ts + BUCKET_S
            if len(self.history) >= MIN_HISTORY_BUCKETS:
                median = statistics.median(self.history)
                threshold = max(self.min_messages, self.factor * median)
                far_enough = bucket_end_ts - self.last_clip_ts >= self.min_gap_s
                if self.bucket_count >= threshold and far_enough:
                    self.last_clip_ts = bucket_end_ts
                    spikes.append((bucket_end_ts, self.bucket_count, median))
            self.history.append(self.bucket_count)
            if self.debug:
                log(f"bucket: {self.bucket_count} msgs")
            self.bucket_start_ts, self.bucket_count = bucket_end_ts, 0
        return spikes
