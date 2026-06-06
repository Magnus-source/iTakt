"""Provider client — thin async wrapper around the Anthropic SDK."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import anthropic

from .config import ModelConfig


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class ProviderResponse:
    content: list[Any]       # list of SDK content blocks
    stop_reason: str
    usage: Usage


class AnthropicProvider:
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        model_cfg: ModelConfig,
    ) -> ProviderResponse:
        kwargs: dict[str, Any] = dict(
            model=model_cfg.model,
            max_tokens=model_cfg.max_tokens,
            temperature=model_cfg.temperature,
            system=system,
            messages=messages,
        )
        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)

        return ProviderResponse(
            content=response.content,
            stop_reason=response.stop_reason or "end_turn",
            usage=Usage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
        )
