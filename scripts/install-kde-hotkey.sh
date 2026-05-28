#!/usr/bin/env bash
# Register `flm-voice toggle` as a KDE Plasma Wayland Custom Shortcut.
#
# KDE's khotkeys schema in kglobalshortcutsrc is fragile to script-edits, so
# this helper does the safe half (installing a .desktop launcher) and prints
# the remaining GUI steps. Override FLM_VOICE_HOTKEY to change the default.
set -euo pipefail

HOTKEY="${FLM_VOICE_HOTKEY:-Meta+Alt+Space}"
BIN="$(command -v flm-voice || true)"
if [ -z "$BIN" ]; then
    echo "flm-voice not in PATH — install the package first (pip install -e .)" >&2
    exit 1
fi

DESKTOP="$HOME/.local/share/applications/flm-voice-toggle.desktop"
mkdir -p "$(dirname "$DESKTOP")"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=flm-voice toggle
Comment=Toggle voice recording (Whisper on NPU)
Exec=$BIN toggle
Icon=audio-input-microphone
NoDisplay=true
EOF
echo "Wrote $DESKTOP"

cat <<MSG

Next steps (KDE Plasma 6):
  1. Open: System Settings -> Shortcuts -> Custom Shortcuts
  2. Edit -> New -> Global Shortcut -> Command/URL
  3. Trigger:  ${HOTKEY}
  4. Action:   ${BIN} toggle
  5. Apply

Then start the daemon:
  systemctl --user enable --now flm-voice
MSG
