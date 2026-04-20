# Alert Rules and Runbooks

## Context: Study Abroad Document Chatbot

**Dashboard**: http://localhost:27100
**Runbook**: config/alert_rules.yaml

---

## 1. High latency P95
- **Severity**: P2
- **Trigger**: `latency_p95_ms > 5000 for 30m`
- **Impact**: Sinh viên chờ > 5s, tỷ lệ bỏ cuộc cao
- **Dashboard Panel**: Latency (Panel 1)
- **First checks**:
  1. Mở top slow traces trong 1h qua trên Langfuse
  2. So sánh RAG span vs LLM span để xác định bottleneck
  3. Kiểm tra incident toggle `rag_slow` có enabled không
- **Mitigation**:
  - Truncate queries dài > 500 từ
  - Fallback sang retrieval source nhanh hơn
  - Giảm prompt size

## 2. High error rate
- **Severity**: P1
- **Trigger**: `error_rate_pct > 5 for 5m`
- **Impact**: Sinh viên nhận lỗi, không có câu trả lời
- **Dashboard Panel**: Error Rate (Panel 3)
- **First checks**:
  1. Group logs by `error_type` (llm_timeout, rag_empty, schema_validation, pii_blocked)
  2. Inspect failed traces trên Langfuse
  3. Xác định lỗi từ LLM, RAG, hay schema validation
- **Mitigation**:
  - Rollback thay đổi gần nhất
  - Disable tool bị lỗi
  - Retry với fallback model

## 3. Cost budget spike
- **Severity**: P2
- **Trigger**: `hourly_cost_usd > 2x_baseline for 15m`
- **Impact**: Chi phí vượt ngân sách $2.5/ngày
- **Dashboard Panel**: Cost (Panel 4)
- **First checks**:
  1. Split traces by feature (qa, summary, document_review, visa_check) và model
  2. So sánh tokens_in/tokens_out để tìm prompt bloat
  3. Kiểm tra `cost_spike` incident có enabled không
- **Mitigation**:
  - Shorten prompts
  - Route easy requests sang model rẻ hơn
  - Apply prompt cache

## 4. Low quality score
- **Severity**: P2
- **Trigger**: `quality_score_avg < 0.5 for 15m`
- **Impact**: Câu trả lời không hữu ích, sinh viên không hài lòng
- **Dashboard Panel**: Quality (Panel 6)
- **First checks**:
  1. Kiểm tra `rag_docs_count` trong traces (0 = không tìm được docs)
  2. Xem sample answers có bị `[REDACTED]` do PII scrubbing không
  3. So sánh quality_score theo feature type
- **Mitigation**:
  - Expand RAG knowledge base
  - Improve retrieval relevance
  - Add prompt templates per feature

## 5. High regenerate rate
- **Severity**: P3
- **Trigger**: `regenerate_rate > 30 for 10m`
- **Impact**: Sinh viên phải hỏi lại nhiều lần, trải nghiệm kém
- **Dashboard Panel**: Quality (Panel 6)
- **First checks**:
  1. Nhóm sessions có regenerate > 2 lần
  2. Phân tích common patterns trong failed queries
  3. Kiểm tra empty_rag_rate (RAG không tìm được docs)
- **Mitigation**:
  - Improve query understanding
  - Add clarification prompts
  - Expand document coverage cho các topic phổ biến

---

## Security Alerts

## 6. PII Leak Detected
- **Severity**: P1 (CRITICAL)
- **Trigger**: `pii_leak_count > 0 for 1m`
- **Impact**: Dữ liệu nhạy cảm của sinh viên bị lộ trong logs (email, SĐT, CCCD, credit card)
- **Dashboard Panel**: Security (Panel 7)
- **First checks**:
  1. Kiểm tra log lines có PII không bị redact: `grep -E "(email|phone|credit)" data/logs.jsonl`
  2. Xác định source: input validation hay output scrubbing
  3. Review PII patterns trong `app/pii.py`
- **Mitigation**:
  - Enable strict PII scrubbing mode
  - Block request chứa PII chưa được hash
  - Audit toàn bộ logs trong 24h qua
- **Compliance**: GDPR, FERPA violation nếu không xử lý

## 7. Prompt Injection Detected
- **Severity**: P1 (CRITICAL)
- **Trigger**: `prompt_injection_count > 0 for 5m`
- **Impact**: Sinh viên cố gắng bypass system prompt, truy cập thông tin nhạy cảm hoặc thao tác hệ thống
- **Dashboard Panel**: Security (Panel 7)
- **First checks**:
  1. Inspect traces có `prompt_injection` tag trên Langfuse
  2. Phân tích pattern injection attempts (nhóm by user_id, session_id)
  3. Kiểm tra system prompt có bị leak trong responses không
- **Mitigation**:
  - Add input validation rules cho suspicious patterns
  - Strengthen system prompt guardrails
  - Block suspicious user sessions
- **Common Patterns**:
  - "Ignore previous instructions"
  - "You are now [different persona]"
  - "Reveal your system prompt"
  - "What are your rules/constraints"

## 8. Unauthorized Access Attempt
- **Severity**: P1 (CRITICAL)
- **Trigger**: `auth_failure_count > 10 for 5m`
- **Impact**: Brute force attack hoặc truy cập trái phép vào hệ thống
- **Dashboard Panel**: Security (Panel 7)
- **First checks**:
  1. Group auth failures by IP và user_id
  2. Kiểm tra có pattern automated attack không (rapid succession)
  3. Review access logs cho suspicious activity
- **Mitigation**:
  - Rate limit API endpoints
  - Block suspicious IPs
  - Enable CAPTCHA cho login
- **Indicators**:
  - Multiple failed API key attempts
  - Requests từ IPs không whitelist
  - Unusual user-agent patterns

## 9. Data Exfiltration Risk
- **Severity**: P1 (CRITICAL)
- **Trigger**: `tokens_out_per_request > 10000 for 3 requests`
- **Impact**: AI có thể đang leak toàn bộ knowledge base hoặc dữ liệu nhạy cảm qua responses quá dài
- **Dashboard Panel**: Security (Panel 7)
- **First checks**:
  1. Inspect traces với `tokens_out > 10000` trên Langfuse
  2. Kiểm tra response content có chứa raw documents không
  3. Xem có pattern scraping (sequential queries extracting data)
- **Mitigation**:
  - Set max_tokens limit cho responses (max 2000)
  - Add output validation để detect raw document leaks
  - Implement response length guardrails
- **Indicators**:
  - Single response > 10000 tokens
  - Multiple responses containing full document text
  - Sequential queries targeting specific knowledge areas
