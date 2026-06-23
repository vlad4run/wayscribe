# Transcription backend

wayscribe does **no transcription itself**. On each toggle it POSTs the recorded
WAV to an OpenAI-compatible `/v1/audio/transcriptions` endpoint and reads the
`text` field of the JSON reply. Everything below that HTTP boundary — the model,
the hardware — is swappable. You choose which server it talks to with two keys
in `~/.config/wayscribe/config.toml`:

```toml
endpoint = "http://localhost:52625"   # where the STT server listens
model    = "whisper-v3:turbo"          # the model name that server expects
```

- [Default: Whisper on the AMD Ryzen AI NPU](#default-whisper-on-the-amd-ryzen-ai-npu)
- [Any OpenAI-compatible STT](#any-openai-compatible-stt)
- [Optional: LLM backend (spell-fix / translate)](#optional-llm-backend-spell-fix--translate)
- [Latency](#latency-strix-point-hx-370)
- [Troubleshooting](#troubleshooting)

## Default: Whisper on the AMD Ryzen AI NPU

This is what wayscribe was built for: **Whisper V3 Turbo on the AMD Ryzen AI
NPU**, served by the FastFlowLM (FLM) container — the sibling repo
[`../fastflowlm-docker/`](../fastflowlm-docker/), an OpenAI-compatible API server
on port `52625`.

### NPU prerequisites

- AMD Ryzen AI NPU (e.g. Strix Point HX 370), kernel ≥ 6.11 with the `amdxdna`
  driver loaded.
- Docker, and your user in the host `render` group.

Verify the NPU is ready:

```bash
lsmod | grep amdxdna             # expect a match
ls -la /dev/accel/accel0         # expect crw-rw---- root:render
getent group render              # your user must be in this group:
id | grep -q render || { sudo usermod -aG render "$USER" && newgrp render; }
```

memlock unlimited (one-time, needs reboot):

```bash
echo -e "* soft memlock unlimited\n* hard memlock unlimited" | sudo tee -a /etc/security/limits.conf
```

For the NPU driver, kernel setup, and building the container image, see the
[fastflowlm-docker README](../fastflowlm-docker/README.md).

### Start it

With `docker run`:

```bash
docker run -d --rm \
  --device=/dev/accel/accel0 \
  --ulimit memlock=-1:-1 \
  -v ~/.config/flm:/root/.config/flm \
  -p 52625:52625 \
  --restart unless-stopped \
  --name flm-serve \
  fastflowlm serve gemma3:1b --asr 1 --host 0.0.0.0
```

…or via the bundled compose file. In the repo it's `deploy/`; the RPM ships it
as the **NPU backend** compose at
`/usr/share/doc/packages/wayscribe/deploy-npu/` (copy it somewhere writable
first). Then:

```bash
cd deploy        # or: cd /usr/share/doc/packages/wayscribe/deploy-npu
cp .env.example .env
# set RENDER_GID to your host's render group:
sed -i "s/^RENDER_GID=.*/RENDER_GID=$(getent group render | cut -d: -f3)/" .env
docker compose up -d
docker compose logs -f          # wait for "WebServer started on port 52625"
```

`--restart unless-stopped` means the backend survives reboots. First run
downloads ~625 MB into `~/.config/flm/`.

Config to match this backend (the defaults):

```toml
endpoint = "http://localhost:52625"
model    = "whisper-v3:turbo"
```

## Any OpenAI-compatible STT

Because the NPU lives entirely behind the HTTP call, you can point wayscribe at
**any** server that speaks `/v1/audio/transcriptions` and drop the NPU/FLM stack
altogether — just change the two keys:

```toml
endpoint = "http://localhost:8080"     # your STT server
model    = "whisper-1"                  # whatever model name it expects
```

Works with, for example:

- the bundled **FLM container** (NPU, the default — `whisper-v3:turbo` on `:52625`)
- a **whisper.cpp** or **faster-whisper** HTTP server on CPU/GPU
- a remote host on your LAN (`http://192.168.1.50:52625`)
- **OpenAI** itself (`endpoint = "https://api.openai.com"`, `model = "whisper-1"`)

The only requirement: multipart upload (`file`, `model`, optional `language`)
and a JSON reply with a `text` field. No code changes, no NPU needed. The
Wayland/KDE output side (clipboard, auto-type, notifications) is independent of
which backend you pick.

## Optional: LLM backend (spell-fix / translate)

`wayscribe fix --spell` and `wayscribe translate` call an OpenAI-compatible
**`/v1/chat/completions`** endpoint. This is **separate** from the STT endpoint
above and **off by default** — the features stay disabled until you set both
keys:

```toml
llm_endpoint = "http://localhost:52626"   # chat server; empty = LLM features off
llm_model    = "gemma3:1b"                 # the model name that server expects
# llm_api_key = "sk-…"                      # only for endpoints that require auth
# llm_timeout_sec = 30.0
```

Plain layout fixing (`wayscribe fix` without `--spell`) needs none of this — it
is fully local and offline. The LLM only adds spelling/grammar cleanup and
English translation.

### Why a *second* container on the NPU

The NPU's 8 columns are fully consumed by Whisper V3 Turbo, so **no LLM fits
alongside ASR in one FLM container** (confirmed on Strix Point HX 370; see
[Troubleshooting](#troubleshooting)). To serve chat from the NPU, run a second
FLM container **without `--asr 1`**, on a different port:

```bash
docker run -d --rm \
  --device=/dev/accel/accel0 \
  --ulimit memlock=-1:-1 \
  -v ~/.config/flm:/root/.config/flm \
  -p 52626:52625 \
  --restart unless-stopped \
  --name flm-chat \
  fastflowlm serve gemma3:1b --host 0.0.0.0
```

Note the two containers **share one NPU**: they cannot both hold a model loaded
at once, so this suits occasional spell-fix/translate, not sustained concurrent
chat + dictation.

### Or any external chat server

Because it is just an HTTP call, point `llm_endpoint` at anything that speaks
`/v1/chat/completions` — Ollama, llama.cpp/`llama-server`, LM Studio, vLLM, or a
cloud provider — typically a simpler choice than time-sharing the NPU:

```toml
llm_endpoint = "http://localhost:11434"    # e.g. Ollama
llm_model    = "qwen2.5:7b"
```

The client is best-effort: if the endpoint is unreachable or errors, wayscribe
logs it and leaves the text unchanged — `fix --spell` still applies the offline
layout re-key, and `translate` reports that the LLM is unavailable.

## Latency (Strix Point HX 370)

Measured against the NPU backend:

| Audio | Round-trip |
| --- | --- |
| 1 s (silent WAV) | ~2.2 s — base per-request overhead |
| 5 s of speech | ~3.5 s |
| 10 s of speech | ~4.0 s |
| 30 s clip | 5.1–5.5 s |

Throughput is ~6× real-time. A flat ~2 s overhead per call dominates short
utterances. (Feeding pure silence can produce short hallucinations; the daemon's
startup warm-up uses 1 s of silence and discards the result.)

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `FLM unreachable at http://localhost:52625` | Backend down | `docker ps`; restart it. The daemon stays idle, it won't crash. |
| `curl localhost:52625` refused but backend logs "started" | FLM bound to container loopback | the serve command needs `--host 0.0.0.0` (already in `deploy/compose.yaml`) |
| `Failed to load default model: <LLM>` in backend logs | The NPU's 8 columns are fully used by Whisper — **no LLM fits alongside it**. Confirmed on HX 370; `--pmode turbo` doesn't help. | Harmless: transcription still works on `:52625`. For chat, run a *second* container without `--asr 1` — see [LLM backend](#optional-llm-backend-spell-fix--translate). |
| `translate` says "LLM not configured" | `llm_endpoint`/`llm_model` unset | Set both keys — see [LLM backend](#optional-llm-backend-spell-fix--translate). Plain `fix` works without them. |
| `fix --spell` only re-keys, no spelling fix | Chat endpoint unreachable (best-effort: text left unchanged) | `wayscribe doctor` checks `llm` reachability; confirm the chat container/server is up |
