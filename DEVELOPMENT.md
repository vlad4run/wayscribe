# Development & packaging

For building wayscribe from source, running the tests, and producing the binary
/ RPM. End users want [README.md](README.md) instead.

## Project layout

```text
wayscribe/
├── pyproject.toml
├── README.md                   # user-facing install & usage guide
├── DEVELOPMENT.md              # this file
├── wayscribe/
│   ├── __main__.py             # CLI: daemon|toggle|status|stop|cancel|doctor|oneshot|lang|log|fix|translate|autocorrect
│   ├── config.py               # XDG config + socket path
│   ├── ipc.py                  # line-delimited JSON over Unix socket (client)
│   ├── daemon.py               # asyncio IPC server + state machine + watchdogs
│   ├── recorder.py             # sounddevice → 16kHz mono WAV bytes
│   ├── transcriber.py          # httpx client for the STT backend
│   ├── output.py               # wl-copy / wtype / ydotool / notify-send + key synth
│   ├── keyboard.py             # active KDE layout ↔ ISO-639-1 (gdbus get/setLayout)
│   ├── vad.py                  # energy-based has_speech (pure numpy)
│   ├── doctor.py               # `wayscribe doctor` self-diagnosis checklist
│   ├── layout.py               # bijective ЙЦУКЕН↔QWERTY keymap (pure)
│   ├── langdetect.py           # embedded-trigram language plausibility score (pure)
│   ├── selection.py            # PRIMARY/last-word capture + pure propose_correction
│   ├── llm.py                  # best-effort OpenAI-compatible chat client (spellfix/translate)
│   ├── autocorrect.py          # phase-2 evdev grab+replay autocorrect (opt-in)
│   └── service/
│       └── wayscribe.service   # systemd --user unit
├── deploy/
│   ├── compose.yaml            # FLM backend on the NPU, port 52625
│   └── .env.example            # RENDER_GID / FLM_PORT / FLM_LLM_MODEL
├── packaging/
│   ├── wayscribe.service       # unit shipped in the RPM
│   ├── wayscribe.spec          # rpmbuild spec
│   └── config.example.toml     # reference config shipped as %doc
├── scripts/
│   ├── install-kde-hotkey.sh   # register a KDE Custom Shortcut helper
│   ├── bench_transcribe.py     # latency smoke test against FLM serve
│   ├── build-binary.sh         # PyInstaller --onefile -> dist/wayscribe
│   └── build-rpm.sh            # binary -> ~/rpmbuild/RPMS/x86_64/*.rpm
└── tests/
    ├── test_keyboard.py
    ├── test_language.py
    ├── test_outputs.py
    ├── test_recorder.py
    ├── test_skeleton.py
    ├── test_vad.py
    ├── test_layout.py          # keymap round-trip / known words
    ├── test_langdetect.py      # trigram scoring
    ├── test_selection.py       # propose_correction direction/confidence
    ├── test_llm.py             # chat client parse + best-effort failure
    ├── test_fix.py             # fix/translate IPC commands (I/O mocked)
    └── test_autocorrect.py     # WordBuffer/decide core + command gate/toggle
```

## Architecture invariants

- **No local model.** The repo only HTTP-POSTs to local backends — WAV bytes to
  the STT server, text to the optional chat LLM. All model work (NPU/Whisper)
  lives in the backend; the reference one is the sibling `../fastflowlm-docker/`.
- **Two processes over one Unix socket** at `$XDG_RUNTIME_DIR/wayscribe.sock`: a
  stateless thin client (`ipc.py`) and the asyncio daemon (`daemon.py`) owning
  the `Recorder` and a `IDLE → RECORDING → TRANSCRIBING → IDLE` state machine. A
  single `asyncio.Lock` serializes every command.
- **Blocking I/O is offloaded.** sounddevice `start`/`stop` run via
  `asyncio.to_thread`; transcription uses async httpx. Don't call blocking audio
  APIs on the event loop.
- **`oneshot` bypasses the daemon** — synchronous `record_to_wav` +
  `transcribe_sync`, no socket, no state machine.

### Layout fixer (`fix` / `translate`)

- **Pure core, I/O at the edges.** `layout.py` (keymap) and `langdetect.py`
  (trigram score) are pure and dependency-free; `selection.propose_correction`
  combines them into `(candidate, confidence, target)`. The daemon (`_fix_locked`
  / `_translate_locked`) does the subprocess I/O — capture via
  `selection.capture_target` (`wl-paste --primary`, or synth Ctrl+Shift+Left for
  `last_word`), write-back via the shared `output.type_text`. Both run in
  `asyncio.to_thread` and are gated to `State.IDLE`.
- **Never mangle correct text.** `propose_correction` returns a confidence (the
  trigram-score gap between the re-keyed candidate and the text as typed). Below
  `trigram_confidence_min` the daemon leaves the text untouched, or defers to the
  LLM when one is configured — it never writes back the gibberish re-key of
  already-correct input.
- **LLM is optional and best-effort.** `llm.py` is disabled until both
  `llm_endpoint` and `llm_model` are set (`llm.enabled`); any request failure
  logs and returns the input unchanged, mirroring the STT "unreachable" contract.
  It is a *separate* endpoint from STT (the NPU can't host both — see BACKEND.md).

### Phase-2 global autocorrect (`autocorrect`)

- **Keylogger-class, doubly gated.** `evdev_autocorrect` (config) is the master
  switch — false by default means evdev is never touched. A runtime hotkey
  (`wayscribe autocorrect [on|off|toggle]`) starts/stops the grab; the daemon
  refuses the command when the master gate is off.
- **`evdev` is an optional extra**, imported lazily inside `autocorrect.py` so the
  core/daemon run without it. `autocorrect.py`'s pure half (`KEYCODE_CHARS`,
  `WordBuffer`, `decide`) carries no evdev import and is unit-tested directly.
- **Grab + replay, no feedback loop.** The engine takes `EVIOCGRAB` of each
  keyboard and replays events through its own `UInput`. Corrections are emitted
  via `output.type_text` (ydotool → a *different* uinput device, excluded from the
  grab by name), so synthesized keys never re-enter the buffer.
- **Layout-aware decision.** `decide` reconstructs the on-screen word from the
  active KDE layout (`keyboard.current_layout_lang`), so both directions
  (Latin-active→Russian, Russian-active→English) work without false positives.
  The live grab loop is **experimental** — verify on real hardware.

## Dev setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e .[dev]        # installs evdev too (core dep)
.venv/bin/pytest -q                    # run tests (pytest-asyncio, asyncio_mode=auto)
.venv/bin/pytest tests/test_vad.py::test_name   # single test
.venv/bin/ruff check .                 # lint (E,F,I,B,UP,RUF; line-length 100)
.venv/bin/ruff format .                # format
```

`evdev` is a core dependency, but `autocorrect.py` imports it lazily, so the rest
of the app (and the whole test suite) runs even where evdev is missing or fails
to build. ruff `per-file-ignores` exempt the Cyrillic-bearing modules
(`layout.py`, `langdetect.py`, `selection.py`, `autocorrect.py`, …) from the
ambiguous-glyph lints (`RUF001/2/3`).

Smoke-test against a running FLM backend:

```bash
.venv/bin/wayscribe oneshot --duration 3   # speak, see transcript
scripts/bench_transcribe.py                # latency numbers vs FLM serve
```

## Run from source (no packaging)

```bash
python3 -m venv .venv
.venv/bin/pip install -e .

mkdir -p ~/.config/systemd/user
cp wayscribe/service/wayscribe.service ~/.config/systemd/user/
# point ExecStart at the venv binary:
sed -i "s|%h/.local/bin/wayscribe|$PWD/.venv/bin/wayscribe|" ~/.config/systemd/user/wayscribe.service
systemctl --user daemon-reload
systemctl --user enable --now wayscribe

scripts/install-kde-hotkey.sh          # prints the hotkey-binding steps
```

For a per-user binary in `~/.local/bin` instead of the venv, use `pipx install .`.

## Standalone binary

A single self-contained executable — no Python or venv on the target, only
`libportaudio.so.2` plus whichever output tools you use:

```bash
scripts/build-binary.sh                # PyInstaller --onefile -> dist/wayscribe (~30 MB)
```

Drop `dist/wayscribe` into `~/.local/bin/`, point the unit's `ExecStart=` at it,
and the Python source tree is no longer needed at runtime.

## RPM package (openSUSE)

```bash
sudo zypper install rpm-build          # one-time
scripts/build-rpm.sh                   # builds the binary, then the RPM
# -> ~/rpmbuild/RPMS/x86_64/wayscribe-*.rpm
```

The spec (`packaging/wayscribe.spec`) installs:

- `/usr/bin/wayscribe` — the PyInstaller binary
- `/usr/lib/systemd/user/wayscribe.service` — systemd user unit
- `/usr/share/doc/packages/wayscribe/README.md`
- `/usr/share/doc/packages/wayscribe/config.example.toml`
- `/usr/share/licenses/wayscribe/LICENSE`

Hard dep `libportaudio2`; `Recommends:` `wl-clipboard`, `libnotify-tools`.

## FLM backend container (image build)

The NPU/Whisper engine is the sibling repo `../fastflowlm-docker/` — see its
[README](../fastflowlm-docker/README.md) for the NPU driver and kernel setup.
Build + validate the image:

```bash
cd ../fastflowlm-docker
docker build -t fastflowlm .           # ~15-25 min
docker run --rm --device=/dev/accel/accel0 --ulimit memlock=-1:-1 fastflowlm validate
```

*Running* the container (NPU prereqs, `render` group, memlock, `docker run` /
[deploy/compose.yaml](deploy/compose.yaml), the 8-column "no LLM alongside
Whisper" constraint) is documented for users in **[BACKEND.md](BACKEND.md)**.

### New-machine dev toolchain (openSUSE)

```bash
sudo zypper install \
    docker docker-compose rpm-build \
    libportaudio2 wl-clipboard libnotify-tools \
    python3 python3-pip python3-virtualenv
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER" && newgrp docker
```

NPU runtime prerequisites (render group, memlock unlimited) are in
[BACKEND.md](BACKEND.md#npu-prerequisites).
