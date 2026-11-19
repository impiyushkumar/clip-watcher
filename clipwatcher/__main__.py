"""One command line for every manual task. Run from the repo root:

    python3 -m clipwatcher <command> [options]
    (on a server: .venv/bin/python -m clipwatcher <command>)

Commands:
    settings                 print every effective setting (config.txt + env + defaults)
    targets                  print the upload platforms that are set up, e.g. "youtube,instagram"
    youtube-login            one-time YouTube login, saves token.json
    stats                    fill YouTube views/likes into clips/scoreboard.csv
    meta-setup               one-time Instagram/Facebook setup, saves meta.json
    meta-test <video.mp4>    test upload to Instagram + Facebook
    learn                    refresh stats, relearn, print clips/learning.md
    pick-length [default]    clip length for the next stream (used by scripts/run.sh)
    post-now                 post the best queued clip to every platform once
    rerender [--drop-missing]  re-render queued clips in the current style
"""
import sys


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    command, options = argv[0], argv[1:]

    if command == "settings":
        from clipwatcher import settings
        for name, value in settings.as_dict().items():
            print(f"{name} = {value!r}")
    elif command == "targets":
        from clipwatcher import settings
        from clipwatcher.publish.poster import usable_targets
        requested = options[0] if options else settings.UPLOAD_TARGETS
        print(",".join(usable_targets(requested, explain=True)) or "none")
    elif command == "youtube-login":
        from clipwatcher.publish import youtube
        youtube.get_service(interactive=True)
        print("Logged in to YouTube. token.json saved - uploads are now automatic.")
    elif command == "stats":
        from clipwatcher.publish import youtube
        youtube.refresh_stats()
    elif command == "meta-setup":
        from clipwatcher.publish import meta_graph
        meta_graph.interactive_setup()
    elif command == "meta-test":
        from clipwatcher.publish import meta_graph
        if not options:
            print("usage: python3 -m clipwatcher meta-test clips/ready/<clip>.mp4")
            return 1
        meta_graph.test_upload(options[0])
    elif command == "learn":
        from clipwatcher import learner, paths
        learner.refresh_and_learn()
        with open(paths.LEARNING_REPORT_FILE, encoding="utf-8") as report_file:
            print(report_file.read())
    elif command == "pick-length":
        from clipwatcher import learner
        print(learner.pick_clip_length(int(options[0]) if options else 30))
    elif command == "post-now":
        from clipwatcher.publish import scheduler
        scheduler.main(["--once"] + options)
    elif command == "rerender":
        from clipwatcher.rerender import rerender_queue
        rerender_queue(drop_missing="--drop-missing" in options)
    else:
        print(f"unknown command {command!r}\n{__doc__}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
