"""LLM chat client: enabled gate, response parsing, best-effort failure."""
from __future__ import annotations

import httpx
import pytest

from wayscribe import llm
from wayscribe.config import Config


def _cfg() -> Config:
    return Config(llm_endpoint="http://localhost:9999", llm_model="m")


def test_enabled_requires_endpoint_and_model() -> None:
    assert not llm.enabled(Config())
    assert not llm.enabled(Config(llm_endpoint="http://x"))  # no model
    assert llm.enabled(_cfg())


async def test_spellfix_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_post(self, url, json):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "  fixed text  "}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert await llm.spellfix("fixd txt", _cfg()) == "fixed text"


async def test_translate_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_post(self, url, json):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "hello"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert await llm.translate_to_en("привет", _cfg()) == "hello"


async def test_failure_returns_input(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(self, url, json):
        raise httpx.ConnectError("refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", boom)
    # Best-effort contract: on any error the original text comes back unchanged.
    assert await llm.fix_layout("ghbdtn", _cfg()) == "ghbdtn"
