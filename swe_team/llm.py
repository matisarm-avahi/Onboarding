"""Provider-independent LLM client abstraction plus Bedrock and scripted fake backends."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

# USD per 1M tokens (input, output). Edit to match current provider pricing.
PRICING = {
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": (3.0, 15.0),
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": (1.0, 5.0),
}
SMART_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
FAST_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    latency_s: float

    @property
    def cost_usd(self) -> float:
        pin, pout = PRICING.get(self.model, (0.0, 0.0))
        return (self.input_tokens * pin + self.output_tokens * pout) / 1_000_000


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str, *, model: str | None = None,
                 max_tokens: int = 4096, temperature: float = 0.0) -> LLMResponse: ...


class BedrockClient:
    def __init__(self, region: str = "us-east-1", default_model: str = SMART_MODEL):
        import boto3
        self._rt = boto3.client("bedrock-runtime", region_name=region)
        self.default_model = default_model

    def complete(self, system, prompt, *, model=None, max_tokens=4096, temperature=0.0):
        model = model or self.default_model
        t0 = time.perf_counter()
        r = self._rt.converse(
            modelId=model,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
        text = "".join(b.get("text", "") for b in r["output"]["message"]["content"])
        u = r["usage"]
        return LLMResponse(text, u["inputTokens"], u["outputTokens"], model,
                           time.perf_counter() - t0)


class FakeClient:
    """Returns scripted replies in order; for offline tests."""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system, prompt, *, model=None, max_tokens=4096, temperature=0.0):
        self.calls.append((system, prompt))
        text = self.replies.pop(0)
        return LLMResponse(text, len(prompt) // 4, len(text) // 4, model or "fake", 0.0)
