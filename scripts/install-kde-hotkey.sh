#!/usr/bin/env bash
# Print the steps to bind `wayscribe toggle` to a global hotkey in KDE
# Plasma 6. KDE's khotkeys config is not safe to edit from scripts, so the
# binding itself is done via System Settings. Override WAYSCRIBE_HOTKEY to
# change the suggested combo.
set -euo pipefail

HOTKEY="${WAYSCRIBE_HOTKEY:-Meta+Alt+Space}"
LANG_HOTKEY="${WAYSCRIBE_LANG_HOTKEY:-Meta+Alt+L}"
BIN="$(command -v wayscribe || true)"
if [ -z "$BIN" ]; then
    echo "wayscribe not in PATH — install the package first (pip install -e .)" >&2
    exit 1
fi

cat <<MSG
Bind global hotkeys in KDE Plasma 6:

  System Settings -> Shortcuts -> Custom Shortcuts
  Edit -> New -> Global Shortcut -> Command/URL

Recording toggle:
  Trigger:  ${HOTKEY}
  Action:   ${BIN} toggle

Language cycle (optional):
  Trigger:  ${LANG_HOTKEY}
  Action:   ${BIN} lang next

Then start the daemon:
  systemctl --user enable --now wayscribe
MSG
