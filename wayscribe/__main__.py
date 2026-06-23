"""wayscribe CLI: daemon, toggle, status, fix, translate, autocorrect, and more."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys


def build_parser() -> argparse.ArgumentParser:
    from wayscribe import version_string

    parser = argparse.ArgumentParser(prog="wayscribe")
    parser.add_argument("-V", "--version", action="version", version=version_string())
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version", help="Print version and git build hash")
    sub.add_parser("daemon", help="Run the long-lived daemon (foreground; for systemd)")
    sub.add_parser("toggle", help="Toggle recording (start if idle, stop if recording)")
    sub.add_parser("status", help="Print daemon state as JSON")
    sub.add_parser("stop", help="Tell the daemon to exit cleanly")
    sub.add_parser("cancel", help="Discard the current recording without transcribing")
    sub.add_parser("doctor", help="Diagnose daemon, backend, tools, and config")
    one = sub.add_parser("oneshot", help="Record for N seconds and print transcript (no daemon)")
    one.add_argument("--duration", type=float, default=5.0)
    lang = sub.add_parser(
        "lang",
        help="Show / set / cycle the transcription language (no arg = show)",
    )
    lang.add_argument(
        "value",
        nargs="?",
        help="Language code (e.g. ru, en), 'auto', or 'next' to cycle through configured languages",
    )
    fix = sub.add_parser("fix", help="Fix wrong-layout text in the selection (ghbdtn -> привет)")
    fix.add_argument(
        "--spell", action="store_true", help="Also LLM-correct spelling/grammar after re-keying"
    )
    sub.add_parser("translate", help="Translate the selection to English (needs LLM)")
    ac = sub.add_parser(
        "autocorrect",
        help="Toggle global auto-layout-fix (needs evdev_autocorrect=true in config)",
    )
    ac.add_argument(
        "value",
        nargs="?",
        choices=["on", "off", "toggle"],
        default="toggle",
        help="on / off / toggle (default toggle)",
    )
    logp = sub.add_parser("log", help="Show the daemon journal (systemd --user unit)")
    logp.add_argument("-f", "--follow", action="store_true", help="Follow new log lines")
    logp.add_argument(
        "-n", "--lines", type=int, default=50, help="Show the last N lines (default 50)"
    )
    return parser


# systemd --user unit name the README / packaging install the daemon under.
_UNIT = "wayscribe.service"


def cmd_log(follow: bool, lines: int) -> int:
    """Tail the daemon journal, or print a hint if journalctl/the unit is absent.

    The daemon logs to stderr, which journald captures only when it runs as the
    systemd --user service. A manually-launched `wayscribe daemon` prints to its
    own terminal instead, so there is nothing to tail here.
    """
    if shutil.which("journalctl") is None:
        print(
            "journalctl not found. If you run `wayscribe daemon` manually, the log is "
            "on that terminal's stderr.",
            file=sys.stderr,
        )
        return 2
    argv = ["journalctl", "--user", "-u", _UNIT, "-n", str(lines)]
    if follow:
        argv.append("-f")
    try:
        return subprocess.run(argv, check=False).returncode
    except KeyboardInterrupt:  # Ctrl+C out of -f follow mode is not an error.
        return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "version":
        from wayscribe import version_string
        print(version_string())
        return 0

    if args.cmd == "daemon":
        from wayscribe.daemon import run
        return run()

    if args.cmd == "doctor":
        from wayscribe.doctor import run as doctor_run
        return doctor_run()

    if args.cmd in ("toggle", "status", "stop", "cancel"):
        from wayscribe.ipc import send_command
        return send_command(args.cmd)

    if args.cmd == "lang":
        from wayscribe.ipc import send_command
        if args.value is None:
            return send_command("status")
        if args.value == "next":
            return send_command("lang_next")
        return send_command("lang_set", value=args.value)

    if args.cmd == "fix":
        from wayscribe.ipc import send_command
        if args.spell:
            return send_command("fix", mode="spell")
        return send_command("fix")

    if args.cmd == "translate":
        from wayscribe.ipc import send_command
        return send_command("translate")

    if args.cmd == "autocorrect":
        from wayscribe.ipc import send_command
        return send_command("autocorrect", value=args.value)

    if args.cmd == "log":
        return cmd_log(args.follow, args.lines)

    if args.cmd == "oneshot":
        from wayscribe.recorder import record_to_wav
        from wayscribe.transcriber import transcribe_sync
        wav = record_to_wav(duration=args.duration)
        print(transcribe_sync(wav))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
