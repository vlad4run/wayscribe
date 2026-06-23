"""wayscribe: hotkey voice-to-text and keyboard-layout fixer for KDE Plasma Wayland."""
from __future__ import annotations

import subprocess
from pathlib import Path

__version__ = "0.4.1"


def _git_hash() -> tuple[str, bool] | None:
    """Resolve the git short hash and dirty flag, or None if unknown.

    Prefers the build-time baked module (present only in the PyInstaller
    binary), then falls back to live `git` against this checkout. Any failure
    (git missing, not a repo, baked module absent) yields None.
    """
    try:
        from wayscribe._buildinfo import GIT_DIRTY, GIT_HASH  # type: ignore[import-not-found]
        if GIT_HASH and GIT_HASH != "unknown":
            return GIT_HASH, bool(GIT_DIRTY)
    except Exception:
        pass

    repo = Path(__file__).resolve().parent.parent
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if head.returncode != 0:
            return None
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        return head.stdout.strip(), bool(dirty.stdout.strip())
    except Exception:
        return None


def version_string() -> str:
    """Package version combined with the git build hash, PEP 440 local style."""
    info = _git_hash()
    if info is None:
        return __version__
    h, dirty = info
    return f"{__version__}+g{h}.dirty" if dirty else f"{__version__}+g{h}"
