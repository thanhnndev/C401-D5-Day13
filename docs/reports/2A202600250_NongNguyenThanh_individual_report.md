# Báo Cáo Cá Nhân - Day 13 Observability Lab

## Thông Tin Sinh Viên

- **Họ tên**: Nông Nguyễn Thành
- **MSSV**: 2A202600250
- **Vai trò**: Full-Stack Observability Engineer (đóng góp xuyên suốt 5 lớp hệ thống)

---

## [TASKS_COMPLETED]

### Lớp 1 - Logging & PII Protection

- Cấu hình **structlog** với pipeline 7 processors: `merge_contextvars` → `add_log_level` → `TimeStamper` (ISO format, UTC) → `scrub_event` (PII scrubbing) → `StackInfoRenderer` → `format_exc_info` → `JsonlFileProcessor` → `JSONRenderer`. Pipeline này đảm bảo mọi log line đều có correlation_id, timestamp chuẩn ISO, và được scrub PII trước khi ghi.
- Triển khai **CorrelationIdMiddleware** (`app/middleware.py:11-28`) sử dụng `BaseHTTPMiddleware` của Starlette, tạo UUID dạng `req-{hex8}` cho mỗi request, bind vào `structlog.contextvars` qua `bind_contextvars(correlation_id=...)`, và propagate qua response headers `x-request-id` + `x-response-time-ms`.
- Thiết kế **7 PII patterns** trong `app/pii.py:6-14`: `email` (RFC-style regex), `phone_vn` (hỗ trợ +84 và 0xxx), `cccd` (12 chữ số), `credit_card` (16 số với separator), `passport` (1 letter + 7-8 digits), `visa_number` (2 uppercase letters + 7 digits), `address_keyword` (tiếng Việt: số nhà, đường, phường, quận, huyện, thành phố, tỉnh).
- Xây dựng hàm `scrub_text()` thay thế PII bằng `[REDACTED_{TYPE}]` và `summarize_text()` cắt preview tối đa 80 ký tự sau khi scrub. Hàm `hash_user_id()` dùng SHA-256 để anonymize user ID (lấy 12 ký tự đầu).
- Tích hợp **PII scrubber** vào structlog pipeline qua processor `scrub_event` (`app/logging_config.py:25-33`), scrub cả trường `event` và toàn bộ `payload` dict.
- Cấu hình **JSONL log output** qua `JsonlFileProcessor` (`app/logging_config.py:16-22`), ghi log vào `data/logs.jsonl` với encoding UTF-8, auto-create thư mục nếu chưa tồn tại.
- Triển khai **log enrichment** với context variables (`app/main.py:56-61`): bind `user_id_hash`, `session_id`, `feature`, `model`, `env` vào mọi log line trong scope của request.

### Lớp 2 - Tracing & Enrichment

- Tích hợp **Langfuse client** (`app/tracing.py:6-54`) với `LANGFUSE_BASE_URL` (default `http://localhost:27100`), hỗ trợ graceful fallback qua `_DummyLangfuse` và `_DummySpan` khi Langfuse không khả dụng.
- Xây dựng **6-span trace hierarchy** trong `app/agent.py:180-315`:
  - **agent-run** (root span): chứa metadata `model`, `security_flags`, `pii_types`, `injection_keywords`, gắn `user_id` (hashed), `session_id`, `tags`.
  - **pii-scan** (guardrail): ghi nhận kết quả PII scan với `pii_safety` score (0.0 hoặc 1.0).
  - **injection-scan** (guardrail): phát hiện prompt injection keywords (10 keywords: "ignore previous", "system prompt", "jailbreak", "dan mode", v.v.) với `injection_safety` score.
  - **rag-retrieval** (retriever): ghi nhận số lượng docs retrieved và preview.
  - **llm-call** (generation): span quan trọng nhất với `model_parameters` (temperature, max_tokens), `usage_details` (prompt_tokens, completion_tokens, total_tokens), `cost_details` (total, input, output USD).
  - **response-validation** (evaluator): tính và ghi nhận 5 quality scores.
  - **cost-calculation** (tool): breakdown chi tiết input/output cost với pricing metadata.
- Gắn **user_id/session_id/tags** lên mọi trace: `user_id` được hash SHA-256 (12 chars), `session_id` giữ nguyên, `tags` bao gồm feature type + security flags (ví dụ: `["qa", "pii_detected", "pii:email"]`).
- Triển khai **generation span** với đầy đủ `usage_details` và `cost_details` (`app/agent.py:245-262`), bao gồm metadata `price_per_1k_input_usd`, `price_per_1k_output_usd`, `cost_currency`.
- Xây dựng **security guardrail spans** cho PII và injection detection (`app/agent.py:193-225`), mỗi span có `output.passed`, `output.findings`, `metadata.scan_type`, và numeric score.
- Cấu hình **atexit shutdown handler** (`app/main.py:28-29`) để đảm bảo Langfuse client flush toàn bộ traces trước khi process terminate.

### Lớp 3 - SLOs & Alerts

- Triển khai **time-windowed metrics** (`app/metrics.py:8-28`) với cửa sổ 5 phút (`WINDOW_SECONDS = 300`), sử dụng `deque` với `(timestamp, value)` tuples và hàm `_prune()` tự động loại bỏ dữ liệu cũ.
- Tính toán **Latency P50/P95/P99** (`app/metrics.py:92-97`, `130-132`) qua hàm `percentile()` với algorithm sorted-index, trả về giá trị chính xác cho từng phân vị.
- Theo dõi **error rate** (`app/metrics.py:116-117`): `error_rate_pct = (total_errors / total_requests * 100)`, breakdown theo `error_type` qua `Counter`.
- Triển khai **cost tracking** (`app/metrics.py:135-136`): `cost_per_minute_usd` (tổng cost chia cho window), `total_cost_usd`, `daily_budget_remaining_pct` (so với ngân sách $2.5/ngày).
- Theo dõi **token usage** (`app/metrics.py:137-140`): `tokens_in_per_request`, `tokens_out_per_request`, `tokens_in_total`, `tokens_out_total`.
- Xây dựng **5 quality scores** (`app/metrics.py:141-145`):
  - `quality_score_avg` - Heuristic quality (0-1)
  - `relevance_score_avg` - Keyword overlap giữa question và answer
  - `completeness_score_avg` - Độ dài answer so với ideal (300 words)
  - `safety_score_avg` - PII và injection safety
  - `overall_score_avg` - Weighted average (quality: 35%, relevance: 25%, completeness: 15%, safety: 25%)
- Triển khai **security metrics** (`app/metrics.py:24-28`, `149-153`): `pii_leak_count`, `prompt_injection_count`, `auth_failure_count`, `redaction_rate_pct`, `redacted_count`.
- Cấu hình **9 alert rules** trong `config/alert_rules.yaml`:
  - 5 standard alerts: `high_latency_p95` (P2), `high_error_rate` (P1), `cost_budget_spike` (P2), `low_quality_score` (P2), `high_regenerate_rate` (P3).
  - 4 security alerts: `pii_leak_detected` (P1), `prompt_injection_detected` (P1), `unauthorized_access_attempt` (P1), `data_exfiltration_risk` (P1).
- Viết **Vietnamese alert runbook** (`docs/alerts.md`) với đầy đủ 9 rules, mỗi rule có: severity, trigger condition, impact description, first checks (3 bước), mitigation actions (3 bước), và dashboard panel reference. Security alerts bổ sung thêm compliance notes (GDPR, FERPA) và common attack patterns.

### Lớp 4 - Load Test & Dashboard

- Xây dựng **load test script** (`scripts/load_test.py`) với **realistic study-abroad queries** cho 4 features:
  - `qa`: Visa du học Mỹ, học bổng Úc, IELTS yêu cầu, chi phí Singapore.
  - `summary`: Tóm tắt visa Đức, học bổng MEXT Nhật, công nhận bằng Úc.
  - `document_review`: Review SOP Harvard, CV exchange, thư giới thiệu.
  - `visa_check`: Visa Hàn Quốc D-2, F-1 Mỹ chứng minh tài chính, Úc subclass 500.
- Hỗ trợ **concurrent execution** qua `ThreadPoolExecutor` với configurable `--concurrency`, `--count`, `--duration`, và `--scenario` flags.
- Triển khai **7-panel Dashboard** (`app/dashboard.py`) bằng Streamlit + Altair với 3 tabs:
  - **Layer 1: Executive Overview** - Health badge (HEALTHY/DEGRADED/CRITICAL), 4 KPI metrics (Total Requests, P99 Latency, Total Cost, Avg Quality), Traffic Velocity chart (Altair area với gradient).
  - **Layer 2: Engineering Detail** - 5 Golden Signals: Latency (P50/P95/P99 với SLO line), Traffic (QPS smoothed), Error Rate (với SLO line + breakdown bar chart), Cost Trend (area gradient), Token Throughput (tokens in/out line chart). Bổ sung Cost by Feature (pie chart) và Feature Distribution (bar chart).
  - **Layer 3: Debug Investigation** - Log search/filter (by level, feature, text), full log table với column config, **Correlation Explorer** cho phép trace toàn bộ lifecycle của một request qua correlation ID.
- Thiết kế **design system** với CSS custom: Fira Code + Fira Sans fonts, dark theme (#0F172A background), metric cards với border/shadow, health badge với 3 trạng thái màu (green/amber/red).
- Xây dựng **dashboard validation script** (`scripts/validate_dashboard.py`) kiểm tra 3 aspects: log schema compliance (required fields, enum validation, numeric constraints, correlation_id format), Langfuse traces count (>= 10 minimum), metrics endpoint response (9 expected keys).

### Lớp 5 - Infrastructure & Integration

- Cấu hình **Docker Compose** (`docker-compose.yml`) với **6 containers** cho Langfuse stack:
  - `langfuse-web` (port 27100): Web UI với auto-init org/project/user.
  - `langfuse-worker` (port 27130): Background worker với đầy đủ S3/ClickHouse/Redis config.
  - `postgres` (port 27433): Database với health check `pg_isready`.
  - `clickhouse` (ports 27124/27001): Analytics engine với HTTP và native interfaces.
  - `minio` (ports 27092/27093): S3-compatible object storage cho event/media uploads.
  - `redis` (port 27380): Cache/queue với `requirepass` và `noeviction` policy.
- Tích hợp **LM Studio native API** (`app/mock_llm.py:45-75`): gọi endpoint `/api/v1/chat` với JSON payload, parse response theo LM Studio format (`output[].content`, `stats.input_tokens`, `stats.total_output_tokens`), fallback sang deterministic responses khi LM Studio không khả dụng.
- Triển khai **Real LLM integration** (`app/llm.py`): gọi DashScope/Qwen qua OpenAI-compatible REST API, system prompt được build từ 3 sources (company_policy.md, Q&A corpus, alerts.md runbooks), hỗ trợ `enable_thinking: false` cho Qwen3, loại bỏ `<think>` tags từ response.
- Xây dựng **MODEL_PRICING table** (`app/agent.py:110-135`) với **16 models**:
  - Qwen/DashScope: qwen3.5-27b, qwen-max, qwen-plus, qwen-turbo, qwen-long.
  - OpenAI: gpt-4o, gpt-4o-mini, gpt-4.1, gpt-4.1-mini, gpt-4.1-nano, o3, o3-mini, o4-mini.
  - Anthropic: claude-opus-4-5, claude-sonnet-4-5, claude-haiku-4-5.
  - Default fallback: _default.
- Triển khai **USE_REAL_LLM toggle** (`app/agent.py:144-150`): khi `USE_REAL_LLM=true` thì dùng `LLM` class (DashScope), ngược lại dùng `FakeLLM` (LM Studio/fallback).
- Xử lý **merge conflict resolution** xuyên suốt 7 files: `app/main.py` (duplicate bind_contextvars), `app/logging_config.py` (PII scrubber pipeline), `app/middleware.py` (correlation ID), `app/pii.py` (merged PII patterns), `app/agent.py` (MODEL_PRICING + LLM + tracing integration), `app/tracing.py` (simplified client), `.env.example` (Langfuse host + LM Studio config).

---

## [EVIDENCE_LINK]

| Component | File | Lines |
|---|---|---|
| Structlog config + PII scrubber | `app/logging_config.py` | 1-55 |
| Correlation ID middleware | `app/middleware.py` | 1-28 |
| PII patterns + scrubbing | `app/pii.py` | 1-30 |
| Langfuse client + tracing | `app/tracing.py` | 1-54 |
| Agent pipeline + 6-span trace | `app/agent.py` | 1-377 |
| FastAPI app + context binding | `app/main.py` | 1-123 |
| Time-windowed metrics | `app/metrics.py` | 1-154 |
| Request/Response schemas | `app/schemas.py` | 1-59 |
| Real LLM (DashScope) | `app/llm.py` | 1-237 |
| Mock LLM (LM Studio) | `app/mock_llm.py` | 1-104 |
| 7-panel Dashboard | `app/dashboard.py` | 1-381 |
| Alert rules (9 rules) | `config/alert_rules.yaml` | 1-153 |
| Alert runbook (Vietnamese) | `docs/alerts.md` | 1-152 |
| Dashboard spec (7 panels) | `docs/dashboard-spec.md` | 1-280 |
| Load test script | `scripts/load_test.py` | 1-124 |
| Dashboard validation | `scripts/validate_dashboard.py` | 1-306 |
| Docker Compose (6 containers) | `docker-compose.yml` | 1-168 |

---

## [TECHNICAL_CHALLENGES]

### 1. Merge Conflict Resolution Across 7 Files

**Vấn đề**: Khi merge nhiều feature branches (Logging, Tracing, Metrics, Dashboard, LLM), xảy ra conflict ở 7 file cùng lúc do các thành viên chỉnh sửa overlapping regions (đặc biệt là `app/main.py` với duplicate `bind_contextvars` calls, `app/agent.py` với cả tracing và pricing logic).

**Giải pháp**: Phân tích từng conflict block, giữ lại cả hai logic khi cần thiết (ví dụ: giữ cả structlog config và Langfuse init trong `main.py`), loại bỏ duplicate (xóa `bind_contextvars` thừa), và đảm bảo import statements không bị trùng. Commit `1f9063b`, `551732c`, `9b76366`, `196962a` ghi lại quá trình này.

### 2. Langfuse Dummy Fallback Khi Không Có Server

**Vấn đề**: Khi Langfuse server chưa khởi động hoặc package không cài đặt, app crash vì import error.

**Giải pháp**: Triển khai `_DummyLangfuse` và `_DummySpan` classes (`app/tracing.py:17-41`) với context manager protocol (`__enter__`/`__exit__`), cho phép code tracing chạy bình thường mà không gửi data đi. Hàm `tracing_enabled()` kiểm tra `auth_check()` để xác định server có sẵn không.

### 3. PII Scrubbing Trong Log Pipeline

**Vấn đề**: PII patterns cần được scrub trước khi log ghi ra file, nhưng structlog processors chain cần đúng thứ tự - scrub phải xảy ra trước JSON rendering.

**Giải pháp**: Đặt `scrub_event` processor trước `JsonlFileProcessor` và `JSONRenderer` trong chain (`app/logging_config.py:39-47`). Scrub cả `event` string và mọi string values trong `payload` dict.

### 4. Time-Windowed Metrics Với deque

**Vấn đề**: Cần tính metrics trong cửa sổ thời gian rolling (5 phút) thay vì toàn bộ history, nhưng Python `deque` không có built-in time-based pruning.

**Giải pháp**: Lưu `(timestamp, value)` tuples trong deque, triển khai `_prune()` function (`app/metrics.py:31-34`) loại bỏ entries cũ hơn `WINDOW_SECONDS` mỗi khi đọc. Hàm `_values()` gọi `_prune()` rồi extract values.

### 5. LM Studio API Integration Với Fallback

**Vấn đề**: LM Studio có thể không chạy, cần fallback sang deterministic responses mà không làm crash pipeline.

**Giải pháp**: Wrap LM Studio API call trong try/except (`app/mock_llm.py:45-75`), catch `URLError`, `OSError`, `JSONDecodeError`, `KeyError`. Khi fail, fallback sang `_fallback()` method với keyword-based matching cho các domain topics (giờ làm, phạt, lương, bảo mật, refund, monitoring).

### 6. Docker Compose Port Conflicts

**Vấn đề**: Các port mặc định của Langfuse stack (3000, 5432, 6379, 8123, 9000) conflict với các dev projects khác đang chạy trên máy.

**Giải pháp**: Map tất cả ports sang custom range 27xxx: Langfuse Web 27100, Worker 27130, PostgreSQL 27433, ClickHouse HTTP 27124 / Native 27001, MinIO 27092 / Console 27093, Redis 27380. Sử dụng environment variables với defaults để dễ override.

---

## [LEARNING_OUTCOMES]

1. **Structured Logging Pipeline**: Hiểu sâu về structlog processor chain, cách bind context variables vào request scope, và tầm quan trọng của PII scrubbing trước khi ghi log. Nhận ra rằng log format không chỉ là convenience mà là requirement cho compliance (GDPR, FERPA).

2. **Distributed Tracing Concepts**: Nắm vững hierarchy của spans (root → child → grandchild), cách gắn metadata/tags/user_id/session_id vào traces, và sự khác biệt giữa span types (generation, guardrail, retriever, evaluator, tool). Hiểu tại sao tracing quan trọng hơn logging trong việc debug distributed systems.

3. **SLO Engineering**: Học cách định nghĩa Service Level Indicators (SLIs) và Objectives (SLOs) dựa trên business impact. Hiểu sự khác biệt giữa P50 (typical user), P95 (unlucky users), và P99 (worst cases). Nhận ra rằng error budget là công cụ để cân bằng giữa velocity và reliability.

4. **Security Observability**: Hiểu rằng observability không chỉ là performance monitoring mà còn là security monitoring. PII leak detection, prompt injection detection, và data exfiltration monitoring là first-class citizens trong observability pipeline.

5. **Quality Metrics for AI Systems**: Học cách đo lường chất lượng AI response qua 5 dimensions (quality, relevance, completeness, safety, overall) với weighted scoring. Nhận ra rằng heuristic quality metrics là proxy tốt khi không có human evaluation.

6. **Infrastructure as Code**: Trải nghiệm thực tế với Docker Compose cho multi-service stack (6 containers với dependencies, health checks, volume mounts). Hiểu tầm quan trọng của port management và environment variable configuration.

7. **Merge Conflict Resolution**: Kỹ năng phân tích và resolve merge conflicts trong team environment, đặc biệt khi nhiều người chỉnh sửa cùng file. Học cách giữ lại cả hai logic khi cần thiết và loại bỏ duplicates.

8. **Dashboard Design Principles**: Học cách thiết kế dashboard theo 3 layers (Executive → Engineering → Debug), mỗi layer phục vụ audience khác nhau. Hiểu tầm quan trọng của SLO threshold lines, unit labels, và auto-refresh trong production dashboards.

---

## [CONTRIBUTION_PERCENTAGE]

**Ước lượng: 20%** tổng đóng góp dự án

Lý do: Đóng góp xuyên suốt cả 5 lớp hệ thống (Logging/PII, Tracing, SLOs/Alerts, Load Test/Dashboard, Infrastructure), bao gồm:
- Viết code cho 17 files trong project
- Xử lý merge conflict resolution cho 7 files
- Cấu hình infrastructure (Docker Compose 6 containers)
- Tích hợp Real LLM (DashScope/Qwen) và LM Studio
- Viết 9 alert rules với Vietnamese runbook
- Xây dựng 7-panel dashboard với 3-layer design
- Phát triển load test với realistic study-abroad queries
- Triển khai MODEL_PRICING table với 16 models
- Viết dashboard validation script
