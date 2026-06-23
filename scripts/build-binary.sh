#!/usr/bin/env bash
# Pack wayscribe into a single self-contained Linux binary via PyInstaller.
#
# Output: dist/wayscribe (~25-40 MB; bundles Python, numpy, sounddevice,
# httpx). Runtime requirements on the target machine:
#   - PortAudio (libportaudio.so.2) — provided by libasound2/pipewire on
#     openSUSE; install separately on minimal targets.
#   - For the output backends you intend to use: wl-clipboard, wtype/ydotool,
#     libnotify-tools.
#
# The global autocorrect needs python-evdev (a core dependency). It is bundled
# by default so `wayscribe autocorrect` works from the binary. Set
# WITHOUT_EVDEV=1 to skip it (leaner binary; that one feature then no-ops with a
# "python-evdev not installed" notice).
#
# Usage:
#   scripts/build-binary.sh                    # uses .venv (creates if missing)
#   WITHOUT_EVDEV=1 scripts/build-binary.sh    # skip the evdev bundle
#   PY=/usr/bin/python3.12 scripts/build-binary.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PY:-$ROOT/.venv/bin/python}"
if [ ! -x "$PY" ]; then
    echo "error: $PY not found." >&2
    echo "       Create a venv first:  python3 -m venv .venv && .venv/bin/pip install -e ." >&2
    echo "       Or set PY=/path/to/python before running this script." >&2
    exit 1
fi

if ! "$PY" -m PyInstaller --version >/dev/null 2>&1; then
    echo ">>> Installing PyInstaller into $PY"
    "$PY" -m pip install --quiet pyinstaller
fi

EVDEV_ARGS=()
if [ "${WITHOUT_EVDEV:-0}" = "1" ]; then
    echo ">>> Skipping evdev bundle (WITHOUT_EVDEV=1) — autocorrect disabled in binary"
else
    if ! "$PY" -c "import evdev" >/dev/null 2>&1; then
        echo ">>> Installing evdev into $PY"
        "$PY" -m pip install --quiet evdev
    fi
    # evdev is a C-extension with data + submodules (ecodes, _input); pull it
    # all in so the bundled `wayscribe autocorrect` can import it at runtime.
    EVDEV_ARGS=(--collect-all evdev)
    echo ">>> Bundling evdev (global autocorrect enabled in binary)"
fi

echo ">>> Cleaning previous build artifacts"
rm -rf build/ dist/ wayscribe.spec

# Bake the git build hash into the binary: PyInstaller's output has no .git, so
# version_string() reads wayscribe/_buildinfo.py instead. Generated here, removed
# on exit (gitignored), pulled into the binary by --collect-submodules wayscribe.
GIT_HASH="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
GIT_DIRTY="$([ -n "$(git status --porcelain 2>/dev/null)" ] && echo True || echo False)"
printf 'GIT_HASH = "%s"\nGIT_DIRTY = %s\n' "$GIT_HASH" "$GIT_DIRTY" > wayscribe/_buildinfo.py
trap 'rm -f "$ROOT/wayscribe/_buildinfo.py"' EXIT
echo ">>> Baked build hash ${GIT_HASH} (dirty=${GIT_DIRTY})"

echo ">>> Building single-file binary"
"$PY" -m PyInstaller \
    --onefile \
    --name wayscribe \
    --noupx \
    --clean \
    --log-level WARN \
    --collect-submodules wayscribe \
    "${EVDEV_ARGS[@]}" \
    wayscribe/__main__.py

SIZE="$(du -h dist/wayscribe | awk '{print $1}')"
echo
echo ">>> Built dist/wayscribe (${SIZE})"
echo "Smoke test:"
dist/wayscribe --help | sed 's/^/    /'
