"""clips/scoreboard.csv: one row per clip with its post links and view stats.
learner.py reads it to tune settings. Column names are stored on disk: never rename them."""
import csv
import os

from clipwatcher import paths

COLUMNS = ["clip", "created", "source", "hook", "length_s", "youtube_url",
           "views", "likes", "comments", "stats_updated", "instagram_url", "facebook_url", "posted"]


def read_rows(scoreboard_path=None):
    scoreboard_path = scoreboard_path or paths.SCOREBOARD_FILE
    if not os.path.exists(scoreboard_path):
        return []
    with open(scoreboard_path, encoding="utf-8") as scoreboard_file:
        return list(csv.DictReader(scoreboard_file))


def write_rows(rows, scoreboard_path=None):
    scoreboard_path = scoreboard_path or paths.SCOREBOARD_FILE
    extra_columns = [name for name in (rows[0].keys() if rows else []) if name not in COLUMNS]
    columns = COLUMNS + extra_columns
    os.makedirs(os.path.dirname(scoreboard_path), exist_ok=True)
    with open(scoreboard_path, "w", newline="", encoding="utf-8") as scoreboard_file:
        writer = csv.DictWriter(scoreboard_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows({name: row.get(name, "") for name in columns} for row in rows)


def upsert_row(new_row, scoreboard_path=None):
    """Add the row, or fill its non-empty fields into the existing row for the same clip."""
    rows = read_rows(scoreboard_path)
    for row in rows:
        if row.get("clip") == new_row.get("clip"):
            row.update({name: value for name, value in new_row.items() if value})
            break
    else:
        rows.append(new_row)
    write_rows(rows, scoreboard_path)
