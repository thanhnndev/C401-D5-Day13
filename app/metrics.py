from __future__ import annotations

import time
from collections import Counter, deque
from statistics import mean

# Time-windowed metrics (last 5 minutes)
WINDOW_SECONDS = 300

REQUEST_LATENCIES: deque[tuple[float, int]] = deque()
REQUEST_COSTS: deque[tuple[float, float]] = deque()
REQUEST_TOKENS_IN: deque[tuple[float, int]] = deque()
REQUEST_TOKENS_OUT: deque[tuple[float, int]] = deque()
QUALITY_SCORES: deque[tuple[float, float]] = deque()
RELEVANCE_SCORES: deque[tuple[float, float]] = deque()
COMPLETENESS_SCORES: deque[tuple[float, float]] = deque()
SAFETY_SCORES: deque[tuple[float, float]] = deque()
OVERALL_SCORES: deque[tuple[float, float]] = deque()
ERRORS: Counter[str] = Counter()
TRAFFIC: deque[tuple[float, int]] = deque()
SESSIONS: dict[str, float] = {}
FEATURE_TRAFFIC: Counter[str] = Counter()

# Security metrics
PII_LEAKS: deque[tuple[float, int]] = deque()
PROMPT_INJECTIONS: deque[tuple[float, int]] = deque()
AUTH_FAILURES: deque[tuple[float, int]] = deque()
REDACTED_COUNT: deque[tuple[float, int]] = deque()


def _prune(deq: deque, window: int = WINDOW_SECONDS) -> None:
    cutoff = time.time() - window
    while deq and deq[0][0] < cutoff:
        deq.popleft()


def _values(deq: deque) -> list:
    _prune(deq)
    return [v for _, v in deq]


def record_request(
    latency_ms: int,
    cost_usd: float,
    tokens_in: int,
    tokens_out: int,
    quality_score: float,
    session_id: str | None = None,
    feature: str | None = None,
    relevance_score: float = 0.0,
    completeness_score: float = 0.0,
    safety_score: float = 0.0,
    overall_score: float = 0.0,
) -> None:
    now = time.time()
    REQUEST_LATENCIES.append((now, latency_ms))
    REQUEST_COSTS.append((now, cost_usd))
    REQUEST_TOKENS_IN.append((now, tokens_in))
    REQUEST_TOKENS_OUT.append((now, tokens_out))
    QUALITY_SCORES.append((now, quality_score))
    RELEVANCE_SCORES.append((now, relevance_score))
    COMPLETENESS_SCORES.append((now, completeness_score))
    SAFETY_SCORES.append((now, safety_score))
    OVERALL_SCORES.append((now, overall_score))
    TRAFFIC.append((now, 1))
    if session_id:
        SESSIONS[session_id] = now
    if feature:
        FEATURE_TRAFFIC[feature] += 1


def record_error(error_type: str) -> None:
    ERRORS[error_type] += 1


def record_pii_leak() -> None:
    PII_LEAKS.append((time.time(), 1))


def record_prompt_injection() -> None:
    PROMPT_INJECTIONS.append((time.time(), 1))


def record_auth_failure() -> None:
    AUTH_FAILURES.append((time.time(), 1))


def record_redaction() -> None:
    REDACTED_COUNT.append((time.time(), 1))


def percentile(values: list[int | float], p: int) -> float:
    items = sorted(v for v in values if v is not None)
    if not items:
        return 0.0
    idx = max(0, min(len(items) - 1, round((p / 100) * len(items) + 0.5) - 1))
    return float(items[idx])


def snapshot() -> dict:
    latencies = _values(REQUEST_LATENCIES)
    costs = _values(REQUEST_COSTS)
    tokens_in = _values(REQUEST_TOKENS_IN)
    tokens_out = _values(REQUEST_TOKENS_OUT)
    quality = _values(QUALITY_SCORES)
    relevance = _values(RELEVANCE_SCORES)
    completeness = _values(COMPLETENESS_SCORES)
    safety = _values(SAFETY_SCORES)
    overall = _values(OVERALL_SCORES)
    traffic = _values(TRAFFIC)

    now = time.time()
    active_sessions = sum(1 for ts in SESSIONS.values() if now - ts < 300)

    total_requests = len(latencies)
    total_errors = sum(ERRORS.values())
    error_rate = (total_errors / total_requests * 100) if total_requests > 0 else 0.0

    # Security metrics
    pii_leak_count = sum(_values(PII_LEAKS))
    prompt_injection_count = sum(_values(PROMPT_INJECTIONS))
    auth_failure_count = sum(_values(AUTH_FAILURES))
    redacted_count = sum(_values(REDACTED_COUNT))
    redaction_rate = (redacted_count / total_requests * 100) if total_requests > 0 else 0.0

    return {
        "request_count": total_requests,
        "rpm": round(len(traffic) / max(1, (WINDOW_SECONDS / 60)), 1),
        "active_sessions": active_sessions,
        "latency_p50_ms": round(percentile(latencies, 50), 1),
        "latency_p95_ms": round(percentile(latencies, 95), 1),
        "latency_p99_ms": round(percentile(latencies, 99), 1),
        "error_rate_pct": round(error_rate, 2),
        "error_breakdown": dict(ERRORS),
        "cost_per_minute_usd": round(sum(costs) / max(1, WINDOW_SECONDS / 60), 4),
        "total_cost_usd": round(sum(costs), 4),
        "tokens_in_per_request": round(mean(tokens_in), 1) if tokens_in else 0,
        "tokens_out_per_request": round(mean(tokens_out), 1) if tokens_out else 0,
        "tokens_in_total": sum(tokens_in),
        "tokens_out_total": sum(tokens_out),
        "quality_score_avg": round(mean(quality), 3) if quality else 0.0,
        "relevance_score_avg": round(mean(relevance), 3) if relevance else 0.0,
        "completeness_score_avg": round(mean(completeness), 3) if completeness else 0.0,
        "safety_score_avg": round(mean(safety), 3) if safety else 0.0,
        "overall_score_avg": round(mean(overall), 3) if overall else 0.0,
        "feature_distribution": dict(FEATURE_TRAFFIC),
        "daily_budget_remaining_pct": round(max(0, (2.5 - sum(costs)) / 2.5 * 100), 1),
        # Security metrics
        "pii_leak_count": pii_leak_count,
        "prompt_injection_count": prompt_injection_count,
        "auth_failure_count": auth_failure_count,
        "redaction_rate_pct": round(redaction_rate, 2),
        "redacted_count": redacted_count,
    }
