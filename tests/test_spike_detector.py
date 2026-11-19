import unittest

from clipwatcher.capture.spike_detector import BUCKET_S, SpikeDetector


def feed(detector, start_ts, messages_per_bucket):
    """Send `count` messages inside each consecutive 10 s bucket; return all spikes."""
    spikes = []
    for bucket_index, count in enumerate(messages_per_bucket):
        for message_index in range(count):
            spikes += detector.add_message(start_ts + bucket_index * BUCKET_S + message_index * 0.01)
    spikes += detector.close_buckets(start_ts + len(messages_per_bucket) * BUCKET_S)
    return spikes


class SpikeDetectorTest(unittest.TestCase):
    def test_spike_after_baseline(self):
        detector = SpikeDetector(min_messages=10, factor=2.5, min_gap_s=30, start_ts=1000.0)
        spikes = feed(detector, 1000.0, [4] * 6 + [30])
        self.assertEqual(len(spikes), 1)
        bucket_end_ts, count, median = spikes[0]
        self.assertEqual((bucket_end_ts, count, median), (1070.0, 30, 4))

    def test_no_spike_without_baseline(self):
        detector = SpikeDetector(min_messages=10, factor=2.5, min_gap_s=30, start_ts=0.0)
        self.assertEqual(feed(detector, 0.0, [50, 50]), [])

    def test_min_messages_floor(self):
        detector = SpikeDetector(min_messages=10, factor=2.5, min_gap_s=30, start_ts=0.0)
        self.assertEqual(feed(detector, 0.0, [1] * 6 + [9]), [])  # 9 > 2.5*1 but < 10

    def test_min_gap_between_clips(self):
        detector = SpikeDetector(min_messages=10, factor=2.5, min_gap_s=30, start_ts=0.0)
        spikes = feed(detector, 0.0, [2] * 6 + [40, 40, 40, 40])
        self.assertEqual([spike[0] for spike in spikes], [70.0, 100.0])

    def test_silent_chat_still_closes_buckets(self):
        detector = SpikeDetector(min_messages=10, factor=2.5, min_gap_s=30, start_ts=0.0)
        detector.close_buckets(65.0)
        self.assertEqual(len(detector.history), 6)


if __name__ == "__main__":
    unittest.main()
