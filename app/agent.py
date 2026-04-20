from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

from . import metrics
from .llm import LLM
from .mock_llm import FakeLLM
from .mock_rag import retrieve
from .pii import hash_user_id, PII_PATTERNS, scrub_text, summarize_text
from .tracing import tracing_enabled, get_langfuse_client

try:
    from langfuse.api import ScoreDataType
except Exception:
    class ScoreDataType:
        NUMERIC = "NUMERIC"
        BOOLEAN = "BOOLEAN"
        CATEGORICAL = "CATEGORICAL"

PROMPT_INJECTION_KEYWORDS = [
    "ignore previous",
    "ignore prior",
    "system prompt",
    "jailbreak",
    "dan mode",
    "do anything now",
    "bypass safety",
    "override instructions",
    "forget all instructions",
    "act as unfiltered",
]

PII_PATTERNS_EXTENDED = {
    **PII_PATTERNS,
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card_extended": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "passport": r"\b[A-Za-z]\d{7,8}\b",
    "visa_number": r"\b[A-Z]{2}\d{7}\b",
    "address_keyword": r"(?i)\b(số nhà|đường|phường|quận|huyện|thành phố|tỉnh)\b",
}

def _detect_pii(text: str) -> list[str]:
    found = []
    for name, pattern in PII_PATTERNS_EXTENDED.items():
        if re.search(pattern, text, re.IGNORECASE):
            found.append(name)
    return found

def _detect_injection(text: str) -> list[str]:
    lower = text.lower()
    return [kw for kw in PROMPT_INJECTION_KEYWORDS if kw in lower]

def _compute_relevance(question: str, answer: str) -> float:
    q_tokens = set(question.lower().split())
    a_tokens = set(answer.lower().split())
    if not q_tokens:
        return 0.0
    overlap = q_tokens & a_tokens
    return round(len(overlap) / len(q_tokens), 2)

def _compute_completeness(answer: str, min_len: int = 40, ideal_len: int = 300) -> float:
    length = len(answer.split())
    if length <= 5:
        return 0.1
    if length >= ideal_len:
        return 1.0
    return round(min(1.0, length / ideal_len), 2)

def _compute_safety(pii_found: list[str], injection_found: list[str], answer: str) -> float:
    score = 1.0
    if pii_found:
        score -= 0.3 * len(pii_found)
    if injection_found:
        score -= 0.3 * len(injection_found)
    if "[REDACTED" in answer:
        score -= 0.1
    return round(max(0.0, min(1.0, score)), 2)

def _compute_overall(quality: float, relevance: float, completeness: float, safety: float) -> float:
    weights = {"quality": 0.35, "relevance": 0.25, "completeness": 0.15, "safety": 0.25}
    return round(
        quality * weights["quality"]
        + relevance * weights["relevance"]
        + completeness * weights["completeness"]
        + safety * weights["safety"],
        2,
    )

@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float
    relevance_score: float = 0.0
    completeness_score: float = 0.0
    safety_score: float = 0.0
    overall_score: float = 0.0


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
    PRICE_PER_1K_INPUT = 0.003
    PRICE_PER_1K_OUTPUT = 0.015

    def __init__(self, model: str = "qwen/qwen3-8b") -> None:
        self.model = os.getenv("LLM_MODEL", model)
        use_real_llm = os.getenv("USE_REAL_LLM", "false").lower() == "true"
        if use_real_llm:
            qwen_model = os.getenv("QWEN_MODEL", "qwen3.5-27b")
            self.llm = LLM(model=qwen_model)
            self.model = qwen_model
        else:
            self.llm = FakeLLM(model=self.model)

    def run(self, user_id: str, feature: str, session_id: str, message: str) -> AgentResult:
        started = time.perf_counter()

        pii_found = _detect_pii(message)
        injection_found = _detect_injection(message)

        security_tags: list[str] = []
        if pii_found:
            security_tags.append("pii_detected")
            for p in pii_found:
                security_tags.append(f"pii:{p}")
            metrics.record_pii_leak()
        if injection_found:
            security_tags.append("prompt_injection")
            for inj in injection_found:
                security_tags.append(f"injection:{inj}")
            metrics.record_prompt_injection()

        safe_message = scrub_text(message) if pii_found else message

        docs = retrieve(safe_message)
        prompt = f"Feature={feature}\nDocs={docs}\nQuestion={safe_message}"

        client = get_langfuse_client()
        response = None

        if client is not None and tracing_enabled():
            try:
                with client.start_as_current_observation(
                    name="agent-run",
                    input={"feature": feature, "message_preview": summarize_text(message)},
                    user_id=hash_user_id(user_id),
                    session_id=session_id,
                    tags=[feature] + security_tags,
                    metadata={
                        "model": self.model,
                        "security_flags": security_tags,
                        "pii_types": pii_found,
                        "injection_keywords": injection_found,
                    },
                ) as root_span:
                    with root_span.start_as_current_observation(
                        name="pii-scan",
                        as_type="guardrail",
                        input={"text_preview": summarize_text(message)},
                    ) as pii_span:
                        pii_passed = len(pii_found) == 0
                        pii_span.update(
                            output={"passed": pii_passed, "findings": pii_found},
                            metadata={"scan_type": "pii", "patterns_checked": len(PII_PATTERNS_EXTENDED)},
                        )
                        pii_span.score(
                            name="pii_safety",
                            value=1.0 if pii_passed else 0.0,
                            data_type=ScoreDataType.NUMERIC,
                            comment=f"PII scan: {'clean' if pii_passed else 'found: ' + ', '.join(pii_found)}",
                        )

                    with root_span.start_as_current_observation(
                        name="injection-scan",
                        as_type="guardrail",
                        input={"text_preview": summarize_text(message)},
                    ) as inj_span:
                        inj_passed = len(injection_found) == 0
                        inj_span.update(
                            output={"passed": inj_passed, "findings": injection_found},
                            metadata={"scan_type": "injection", "keywords_checked": len(PROMPT_INJECTION_KEYWORDS)},
                        )
                        inj_span.score(
                            name="injection_safety",
                            value=1.0 if inj_passed else 0.0,
                            data_type=ScoreDataType.NUMERIC,
                            comment=f"Injection scan: {'clean' if inj_passed else 'found: ' + ', '.join(injection_found)}",
                        )

                    with root_span.start_as_current_observation(
                        name="rag-retrieval",
                        as_type="retriever",
                        input={"query_preview": summarize_text(safe_message)},
                    ) as rag_span:
                        rag_span.update(output={"docs_count": len(docs), "docs_preview": [summarize_text(d) for d in docs[:3]]})

                    with root_span.start_as_current_observation(
                        name="llm-call",
                        as_type="generation",
                        model=self.model,
                        input={"prompt_preview": summarize_text(prompt)},
                        model_parameters={"temperature": 0.7, "max_tokens": 512},
                    ) as gen_span:
                        response = self.llm.generate(prompt)
                        cost = self._estimate_cost(response.usage.input_tokens, response.usage.output_tokens)
                        input_cost = (response.usage.input_tokens / 1_000) * self.PRICE_PER_1K_INPUT
                        output_cost = (response.usage.output_tokens / 1_000) * self.PRICE_PER_1K_OUTPUT
                        gen_span.update(
                            output={"text_preview": summarize_text(response.text)},
                            usage_details={
                                "prompt_tokens": response.usage.input_tokens,
                                "completion_tokens": response.usage.output_tokens,
                                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                            },
                            cost_details={
                                "total": cost,
                                "input": round(input_cost, 6),
                                "output": round(output_cost, 6),
                            },
                            metadata={
                                "price_per_1k_input_usd": self.PRICE_PER_1K_INPUT,
                                "price_per_1k_output_usd": self.PRICE_PER_1K_OUTPUT,
                                "cost_currency": "USD",
                            },
                        )

                    with root_span.start_as_current_observation(
                        name="response-validation",
                        as_type="evaluator",
                        input={"response_preview": summarize_text(response.text) if response else ""},
                    ) as eval_span:
                        quality = self._heuristic_quality(message, response.text, docs) if response else 0.0
                        relevance = _compute_relevance(message, response.text) if response else 0.0
                        completeness = _compute_completeness(response.text) if response else 0.0
                        safety = _compute_safety(pii_found, injection_found, response.text) if response else 0.0
                        overall = _compute_overall(quality, relevance, completeness, safety)
                        eval_span.update(
                            output={
                                "quality_score": quality,
                                "relevance_score": relevance,
                                "completeness_score": completeness,
                                "safety_score": safety,
                                "overall_score": overall,
                            },
                            metadata={
                                "answer_length": len(response.text) if response else 0,
                                "answer_word_count": len(response.text.split()) if response else 0,
                                "has_redaction": "[REDACTED" in (response.text if response else ""),
                            },
                        )
                        eval_span.score(name="quality_score", value=quality, data_type=ScoreDataType.NUMERIC, comment="Heuristic quality score")
                        eval_span.score(name="relevance_score", value=relevance, data_type=ScoreDataType.NUMERIC, comment="Keyword overlap relevance")
                        eval_span.score(name="completeness_score", value=completeness, data_type=ScoreDataType.NUMERIC, comment="Answer length completeness")
                        eval_span.score(name="safety_score", value=safety, data_type=ScoreDataType.NUMERIC, comment="PII and injection safety")
                        eval_span.score(name="overall_score", value=overall, data_type=ScoreDataType.NUMERIC, comment="Weighted average of all scores")

                        root_span.score_trace(name="overall_quality", value=overall, data_type=ScoreDataType.NUMERIC, comment="Overall trace quality score")

                    with root_span.start_as_current_observation(
                        name="cost-calculation",
                        as_type="tool",
                        input={
                            "input_tokens": response.usage.input_tokens if response else 0,
                            "output_tokens": response.usage.output_tokens if response else 0,
                        },
                    ) as cost_span:
                        cost_span.update(
                            output={
                                "input_cost_usd": round(input_cost, 6) if response else 0,
                                "output_cost_usd": round(output_cost, 6) if response else 0,
                                "total_cost_usd": cost,
                            },
                            metadata={
                                "pricing_model": "per_token",
                                "input_rate_per_1k": self.PRICE_PER_1K_INPUT,
                                "output_rate_per_1k": self.PRICE_PER_1K_OUTPUT,
                            },
                        )
            except Exception as e:
                from structlog import get_logger
                get_logger().warning("langfuse_trace_failed", error=str(e))
                response = self.llm.generate(prompt)
        else:
            response = self.llm.generate(prompt)

        quality_score = self._heuristic_quality(message, response.text, docs)
        relevance_score = _compute_relevance(message, response.text)
        completeness_score = _compute_completeness(response.text)
        safety_score = _compute_safety(pii_found, injection_found, response.text)
        overall_score = _compute_overall(quality_score, relevance_score, completeness_score, safety_score)
        latency_ms = int((time.perf_counter() - started) * 1000)
        cost_usd = self._estimate_cost(response.usage.input_tokens, response.usage.output_tokens)

        if "[REDACTED" in response.text:
            metrics.record_redaction()

        metrics.record_request(
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
            session_id=session_id,
            feature=feature,
            relevance_score=relevance_score,
            completeness_score=completeness_score,
            safety_score=safety_score,
            overall_score=overall_score,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
            relevance_score=relevance_score,
            completeness_score=completeness_score,
            safety_score=safety_score,
            overall_score=overall_score,
        )

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        pricing = MODEL_PRICING.get(self.model) or MODEL_PRICING["_default"]
        input_cost = (tokens_in / 1_000_000) * pricing["input"]
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
