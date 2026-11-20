"""Find THE moment in a raw clip (the loudest reaction) and pick the final window around it.

Viral clips start on the action and hard-cut right after the punchline, so the clip loops.
Chat reacts a few seconds after something happens, so the cutter grabs a wide search
window around the chat spike; this module finds the real peak in the audio (the scream,
the explosion) and keeps only `length_s` seconds ending `after_peak_s` after it.

Pure math is in `find_peak_s` / `choose_window`; only `loudness_envelope` runs ffmpeg.
"""
import array
import math
import subprocess

SAMPLE_RATE = 8000          # plenty for loudness
STEP_S = 0.1                # one loudness value per 100 ms
SMOOTH_STEPS = 3            # 0.3 s moving average, so clicks don't count as peaks


def loudness_envelope(media_path):
    """[(time_s, loudness_db)] every STEP_S seconds. Empty list if there is no audio."""
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", media_path,
               "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"]
    pcm_bytes = subprocess.run(command, capture_output=True).stdout
    samples = array.array("h")
    samples.frombytes(pcm_bytes[:len(pcm_bytes) // 2 * 2])
    step = int(SAMPLE_RATE * STEP_S)
    envelope = []
    for start in range(0, len(samples) - step + 1, step):
        chunk = samples[start:start + step]
        rms = math.sqrt(sum(value * value for value in chunk) / step)
        envelope.append((start / SAMPLE_RATE, 20 * math.log10(rms / 32768) if rms > 0 else -100.0))
    return envelope


def smooth(envelope, steps=SMOOTH_STEPS):
    smoothed = []
    for index, (time_s, _db) in enumerate(envelope):
        window = envelope[max(0, index - steps + 1):index + 1]
        smoothed.append((time_s, sum(db for _t, db in window) / len(window)))
    return smoothed


def find_peak_s(envelope, search_start_s=0.0, search_end_s=None):
    """Time of the loudest (smoothed) moment in [search_start_s, search_end_s], or None."""
    candidates = [(db, time_s) for time_s, db in smooth(envelope)
                  if time_s >= search_start_s and (search_end_s is None or time_s <= search_end_s)]
    if not candidates:
        return None
    _loudest_db, peak_s = max(candidates)
    return peak_s


def find_onset_s(envelope, peak_s, rise_db=6.0, max_lookback_s=1.5):
    """Where the loudness starts rising into the peak: the right spot for an impact sound."""
    by_time = dict(smooth(envelope))
    peak_db = by_time.get(peak_s)
    if peak_db is None:
        return peak_s
    onset_s = peak_s
    for time_s, db in sorted(by_time.items(), reverse=True):
        if time_s > peak_s:
            continue
        if peak_s - time_s > max_lookback_s or db < peak_db - rise_db:
            break
        onset_s = time_s
    return onset_s


def choose_window(duration_s, peak_s, length_s, after_peak_s):
    """(start_s, end_s) of the final clip: ends after_peak_s past the peak, length_s long,
    clamped to the raw clip."""
    end_s = min(duration_s, peak_s + after_peak_s)
    start_s = max(0.0, end_s - length_s)
    end_s = min(duration_s, start_s + length_s)
    return round(start_s, 2), round(end_s, 2)


def find_key_moment(envelope, max_length_s=3.0, min_length_s=0.8, drop_db=18.0, quiet_gap_s=0.3,
                    lead_in_s=0.15):
    """(start_s, end_s) of the main sound event in a meme clip: the loudest moment, extended
    left and right while the sound stays within drop_db of it (a quiet gap of quiet_gap_s ends
    it). E.g. just the "noice" out of a 7 s clip. None if there is no audio."""
    smoothed = smooth(envelope)
    if not smoothed:
        return None
    peak_db, peak_index = max((db, index) for index, (_time_s, db) in enumerate(smoothed))
    threshold_db = peak_db - drop_db
    gap_steps = max(1, int(quiet_gap_s / STEP_S))

    def edge(direction):
        index, quiet_run, last_loud = peak_index, 0, peak_index
        while 0 <= index + direction < len(smoothed):
            index += direction
            if smoothed[index][1] >= threshold_db:
                quiet_run, last_loud = 0, index
            else:
                quiet_run += 1
                if quiet_run >= gap_steps:
                    break
        return last_loud

    start_s = max(0.0, smoothed[edge(-1)][0] - lead_in_s)
    end_s = smoothed[edge(+1)][0] + STEP_S * 2
    peak_s = smoothed[peak_index][0]
    if end_s - start_s > max_length_s:  # long event: keep the part around the peak
        start_s = max(start_s, peak_s - max_length_s * 0.35)
        end_s = start_s + max_length_s
    if end_s - start_s < min_length_s:
        end_s = start_s + min_length_s
    return round(start_s, 2), round(end_s, 2)
