#!/usr/bin/env bash
# Print the steps to bind `flm-voice toggle` to a global hotkey in KDE
# Plasma 6. KDE's khotkeys config is not safe to edit from scripts, so the
# binding itself is done via System Settings. Override FLM_VOICE_HOTKEY to
# change the suggested combo.
set -euo pipefail

HOTKEY="${FLM_VOICE_HOTKEY:-Meta+Alt+Space}"
LANG_HOTKEY="${FLM_VOICE_LANG_HOTKEY:-Meta+Alt+L}"
BIN="$(command -v flm-voice || true)"
if [ -z "$BIN" ]; then
    echo "flm-voice not in PATH — install the package first (pip install -e .)" >&2
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
  systemctl --user enable --now flm-voice
MSG
