#!/usr/bin/env bash
# Pack flm-voice into a single self-contained Linux binary via PyInstaller.
#
# Output: dist/flm-voice (~25-40 MB; bundles Python, numpy, sounddevice,
# httpx). Runtime requirements on the target machine:
#   - PortAudio (libportaudio.so.2) — provided by libasound2/pipewire on
#     openSUSE; install separately on minimal targets.
#   - For the output backends you intend to use: wl-clipboard, wtype,
#     libnotify-tools.
#
# Usage:
#   scripts/build-binary.sh            # uses .venv (creates if missing)
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

echo ">>> Cleaning previous build artifacts"
rm -rf build/ dist/ flm-voice.spec

echo ">>> Building single-file binary"
"$PY" -m PyInstaller \
    --onefile \
    --name flm-voice \
    --noupx \
    --clean \
    --log-level WARN \
    --collect-submodules flm_voice \
    flm_voice/__main__.py

SIZE="$(du -h dist/flm-voice | awk '{print $1}')"
echo
echo ">>> Built dist/flm-voice (${SIZE})"
echo "Smoke test:"
dist/flm-voice --help | sed 's/^/    /'
