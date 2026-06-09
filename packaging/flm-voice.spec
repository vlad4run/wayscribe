# Disable debug subpackage — we ship a pre-built PyInstaller binary with
# no extractable debug symbols.
%global debug_package %{nil}

Name:           flm-voice
Version:        0.1.0
Release:        1%{?dist}
Summary:        Hotkey voice-to-text for KDE Plasma Wayland (Whisper on AMD NPU)
License:        MIT

# Sources are staged by scripts/build-rpm.sh into %%{_topdir}/SOURCES.
Source0:        flm-voice
Source1:        flm-voice.service
Source2:        LICENSE
Source3:        README.md
Source4:        config.example.toml

# Pre-built x86_64 binary; do not mark noarch.
ExclusiveArch:  x86_64

Requires:       libportaudio2
Recommends:     wl-clipboard
Recommends:     libnotify-tools

%description
flm-voice is a headless voice-to-text daemon for KDE Plasma Wayland. A
global hotkey starts and stops recording; audio is transcribed by Whisper
V3 Turbo running on the AMD Ryzen AI NPU (via FastFlowLM) and the result
lands in the clipboard, with a KDE notification preview.

The Whisper inference engine itself runs in a separate FastFlowLM Docker
container (not packaged here); see the project README for setup of the
NPU backend and KDE hotkey bindings.

%prep
%setup -q -T -c -n %{name}-%{version}
cp -p %{SOURCE2} LICENSE
cp -p %{SOURCE3} README.md
cp -p %{SOURCE4} config.example.toml

%install
install -D -m 0755 %{SOURCE0} %{buildroot}%{_bindir}/flm-voice
install -D -m 0644 %{SOURCE1} %{buildroot}%{_userunitdir}/flm-voice.service

%files
%license LICENSE
%doc README.md
%doc config.example.toml
%{_bindir}/flm-voice
%{_userunitdir}/flm-voice.service

%changelog
* Mon Jun 09 2026 Vladislav Zverev <vladspbru@gmail.com> - 0.1.0-1
- Default language ru; follow KDE keyboard layout by default
- Ship config.example.toml reference

* Thu May 28 2026 Vladislav Zverev <vladspbru@gmail.com> - 0.1.0-1
- Initial RPM: PyInstaller-bundled binary + systemd user unit
