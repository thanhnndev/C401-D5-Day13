from __future__ import annotations

import os
import time
from dataclasses import dataclass

from . import metrics
from .llm import LLM
from .mock_rag import retrieve
from .pii import hash_user_id, summarize_text
from .tracing import langfuse_context, observe


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float


# ---------------------------------------------------------------------------
# Pricing table (USD per 1M tokens) — update as needed
# Source: official provider pricing pages
# ---------------------------------------------------------------------------
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Qwen / DashScope (international endpoint)
    "qwen3.5-27b":       {"input": 0.65,  "output": 2.60},
    "qwen-max":          {"input": 1.60,  "output": 6.40},
    "qwen-plus":         {"input": 0.40,  "output": 1.20},
    "qwen-turbo":        {"input": 0.20,  "output": 0.60},
    "qwen-long":         {"input": 0.05,  "output": 0.15},

    # OpenAI
    "gpt-4o":            {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":       {"input": 0.15,  "output": 0.60},
    "gpt-4.1":           {"input": 2.00,  "output": 8.00},
    "gpt-4.1-mini":      {"input": 0.40,  "output": 1.60},
    "gpt-4.1-nano":      {"input": 0.10,  "output": 0.40},
    "o3":                {"input": 10.00, "output": 40.00},
    "o3-mini":           {"input": 1.10,  "output": 4.40},
    "o4-mini":           {"input": 1.10,  "output": 4.40},

    # Anthropic Claude
    "claude-opus-4-5":   {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-5": {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5":  {"input": 0.80,  "output": 4.00},

    # fallback default
    "_default":          {"input": 1.00,  "output": 4.00},
}


class LabAgent:
    def __init__(self, model: str = "qwen3.5-27b") -> None:
        self.model = os.getenv("QWEN_MODEL", model)
        self.llm = LLM(model=self.model)

    @observe()
    def run(self, user_id: str, feature: str, session_id: str, message: str) -> AgentResult:
        started = time.perf_counter()
        docs = retrieve(message)
        prompt = f"Feature={feature}\nDocs={docs}\nQuestion={message}"
        response = self.llm.generate(prompt)
        quality_score = self._heuristic_quality(message, response.text, docs)
        latency_ms = int((time.perf_counter() - started) * 1000)
        cost_usd = self._estimate_cost(response.usage.input_tokens, response.usage.output_tokens)

        langfuse_context.update_current_trace(
            user_id=hash_user_id(user_id),
            session_id=session_id,
            tags=["lab", feature, self.model],
        )
        langfuse_context.update_current_observation(
            metadata={"doc_count": len(docs), "query_preview": summarize_text(message)},
            usage={"input": response.usage.input_tokens, "output": response.usage.output_tokens},
        )

        metrics.record_request(
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
        )

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        pricing = MODEL_PRICING.get(self.model) or MODEL_PRICING["_default"]
        input_cost  = (tokens_in  / 1_000_000) * pricing["input"]
        output_cost = (tokens_out / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(token in answer.lower() for token in question.lower().split()[:3]):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
