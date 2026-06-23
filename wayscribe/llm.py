"""OpenAI-compatible chat client for spell-fix / translation / layout fallback.

Talks to whatever `/v1/chat/completions` endpoint the user configures — a second
FastFlowLM container (no `--asr`, per BACKEND.md) or any external OpenAI-style
server. Disabled until `llm_endpoint` + `llm_model` are set. Best-effort, like
the STT path: any failure logs and returns the input unchanged so the daemon
never crashes on a flaky LLM.
"""
from __future__ import annotations

import logging

import httpx

from wayscribe.config import Config

log = logging.getLogger("wayscribe")

_SPELLFIX_SYS = (
    "You fix spelling and grammar mistakes in the user's text. "
    "Preserve the original language and meaning. "
    "Reply with ONLY the corrected text, no quotes, no explanation."
)
_TRANSLATE_SYS = (
    "You translate the user's text to English. "
    "Reply with ONLY the translation, no quotes, no explanation."
)
_FIXLAYOUT_SYS = (
    "The user's text was typed in the wrong keyboard layout and looks like "
    "gibberish. Reconstruct the intended text. "
    "Reply with ONLY the corrected text, no quotes, no explanation."
)


def enabled(cfg: Config) -> bool:
    """True when an endpoint and model are configured."""
    return bool(cfg.llm_endpoint and cfg.llm_model)


async def _chat(cfg: Config, system: str, user: str) -> str:
    """One chat round-trip; returns the assistant text, or `user` on any failure."""
    headers = {}
    if cfg.llm_api_key:
        headers["Authorization"] = f"Bearer {cfg.llm_api_key}"
    payload = {
        "model": cfg.llm_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(
            base_url=cfg.llm_endpoint, timeout=cfg.llm_timeout_sec, headers=headers
        ) as client:
            r = await client.post("/v1/chat/completions", json=payload)
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"].strip() or user
    except Exception as exc:
        log.warning("LLM request failed (%s): %s", type(exc).__name__, exc)
        return user


async def spellfix(text: str, cfg: Config) -> str:
    return await _chat(cfg, _SPELLFIX_SYS, text)


async def translate_to_en(text: str, cfg: Config) -> str:
    return await _chat(cfg, _TRANSLATE_SYS, text)


async def fix_layout(text: str, cfg: Config) -> str:
    return await _chat(cfg, _FIXLAYOUT_SYS, text)
