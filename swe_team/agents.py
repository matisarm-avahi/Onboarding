"""Shared agent interface: every agent maps (typed input artifacts) -> (typed output artifact)."""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from .llm import LLMClient, LLMResponse


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    max_calls: int = 20
    max_cost_usd: float = 1.0
    max_seconds: float = 600.0
    calls: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    log: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def check(self):
        if (self.calls >= self.max_calls or self.cost_usd >= self.max_cost_usd
                or self.seconds >= self.max_seconds):
            raise BudgetExceeded(f"calls={self.calls} cost=${self.cost_usd:.3f} time={self.seconds:.0f}s")

    def record(self, agent: str, r: LLMResponse):
        with self._lock:
            self.calls += 1
            self.cost_usd += r.cost_usd
            self.seconds += r.latency_s
            self.input_tokens += r.input_tokens
            self.output_tokens += r.output_tokens
            self.log.append({"agent": agent, "model": r.model, "in": r.input_tokens,
                             "out": r.output_tokens, "cost": r.cost_usd, "latency": r.latency_s})


def extract_json(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        return m.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


class Agent:
    name: str = "agent"
    instructions: str = ""
    output_model: type[BaseModel]
    max_tokens: int = 8192  # generated files can be long; truncated JSON fails validation
    model: str | None = None  # None -> client default; routing can override per agent

    def __init__(self, llm: LLMClient, budget: Budget):
        self.llm, self.budget = llm, budget

    def run(self, context: str, *, retries: int = 1) -> BaseModel:
        """context holds only the artifacts this agent needs, not conversation history."""
        schema = json.dumps(self.output_model.model_json_schema())
        system = (f"{self.instructions}\n\nRespond with ONLY a JSON object matching this "
                  f"JSON schema:\n{schema}")
        prompt, err = context, None
        for _ in range(retries + 1):
            self.budget.check()
            if err:
                prompt = f"{context}\n\nYour previous reply was invalid: {err}\nReturn corrected JSON only."
            r = self.llm.complete(system, prompt, model=self.model, max_tokens=self.max_tokens)
            self.budget.record(self.name, r)
            try:
                return self.output_model.model_validate_json(extract_json(r.text))
            except ValidationError as e:
                err = str(e)[:800]
        raise ValueError(f"{self.name}: invalid structured output after retries: {err}")
