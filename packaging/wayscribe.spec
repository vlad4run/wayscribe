# Disable debug subpackage — we ship a pre-built PyInstaller binary with
# no extractable debug symbols.
%global debug_package %{nil}

Name:           wayscribe
Version:        0.5.0
Release:        1%{?dist}
Summary:        Hotkey voice-to-text for KDE Plasma Wayland
License:        MIT

# Sources are staged by scripts/build-rpm.sh into %%{_topdir}/SOURCES.
Source0:        wayscribe
Source1:        wayscribe.service
Source2:        LICENSE
Source3:        README.md
Source4:        config.example.toml
Source5:        BACKEND.md
# NPU backend: docker-compose for the FastFlowLM (Whisper-on-NPU) container.
Source6:        compose.yaml
Source7:        env.example

# Pre-built x86_64 binary; do not mark noarch.
ExclusiveArch:  x86_64

Requires:       libportaudio2
Recommends:     wl-clipboard
Recommends:     libnotify-tools
# ydotool: keystroke synthesis for the auto-type output backend.
Recommends:     ydotool

%description
wayscribe is a headless voice-to-text daemon for KDE Plasma Wayland. A
global hotkey starts and stops recording; audio is transcribed by an
OpenAI-compatible speech-to-text backend and the result lands in the
clipboard, with a KDE notification preview.

Transcription runs in a separate local backend reached over HTTP — any
OpenAI-compatible server works. The reference setup runs Whisper V3 Turbo
on an AMD Ryzen AI NPU via a FastFlowLM Docker container (not packaged
here); see the project README and BACKEND.md for backend setup and KDE
hotkey bindings.

%prep
%setup -q -T -c -n %{name}-%{version}
cp -p %{SOURCE2} LICENSE
cp -p %{SOURCE3} README.md
cp -p %{SOURCE4} config.example.toml
cp -p %{SOURCE5} BACKEND.md
# NPU backend compose, shipped as %%doc deploy-npu/ (see BACKEND.md)
mkdir -p deploy-npu
cp -p %{SOURCE6} deploy-npu/compose.yaml
cp -p %{SOURCE7} deploy-npu/.env.example

%install
install -D -m 0755 %{SOURCE0} %{buildroot}%{_bindir}/wayscribe
install -D -m 0644 %{SOURCE1} %{buildroot}%{_userunitdir}/wayscribe.service

%files
%license LICENSE
%doc README.md
%doc BACKEND.md
%doc config.example.toml
# NPU backend compose (FastFlowLM / Whisper-on-NPU)
%doc deploy-npu
%{_bindir}/wayscribe
%{_userunitdir}/wayscribe.service

%changelog
* Mon Jul 27 2026 Vladislav Zverev <vladspbru@gmail.com> - 0.5.0-1
- Scope back to speech-to-text only: drop the keyboard-layout fixer, the
  LLM spell-fix/translate commands, and the opt-in evdev global autocorrect
  (`fix`, `translate`, `autocorrect` subcommands and their config keys are
  gone). That work continues on the feat/keyboard-autocorrect branch
- Drop the evdev runtime dependency
- Add `wayscribe version` (package version + git build hash)
- Auto-type pastes via Shift+Insert so transcripts land in terminals too

* Wed Jun 17 2026 Vladislav Zverev <vladspbru@gmail.com> - 0.3.0-1
- Auto-type: paste non-ASCII (e.g. Cyrillic) transcripts via clipboard +
  Ctrl+V, since `ydotool type` emits ASCII keycodes only
- Add `wayscribe log [-f] [-n N]` to tail the daemon journal

* Wed Jun 10 2026 Vladislav Zverev <vladspbru@gmail.com> - 0.2.0-1
- Add `wayscribe doctor` self-diagnosis command
- status reports backend reachability; warmup notifies on a down backend
- Probe backend outside the daemon state lock

* Tue Jun 09 2026 Vladislav Zverev <vladspbru@gmail.com> - 0.1.0-1
- Default language ru; follow KDE keyboard layout by default
- Ship config.example.toml reference

* Thu May 28 2026 Vladislav Zverev <vladspbru@gmail.com> - 0.1.0-1
- Initial RPM: PyInstaller-bundled binary + systemd user unit
