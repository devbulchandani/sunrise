"""Provider-agnostic LLM client.

Supports:
- any OpenAI-compatible chat completions endpoint (OpenAI, OpenRouter, NVIDIA NIM)
- Anthropic messages API

Implemented directly over httpx so no SDK lock-in. All calls request strict
JSON output and parse through Pydantic schemas.
"""

import json
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("llm")

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


def _extract_json(text: str | None) -> Any:
    """Best-effort extraction of a JSON object/array from an LLM response."""
    if not text or not text.strip():
        raise LLMError("LLM returned an empty response (possibly rate limited)")
    text = text.strip()
    # reasoning models may emit <think>...</think> blocks; drop them first
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # strip markdown fences
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # find first { ... last }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidate_text = text[start : end + 1]
        try:
            return json.loads(candidate_text)
        except json.JSONDecodeError:
            pass
        # repair truncated JSON: close any unclosed braces/brackets,
        # trimming back to the last complete value first
        trimmed = candidate_text.rstrip().rstrip(",")
        for _ in range(6):
            repaired = trimmed + "]" * max(0, _unclosed(trimmed, "["))
            repaired += "}" * max(0, _unclosed(repaired, "{"))
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                # drop the trailing incomplete token and retry
                trimmed = re.sub(r'[,:"\w\s.\-]*$', "", trimmed).rstrip().rstrip(",") or "{}"
    raise LLMError(f"could not parse JSON from LLM response: {text[:200]}")


def _unclosed(text: str, opener: str) -> int:
    closer = {"{": "}", "[": "]"}[opener]
    depth = 0
    in_str = False
    esc = False
    for ch in text:
        if esc:
            esc = False
            continue
        if ch == "\"":
            in_str = not in_str
            continue
        if in_str:
            if ch == "\\":
                esc = True
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
    return depth


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.llm_api_key)

    async def complete(self, system: str, user: str, max_tokens: int = 2000) -> str:
        if not self.configured:
            raise LLMError("LLM_API_KEY not configured")
        if self.settings.llm_no_think and not system.startswith("/no_think"):
            # Nemotron-style reasoning models: /no_think keeps the whole token
            # budget for the actual answer instead of burning it on chain-of-thought
            system = "/no_think\n" + system
        if self.settings.llm_provider == "anthropic":
            return await self._complete_anthropic(system, user, max_tokens)
        return await self._complete_openai(system, user, max_tokens)

    async def _complete_openai(self, system: str, user: str, max_tokens: int) -> str:
        base = (
            self.settings.llm_base_url.rstrip("/")
            if self.settings.llm_base_url
            else "https://api.openai.com/v1"
        )
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.settings.llm_no_think:
            # NVIDIA NIM reasoning models (Nemotron family): disable
            # chain-of-thought so the budget goes to the actual answer
            payload["chat_template_kwargs"] = {"thinking": False}
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        import asyncio as _asyncio

        last_error = "unknown"
        for attempt in range(3):
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    f"{base}/chat/completions", json=payload, headers=headers
                )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            if resp.status_code in (400, 422) and "chat_template_kwargs" in payload:
                # gateway rejected the NIM-specific toggle — retry plain
                log.warn("llm.think_toggle_rejected", status=resp.status_code)
                payload = {k: v for k, v in payload.items() if k != "chat_template_kwargs"}
                continue
            last_error = f"LLM HTTP {resp.status_code}: {resp.text[:300]}"
            if resp.status_code == 402:
                log.error("llm.credits_exhausted", hint="top up at https://openrouter.ai/settings")
            if resp.status_code == 429 and attempt < 2:
                wait = 10 * (attempt + 1)
                log.warn("llm.rate_limited", retry_in=wait)
                await _asyncio.sleep(wait)
                continue
            break
        raise LLMError(last_error)

    async def _complete_anthropic(self, system: str, user: str, max_tokens: int) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.settings.llm_api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": self.settings.llm_model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
        if resp.status_code != 200:
            raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return "".join(block.get("text", "") for block in data.get("content", []))

    async def structured(
        self, schema: type[T], system: str, user: str, max_tokens: int = 2000
    ) -> T:
        raw = await self.complete(system, user, max_tokens=max_tokens)
        try:
            return schema.model_validate(_extract_json(raw))
        except ValidationError as exc:
            raise LLMError(f"LLM output failed schema validation: {exc}") from exc
        except LLMError:
            # likely a reasoning model that spent the budget thinking and
            # truncated its JSON — retry once with double headroom
            raw2 = await self.complete(
                system + "\nSkip all reasoning. Output ONLY the JSON object.",
                user,
                max_tokens=max_tokens * 2,
            )
            try:
                return schema.model_validate(_extract_json(raw2))
            except (ValidationError, LLMError) as exc2:
                raise LLMError(
                    f"structured output failed after retry ({exc2})"
                ) from exc2


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
