"""Output backends: clipboard (wl-copy), keystroke synthesis (wtype/ydotool), KDE notify."""
from __future__ import annotations

import shutil
import subprocess


def to_clipboard(text: str) -> None:
    subprocess.run(["wl-copy"], input=text.encode(), check=True)


def type_text(text: str) -> None:
    if shutil.which("wtype"):
        subprocess.run(["wtype", "--", text], check=True)
    elif shutil.which("ydotool"):
        subprocess.run(["ydotool", "type", "--", text], check=True)
    else:
        raise RuntimeError("neither wtype nor ydotool found in PATH")


def notify(title: str, body: str = "", icon: str = "audio-input-microphone") -> None:
    subprocess.run(
        ["notify-send", "--app-name=flm-voice", "--icon", icon, title, body],
        check=False,
    )
