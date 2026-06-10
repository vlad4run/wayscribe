"""HTTP client for FastFlowLM `/v1/audio/transcriptions` (OpenAI-compatible)."""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from wayscribe.config import Config


@dataclass
class BackendHealth:
    """Result of a cheap reachability probe against the STT backend."""

    reachable: bool
    models: list[str] = field(default_factory=list)
    detail: str | None = None

    def has_model(self, model: str) -> bool:
        return any(m == model or m.startswith(model + ":") for m in self.models)


def _parse_models(payload: object) -> list[str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    return [m["id"] for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)]


def probe_sync(cfg: Config | None = None, timeout: float = 2.0) -> BackendHealth:
    cfg = cfg or Config.load()
    try:
        with httpx.Client(base_url=cfg.endpoint, timeout=timeout) as client:
            r = client.get("/v1/models")
            r.raise_for_status()
            return BackendHealth(True, _parse_models(r.json()))
    except Exception as exc:
        return BackendHealth(False, detail=str(exc))


async def probe_async(cfg: Config | None = None, timeout: float = 2.0) -> BackendHealth:
    cfg = cfg or Config.load()
    try:
        async with httpx.AsyncClient(base_url=cfg.endpoint, timeout=timeout) as client:
            r = await client.get("/v1/models")
            r.raise_for_status()
            return BackendHealth(True, _parse_models(r.json()))
    except Exception as exc:
        return BackendHealth(False, detail=str(exc))


def transcribe_sync(wav: bytes, cfg: Config | None = None) -> str:
    cfg = cfg or Config.load()
    files = {"file": ("audio.wav", wav, "audio/wav")}
    data: dict[str, str] = {"model": cfg.model}
    if cfg.language:
        data["language"] = cfg.language
    with httpx.Client(base_url=cfg.endpoint, timeout=cfg.request_timeout_sec) as client:
        r = client.post("/v1/audio/transcriptions", files=files, data=data)
        r.raise_for_status()
        return r.json().get("text", "")


async def transcribe_async(wav: bytes, cfg: Config | None = None) -> str:
    cfg = cfg or Config.load()
    files = {"file": ("audio.wav", wav, "audio/wav")}
    data: dict[str, str] = {"model": cfg.model}
    if cfg.language:
        data["language"] = cfg.language
    async with httpx.AsyncClient(base_url=cfg.endpoint, timeout=cfg.request_timeout_sec) as client:
        r = await client.post("/v1/audio/transcriptions", files=files, data=data)
        r.raise_for_status()
        return r.json().get("text", "")
