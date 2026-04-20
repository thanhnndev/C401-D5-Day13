from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str = Field(..., examples=["u_team_01"])
    session_id: str = Field(..., examples=["s_demo_01"])
    feature: Literal["qa", "summary", "document_review", "visa_check"] = Field(
        default="qa",
        description="Chatbot feature being used",
    )
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    correlation_id: str
    latency_ms: int = Field(..., description="Response time in milliseconds")
    tokens_in: int = Field(..., description="Input tokens consumed")
    tokens_out: int = Field(..., description="Output tokens consumed")
    cost_usd: float = Field(..., description="Cost in USD")
    quality_score: float = Field(..., ge=0, le=1, description="Heuristic quality 0-1")


class LogRecord(BaseModel):
    """Strict schema for JSON logs consumed by dashboard."""

    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: Literal["info", "warning", "error", "critical"]
    service: Literal["api", "agent", "rag", "llm", "control"]
    event: Literal[
        "request_received",
        "response_sent",
        "request_failed",
        "app_started",
        "incident_enabled",
        "incident_disabled",
        "rag_retrieval",
        "llm_generation",
    ]
    correlation_id: str = Field(..., description="Unique request UUID")
    env: str = Field(default="dev")
    user_id_hash: str | None = Field(None, description="SHA256 hashed user ID")
    session_id: str | None = None
    feature: Literal["qa", "summary", "document_review", "visa_check"] | None = None
    model: str | None = None
    latency_ms: int | None = Field(None, ge=0)
    tokens_in: int | None = Field(None, ge=0)
    tokens_out: int | None = Field(None, ge=0)
    cost_usd: float | None = Field(None, ge=0)
    quality_score: float | None = Field(None, ge=0, le=1)
    error_type: Literal["llm_timeout", "rag_empty", "schema_validation", "pii_blocked"] | None = None
    tool_name: str | None = None
    rag_docs_count: int | None = Field(None, ge=0, description="Number of documents retrieved by RAG")
    payload: dict[str, Any] | None = None
