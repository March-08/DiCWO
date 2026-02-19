"""OpenAI-compatible LLM wrapper with token counting, cost tracking, and retry logic.

Supports OpenAI, OpenRouter, and any provider with an OpenAI-compatible API.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import tiktoken
from openai import OpenAI
from openai import RateLimitError

from src.core.metrics import CallRecord, MetricsCollector


# Pricing per 1M tokens (input, output).
# For OpenRouter models the prices are approximate — actual cost comes from
# the x-openrouter-cost header when available.
_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI direct
    "gpt-4o":             (2.50, 10.00),
    "gpt-4o-mini":        (0.15,  0.60),
    "gpt-4.1":            (2.00,  8.00),
    "gpt-4.1-mini":       (0.40,  1.60),
    "gpt-4.1-nano":       (0.10,  0.40),
    "o3":                 (10.00, 40.00),
    "o4-mini":            (1.10,  4.40),
    # OpenRouter — frontier / strong models
    "openai/gpt-5.2-chat":                 (2.00,  8.00),
    "openai/o3":                           (10.00, 40.00),
    "openai/o4-mini":                      (1.10,  4.40),
    "anthropic/claude-sonnet-4":           (3.00, 15.00),
    "anthropic/claude-opus-4":             (15.00, 75.00),
    "google/gemini-2.5-pro-preview":       (1.25, 10.00),
    # OpenRouter — mid-tier models
    "openai/gpt-4o":                       (2.50, 10.00),
    "openai/gpt-4o-mini":                  (0.15,  0.60),
    "openai/gpt-4.1":                      (2.00,  8.00),
    "openai/gpt-4.1-mini":                 (0.40,  1.60),
    "openai/gpt-4.1-nano":                 (0.10,  0.40),
    "google/gemini-2.5-flash-preview":     (0.15, 0.60),
    "google/gemini-2.0-flash-001":         (0.10, 0.40),
    "deepseek/deepseek-chat-v3-0324":      (0.14, 0.28),
    "deepseek/deepseek-r1":               (0.55, 2.19),
    # OpenRouter — cheap / free models
    "meta-llama/llama-4-scout":            (0.15, 0.60),
    "meta-llama/llama-4-maverick":         (0.20, 0.80),
    "meta-llama/llama-3.3-70b-instruct":       (0.10, 0.30),
    "meta-llama/llama-3.3-70b-instruct:free": (0.00, 0.00),
    "meta-llama/llama-3.1-8b-instruct":       (0.02, 0.05),
    "mistralai/mistral-small-3.1-24b-instruct": (0.10, 0.30),
    "qwen/qwen3-235b-a22b":               (0.20, 0.60),
    "qwen/qwen3-30b-a3b":                 (0.05, 0.15),
}

# Well-known provider base URLs
PROVIDER_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    input_price, output_price = _PRICING.get(model, (1.00, 3.00))
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000


@dataclass
class LLMClient:
    """Thin wrapper around OpenAI-compatible chat completions with automatic metrics.

    Works with OpenAI, OpenRouter, or any compatible endpoint.
    """

    api_key: str
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 16384
    base_url: str | None = None  # None → default OpenAI
    provider: str = "openai"     # "openai" | "openrouter" | custom
    metrics: MetricsCollector = field(default_factory=MetricsCollector)
    progress_callback: Any | None = None  # callable(event_type, data_dict)
    _client: OpenAI = field(init=False, repr=False)
    _encoding: tiktoken.Encoding = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # Resolve base URL
        url = self.base_url or PROVIDER_URLS.get(self.provider)
        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if url:
            kwargs["base_url"] = url

        self._client = OpenAI(**kwargs)

        # tiktoken encoding — fall back to cl100k_base for non-OpenAI models
        try:
            # Strip provider prefix for tiktoken lookup (e.g. "openai/gpt-4o" → "gpt-4o")
            bare_model = self.model.split("/")[-1] if "/" in self.model else self.model
            self._encoding = tiktoken.encoding_for_model(bare_model)
        except KeyError:
            self._encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        return len(self._encoding.encode(text))

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        agent_name: str = "unknown",
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
        response_format: Any | None = None,
    ) -> tuple[str, CallRecord]:
        """Send a chat completion request and return (content, call_record)."""
        model = model or self.model
        temp = temperature if temperature is not None else self.temperature
        max_tok = max_tokens or self.max_tokens

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tok,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        t0 = time.perf_counter()
        for attempt in range(4):
            try:
                response = self._client.chat.completions.create(**kwargs)
                break
            except RateLimitError:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt * 2)
        latency = time.perf_counter() - t0

        choice = response.choices[0]
        content = choice.message.content or ""

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        cost = _estimate_cost(model, prompt_tokens, completion_tokens)

        record = CallRecord(
            agent_name=agent_name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost,
            latency_s=latency,
        )
        self.metrics.record_call(record)

        if self.progress_callback is not None:
            self.progress_callback("llm_call", {
                "agent": agent_name,
                "tokens": record.total_tokens,
                "cost": record.cost_usd,
                "latency": record.latency_s,
                "model": model,
            })

        return content, record
