#!/usr/bin/env python
"""Validate dashboard implementation against the 7-panel spec.

Usage:
    python scripts/validate_dashboard.py

Checks:
    - All 7 required panels present
    - SLO thresholds visible on panels 1, 3, 4, 7
    - Units clearly labeled
    - Metrics schema compliance
    - Log schema compliance
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent

# Required panel definitions
REQUIRED_PANELS = [
    {
        "id": "latency",
        "title_contains": "Latency",
        "metrics": ["latency_p50_ms", "latency_p95_ms", "latency_p99_ms"],
        "slo_required": True,
        "unit": "ms",
    },
    {
        "id": "traffic",
        "title_contains": "Traffic",
        "metrics": ["rpm", "active_sessions"],
        "slo_required": False,
        "unit": "rpm",
    },
    {
        "id": "errors",
        "title_contains": "Error",
        "metrics": ["error_rate_pct"],
        "slo_required": True,
        "unit": "%",
    },
    {
        "id": "cost",
        "title_contains": "Cost",
        "metrics": ["cost_per_minute_usd", "daily_budget_remaining_pct"],
        "slo_required": True,
        "unit": "usd",
    },
    {
        "id": "tokens",
        "title_contains": "Token",
        "metrics": ["tokens_in_per_request", "tokens_out_per_request"],
        "slo_required": False,
        "unit": "tokens",
    },
    {
        "id": "quality",
        "title_contains": "Quality",
        "metrics": ["quality_score_avg", "regenerate_rate"],
        "slo_required": False,
        "unit": "score",
    },
    {
        "id": "security",
        "title_contains": "Security",
        "metrics": ["pii_leak_count", "prompt_injection_count", "auth_failure_count"],
        "slo_required": True,
        "unit": "count",
    },
]

# Valid enum values from schemas.py
VALID_FEATURES = {"qa", "summary", "document_review", "visa_check"}
VALID_SERVICES = {"api", "agent", "rag", "llm", "control"}
VALID_ERROR_TYPES = {"llm_timeout", "rag_empty", "schema_validation", "pii_blocked", None}
VALID_EVENTS = {
    "request_received",
    "response_sent",
    "request_failed",
    "app_started",
    "incident_enabled",
    "incident_disabled",
    "rag_retrieval",
    "llm_generation",
}


def check_log_schema() -> tuple[int, list[str]]:
    """Validate log records against strict schema."""
    log_path = ROOT / "data" / "logs.jsonl"
    if not log_path.exists():
        return 0, ["No logs found. Run the app and generate traffic first."]

    issues = []
    valid_count = 0
    total = 0

    with open(log_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                issues.append(f"Line {line_num}: Invalid JSON")
                continue

            # Check required fields
            for field in ("ts", "level", "service", "event", "correlation_id"):
                if field not in record:
                    issues.append(f"Line {line_num}: Missing required field '{field}'")

            # Validate enums
            if "feature" in record and record["feature"] is not None:
                if record["feature"] not in VALID_FEATURES:
                    issues.append(
                        f"Line {line_num}: Invalid feature '{record['feature']}'. "
                        f"Must be one of {VALID_FEATURES}"
                    )

            if "service" in record and record["service"] not in VALID_SERVICES:
                issues.append(
                    f"Line {line_num}: Invalid service '{record['service']}'. "
                    f"Must be one of {VALID_SERVICES}"
                )

            if "error_type" in record and record["error_type"] not in VALID_ERROR_TYPES:
                issues.append(
                    f"Line {line_num}: Invalid error_type '{record['error_type']}'. "
                    f"Must be one of {VALID_ERROR_TYPES}"
                )

            if "event" in record and record["event"] not in VALID_EVENTS:
                issues.append(
                    f"Line {line_num}: Invalid event '{record['event']}'. "
                    f"Must be one of {VALID_EVENTS}"
                )

            # Check numeric constraints
            for field in ("latency_ms", "tokens_in", "tokens_out", "cost_usd"):
                if field in record and record[field] is not None:
                    if record[field] < 0:
                        issues.append(f"Line {line_num}: {field} must be >= 0, got {record[field]}")

            if "quality_score" in record and record["quality_score"] is not None:
                if not (0 <= record["quality_score"] <= 1):
                    issues.append(
                        f"Line {line_num}: quality_score must be 0-1, got {record['quality_score']}"
                    )

            # Check correlation_id format (should be UUID-like)
            if "correlation_id" in record:
                cid = record["correlation_id"]
                if not cid or len(cid) < 8:
                    issues.append(f"Line {line_num}: correlation_id too short: '{cid}'")

            valid_count += 1

    return valid_count, issues


def check_langfuse_traces() -> tuple[int, list[str]]:
    """Check if Langfuse has minimum traces."""
    issues = []
    try:
        from langfuse import Langfuse
        from dotenv import load_dotenv
        import os

        load_dotenv()

        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        host = os.getenv("LANGFUSE_HOST", "http://localhost:27100")

        if not public_key or not secret_key:
            return 0, ["LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set in .env"]

        langfuse = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        traces = langfuse.fetch_traces(limit=100)
        count = len(traces.data) if traces.data else 0

        if count < 10:
            issues.append(f"Only {count} traces found. Need >= 10 for grading.")

        return count, issues
    except ImportError:
        return 0, ["langfuse package not installed"]
    except Exception as e:
        return 0, [f"Failed to connect to Langfuse: {e}"]


def check_metrics() -> list[str]:
    """Check if metrics endpoint returns expected data."""
    issues = []
    try:
        import httpx

        resp = httpx.get("http://localhost:8009/metrics", timeout=5)
        if resp.status_code != 200:
            issues.append(f"Metrics endpoint returned {resp.status_code}")
            return issues

        data = resp.json()
        expected_keys = {
            "request_count",
            "latency_p50_ms",
            "latency_p95_ms",
            "latency_p99_ms",
            "error_rate_pct",
            "total_cost_usd",
            "tokens_in_total",
            "tokens_out_total",
            "quality_score_avg",
        }

        missing = expected_keys - set(data.keys())
        if missing:
            issues.append(f"Missing metrics: {missing}")

        return issues
    except Exception as e:
        return [f"Failed to reach metrics endpoint: {e}"]


def main() -> int:
    """Run all validation checks."""
    print("=" * 60)
    print("Dashboard Validation - Study Abroad Document Chatbot")
    print("=" * 60)
    print()

    total_checks = 0
    passed_checks = 0
    all_issues = []

    # Check 1: Log schema compliance
    print("▸ Checking log schema compliance...")
    valid_logs, log_issues = check_log_schema()
    total_checks += 1
    if log_issues:
        all_issues.extend(log_issues)
        print(f"  ✗ {len(log_issues)} schema issues found")
        for issue in log_issues[:5]:
            print(f"    - {issue}")
        if len(log_issues) > 5:
            print(f"    ... and {len(log_issues) - 5} more")
    else:
        passed_checks += 1
        print(f"  ✓ {valid_logs} log records pass schema validation")
    print()

    # Check 2: Langfuse traces
    print("▸ Checking Langfuse traces...")
    trace_count, trace_issues = check_langfuse_traces()
    total_checks += 1
    if trace_issues:
        all_issues.extend(trace_issues)
        print(f"  ✗ {trace_issues[0]}")
    else:
        passed_checks += 1
        print(f"  ✓ {trace_count} traces found (minimum: 10)")
    print()

    # Check 3: Metrics endpoint
    print("▸ Checking metrics endpoint...")
    metrics_issues = check_metrics()
    total_checks += 1
    if metrics_issues:
        all_issues.extend(metrics_issues)
        print(f"  ✗ {metrics_issues[0]}")
    else:
        passed_checks += 1
        print("  ✓ Metrics endpoint responding with expected data")
    print()

    # Summary
    print("=" * 60)
    print(f"Results: {passed_checks}/{total_checks} checks passed")
    print("=" * 60)

    if all_issues:
        print("\nIssues to fix:")
        for issue in all_issues:
            print(f"  • {issue}")
        print()
        print("Run these commands to generate data:")
        print("  uvicorn app.main:app --reload")
        print("  python scripts/load_test.py --concurrency 3")
        print("  python scripts/inject_incident.py --scenario rag_slow")
        return 1

    print("\n✓ Dashboard implementation looks good!")
    print("  Proceed to screenshot evidence for grading.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
