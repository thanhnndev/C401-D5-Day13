# Day 13 Observability Lab Report

> **Instruction**: Fill in all sections below. This report is designed to be parsed by an automated grading assistant. Ensure all tags (e.g., `[GROUP_NAME]`) are preserved.

## 1. Team Metadata

- [GROUP_NAME]:
- [REPO_URL]:
- [MEMBERS]:
  - Member A: [Name] | Role: Logging & PII
  - Member B: [Name] | Role: Tracing & Enrichment
  - Member C: [Name] | Role: SLO & Alerts
  - Member D: [Name] | Role: Load Test & Dashboard
  - Member E: [Name] | Role: Demo & Report

---

## 2. Group Performance (Auto-Verified)

- [VALIDATE_LOGS_FINAL_SCORE]: /100
- [TOTAL_TRACES_COUNT]:
- [PII_LEAKS_FOUND]:

---

## 3. Technical Evidence (Group)

### 3.1 Logging & Tracing

- [EVIDENCE_CORRELATION_ID_SCREENSHOT]: [Path to image]
- [EVIDENCE_PII_REDACTION_SCREENSHOT]: [Path to image]
- [EVIDENCE_TRACE_WATERFALL_SCREENSHOT]: [Path to image]
- [TRACE_WATERFALL_EXPLANATION]: (Briefly explain one interesting span in your trace)

### 3.2 Dashboard & SLOs

- [DASHBOARD_7_PANELS_SCREENSHOT]: [Path to image]
- [SLO_TABLE]:
  | SLI | Target | Window | Current Value |
  |---|---:|---|---:|
  | Latency P95 | < 3000ms | 28d | |
  | Error Rate | < 2% | 28d | |
  | Cost Budget | < $2.5/day | 1d | |
  | PII Leaks | 0 | 28d | |
  | Prompt Injections | 0 | 28d | |

### 3.3 Alerts & Runbook

- [ALERT_RULES_SCREENSHOT]: [Path to image]
- [SAMPLE_RUNBOOK_LINK]: [docs/alerts.md#L...]

---

## 4. Incident Response (Group)

- [SCENARIO_NAME]: (e.g., rag_slow)
- [SYMPTOMS_OBSERVED]:
- [ROOT_CAUSE_PROVED_BY]: (List specific Trace ID or Log Line)
- [FIX_ACTION]:
- [PREVENTIVE_MEASURE]:

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

### [MEMBER_B_NAME]

- [TASKS_COMPLETED]:
- [EVIDENCE_LINK]:

### [MEMBER_C_NAME]

- [TASKS_COMPLETED]:
- [EVIDENCE_LINK]:

### [MEMBER_D_NAME]

- [TASKS_COMPLETED]:
- [EVIDENCE_LINK]:

### [MEMBER_E_NAME]

- [TASKS_COMPLETED]:
- [EVIDENCE_LINK]:

---

## 6. Bonus Items (Optional)

- [BONUS_COST_OPTIMIZATION]: (Description + Evidence)
- [BONUS_AUDIT_LOGS]: (Description + Evidence)
- [BONUS_CUSTOM_METRIC]: (Description + Evidence)
