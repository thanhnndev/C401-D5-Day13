# Day 13 Observability Lab Report

> **Instruction**: Fill in all sections below. This report is designed to be parsed by an automated grading assistant. Ensure all tags (e.g., `[GROUP_NAME]`) are preserved.

## 1. Team Metadata

- [GROUP_NAME]: C401-D5.1
- [REPO_URL]: https://github.com/thanhnndev/C401-D5-Day13
- [MEMBERS]:
  - Nông Nguyễn Thành | MSSV: 2A202600250 | Role: Full-Stack Observability
  - Đào Phước Thịnh | MSSV: 2A202600029 | Role: Dashboard & Metrics
  - Nguyễn Tri Nhân | MSSV: 2A202600224 | Role: Mock Data, Logging & LLM Pipeline (mock_rag, sample_queries, logging_config, middleware, LLM integration)

---

## 2. Group Performance (Auto-Verified)

- [VALIDATE_LOGS_FINAL_SCORE]: 95/100
- [TOTAL_TRACES_COUNT]: Mỗi request tạo 1 trace với 7 spans qua `client.start_as_current_observation()` trong `app/agent.py:180-315`
- [PII_LEAKS_FOUND]: 0 (PII được scrub trước khi ghi log qua `scrub_event` processor)

---

## 3. Technical Evidence (Group)

### 3.1 Logging & Tracing

- [EVIDENCE_CORRELATION_ID_SCREENSHOT]: Correlation ID format `req-{hex8}` trong response headers và log lines (`app/middleware.py:15-25`)
- [EVIDENCE_PII_REDACTION_SCREENSHOT]: 7 patterns scrubbed → `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`, etc. (`app/pii.py:6-14`, `app/logging_config.py:25-33`)
- [EVIDENCE_TRACE_WATERFALL_SCREENSHOT]: 7-span trace hierarchy trong `app/agent.py:180-315` (agent-run, pii-scan, injection-scan, rag-retrieval, llm-call, response-validation, cost-calculation)
- [TRACE_WATERFALL_EXPLANATION]: Span **llm-call** (generation) ghi nhận đầy đủ `usage_details` (prompt_tokens, completion_tokens, total_tokens) và `cost_details` (total, input, output USD) với model_parameters (temperature=0.7, max_tokens=512)

### 3.2 Dashboard & SLOs

- [DASHBOARD_7_PANELS_SCREENSHOT]: Streamlit 3-tab dashboard (`app/dashboard.py:1-381`) — Layer 1: Executive Overview (health badge, 4 KPIs, traffic velocity), Layer 2: Engineering Detail (5 Golden Signals với SLO lines), Layer 3: Debug Investigation (log search, Correlation Explorer)
- [SLO_TABLE]:
  | SLI | Target | Window | Current Value |
  |---|---:|---|---:|
  | Latency P95 | < 3000ms | 28d | `percentile(latencies, 95)` từ `REQUEST_LATENCIES` deque (5-min window) |
  | Error Rate | < 2% | 28d | `(total_errors / total_requests * 100)` từ `ERRORS` Counter |
  | Cost Budget | < $2.5/day | 1d | `daily_budget_remaining_pct = max(0, (2.5 - sum(costs)) / 2.5 * 100)` |
  | PII Leaks | 0 | 28d | 0 — PII scrubbed trước khi ghi log |
  | Prompt Injections | 0 | 28d | Phát hiện qua 10 keywords trong `_detect_injection()` |

### 3.3 Alerts & Runbook

- [ALERT_RULES_SCREENSHOT]: 9 rules trong `config/alert_rules.yaml` — 5 standard (high_latency_p95, high_error_rate, cost_budget_spike, low_quality_score, high_regenerate_rate) + 4 security (pii_leak_detected, prompt_injection_detected, unauthorized_access_attempt, data_exfiltration_risk)
- [SAMPLE_RUNBOOK_LINK]: docs/alerts.md (Vietnamese runbook với 9 rules, mỗi rule có severity, triggers, impact, first checks, mitigation actions)

---

## 4. Incident Response (Group)

- [SCENARIO_NAME]: rag_slow (RAG retrieval latency spike)
- [SYMPTOMS_OBSERVED]: P95 latency vượt 3000ms do `time.sleep(2.5)` trong `mock_rag.py:23-24`, quality score giảm, cost_per_minute tăng
- [ROOT_CAUSE_PROVED_BY]: Span `rag-retrieval` trong Langfuse trace có duration ~2500ms (bình thường < 10ms), correlation_id correlate với log lines có `latency_ms` > 3000 trong `data/logs.jsonl`
- [FIX_ACTION]: `POST /incidents/rag_slow/disable`, implement RAG timeout (1s), fallback sang cached responses
- [PREVENTIVE_MEASURE]: Alert rule `high_latency_p95` (P2) cảnh báo sớm, circuit breaker pattern cho RAG retrieval, monitoring retrieval latency trong traces

---

## 5. Individual Contributions & Evidence

### [Đào Phước Thịnh - 2A202600029] - Vai trò: Dashboard

- [TASKS_COMPLETED]:
  - Thiết kế và triển khai Dashboard giám sát 7-panel bằng Streamlit và Altair, đảm bảo tính trực quan và khả năng quan sát (Observability) toàn diện.
  - Xây dựng hệ thống Metric Performance chuyên sâu: Triển khai tính toán các phân vị Latency (P50, P95, P99) kèm theo đường ngưỡng SLO (Service Level Objective) để nhận diện nhanh các điểm nghẽn hiệu năng.
  - Tích hợp giám sát tài nguyên LLM: Xây dựng biểu đồ theo dõi Cost (USD) và Token Throughput theo thời gian thực, giúp kiểm soát ngân sách và mức độ sử dụng mô hình.
  - Phát triển tính năng "Correlation Explorer": Cho phép truy xuất toàn bộ vòng đời của một request dựa trên Correlation ID, hỗ trợ quá trình Debug và điều tra sự cố (Incident Investigation) một cách chính xác.
  - Tối ưu hóa UI/UX: Trải qua nhiều phiên bản tinh chỉnh bố cục (Layout) để tạo ra giao diện phân cấp thông tin rõ ràng (Executive Overview -> Performance Metrics -> Debug Details).
- [EVIDENCE_LINK]: "app/dashboard.py" | "evidence/"

### [Nông Nguyễn Thành - 2A202600250] - Vai trò: Full-Stack Observability

- [TASKS_COMPLETED]:
  - Cấu hình structlog pipeline với 7 processors, PII scrubbing trước khi ghi JSONL, correlation ID middleware (req-{hex8}).
  - Thiết kế 7 PII patterns (email, phone_vn, cccd, credit_card, passport, visa_number, address_keyword) với regex và scrubbing.
  - Tích hợp Langfuse client với 6-span trace hierarchy (agent-run, pii-scan, injection-scan, rag-retrieval, llm-call, response-validation, cost-calculation).
  - Triển khai 5 quality scores (quality, relevance, completeness, safety, overall) với weighted scoring và Langfuse `span.score()`.
  - Xây dựng 9 alert rules (5 standard + 4 security) với Vietnamese runbook chi tiết.
  - Phát triển 7-panel dashboard (Streamlit + Altair) với 3-layer design (Executive → Engineering → Debug).
  - Cấu hình Docker Compose 6 containers (Langfuse stack) với custom ports 27xxx.
  - Tích hợp LM Studio native API + Real LLM (DashScope/Qwen) với MODEL_PRICING table (16 models).
  - Xử lý merge conflict resolution cho 7 files, viết load test và dashboard validation scripts.
- [EVIDENCE_LINK]: "docs/reports/2A202600250_NongNguyenThanh_individual_report.md" | "app/agent.py" | "app/tracing.py" | "app/metrics.py" | "app/mock_llm.py" | "config/alert_rules.yaml" | "docker-compose.yml"

### Nguyễn Tri Nhân - 2A202600224 - Vai trò: Mock Data, Logging & LLM Pipeline

- [TASKS_COMPLETED]:
  - **Mock data creation** (commit "docs: create mock data for chatbot for onboarder"): Xây dựng `data/sample_queries.jsonl` chứa bộ câu hỏi mẫu về du học, phát triển `app/mock_rag.py` — RAG retrieval với domain documents và incident-aware latency
  - **Logging & middleware configuration** (commit "feat: configure logging and middeleware for Streamlit dashboard"): Triển khai `app/logging_config.py` — structlog pipeline với processor chain, `app/middleware.py` — `CorrelationIdMiddleware` (req-{hex8}, bind_contextvars, x-request-id propagation)
  - **LLM pipeline integration** (commit "feat: run full pipeline cho my chatbot"): Phát triển `app/llm.py` — DashScope/Qwen wrapper, `app/agent.py` pipeline orchestration với 7-span trace hierarchy
  - **Full pipeline implementation**: End-to-end chat flow từ request → PII/injection scan → RAG retrieval → LLM generation → response validation → cost calculation → JSONL logging
- [EVIDENCE_LINK]: "data/sample_queries.jsonl" | "app/mock_rag.py" | "app/logging_config.py" | "app/middleware.py" | "app/llm.py" | "app/agent.py"

---

## 6. Bonus Items (Optional)

- [BONUS_COST_OPTIMIZATION]: (Description + Evidence)
- [BONUS_AUDIT_LOGS]: (Description + Evidence)
- [BONUS_CUSTOM_METRIC]: (Description + Evidence)
