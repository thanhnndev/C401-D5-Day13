"""
LLM module - wraps DashScope / Qwen API (OpenAI-compatible endpoint).

When DASHSCOPE_API_KEY is present the real model is called.
If the key is missing or the call fails, a structured fallback answer
is returned so the rest of the pipeline continues working.
"""
from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .incidents import STATE

load_dotenv()

# ---------------------------------------------------------------------------
# Response dataclasses (same shape as FakeLLM so agent.py needs no changes)
# ---------------------------------------------------------------------------

@dataclass
class LLMUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class LLMResponse:
    text: str
    usage: LLMUsage
    model: str


# ---------------------------------------------------------------------------
# System prompt: loaded once at import time from docs + policy + mock corpus
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """
    Build a rich system prompt by combining:
      1. data/company_policy.md   – official HR rules of Công ty TNHH D5
      2. CORPUS                   – structured Q&A extracted from mock_rag
      3. docs/alerts.md           – observability alert runbooks
    """
    base = Path(__file__).parent.parent  # project root

    sections: list[str] = []

    # 1. Company policy --------------------------------------------------
    policy_path = base / "data" / "company_policy.md"
    if policy_path.exists():
        sections.append("## QUY ĐỊNH NỘI BỘ CÔNG TY TNHH D5\n" + policy_path.read_text(encoding="utf-8"))

    # 2. Q&A corpus (mirrored from mock_rag.CORPUS) ----------------------
    corpus_md = """
## CƠ SỞ KIẾN THỨC (Q&A)

- **Hoàn tiền (refund):** Khách hàng có thể yêu cầu hoàn tiền trong vòng 7 ngày kể từ ngày mua và phải cung cấp bằng chứng mua hàng.

- **Monitoring:** Metrics giúp phát hiện sự cố, Traces giúp khoanh vùng vị trí lỗi, Logs giúp giải thích nguyên nhân gốc.

- **Chính sách bảo mật:** Tuyệt đối không tiết lộ thông tin PII trong log. Chỉ sử dụng bản tóm tắt đã được sanitize.

- **Giờ làm việc:** 08:30 – 17:30 (Thứ 2 – Thứ 6), Thứ 7 (08:30 – 12:00). Nghỉ trưa: 12:00 – 13:30. Chấm công bằng FaceID.

- **Gửi xe:** Xe máy tại hầm B1, ô tô tại hầm B2. Miễn phí khi xuất trình thẻ nhân viên.

- **Mức phạt:**
  - Đi trễ (sau 15 phút): 50.000 VNĐ/lần
  - Không đồng phục đúng ngày: 100.000 VNĐ/lần
  - Hút thuốc sai nơi: 200.000 VNĐ/lần
  - Vi phạm 5S: 50.000 VNĐ/lần

- **Lương:** Nhận vào ngày 05 hàng tháng qua Techcombank. Thưởng tháng 13 cho nhân viên đủ 12 tháng.

- **Tính lương Net:** Lương Gross – (BHXH + BHYT + BHTN) – Thuế TNCN. Công ty đóng 100% bảo hiểm trên mức lương hợp đồng.
"""
    sections.append(corpus_md)

    # 3. Observability runbooks ------------------------------------------
    alerts_path = base / "docs" / "alerts.md"
    if alerts_path.exists():
        sections.append("## RUNBOOK VẬN HÀNH / OBSERVABILITY\n" + alerts_path.read_text(encoding="utf-8"))

    system_prompt = """Bạn là trợ lý AI chính thức của Công ty TNHH D5.
Nhiệm vụ của bạn là trả lời câu hỏi của nhân viên và khách hàng dựa CHÍNH XÁC vào tài liệu nội bộ bên dưới.

NGUYÊN TẮC:
- Chỉ trả lời dựa trên tài liệu được cung cấp.
- Nếu không có thông tin, hãy nói rõ "Tôi không có thông tin về vấn đề này."
- KHÔNG bịa đặt thông tin. KHÔNG tiết lộ PII.
- Trả lời ngắn gọn, chuyên nghiệp bằng tiếng Việt.
- Khi câu hỏi liên quan đến observability/kỹ thuật, sử dụng ngôn ngữ chuyên môn chính xác.

--- TÀI LIỆU NỘI BỘ ---

"""
    system_prompt += "\n\n---\n\n".join(sections)
    return system_prompt


_SYSTEM_PROMPT: str = _load_system_prompt()


# ---------------------------------------------------------------------------
# Real LLM class
# ---------------------------------------------------------------------------

class LLM:
    """
    Calls DashScope (Qwen) via OpenAI-compatible REST API.

    Falls back to a structured local answer when:
      - DASHSCOPE_API_KEY is not set
      - The upstream API is unreachable / returns an error
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("QWEN_MODEL", "")
        self._api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self._endpoint = os.getenv(
            "DASHSCOPE_ENDPOINT",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )
        # Lazy-import openai so the module still loads without it
        self._client = None
        if self._api_key:
            try:
                from openai import OpenAI  # type: ignore
                self._client = OpenAI(api_key=self._api_key, base_url=self._endpoint)
            except ImportError:
                pass  # openai not installed

    # ------------------------------------------------------------------
    def generate(self, prompt: str) -> LLMResponse:
        """Generate a response. Raises if model or API key is not configured."""
        # ── incident simulation ──────────────────────────────────────
        if STATE.get("tool_fail"):
            raise RuntimeError("LLM tool_fail incident active")
        if STATE.get("rag_slow"):
            time.sleep(2.5)

        # ── validate config before doing anything ────────────────────
        missing_config = not self.model or not self._api_key or not self._client

        # ── cost-spike simulation (multiplies tokens) ─────────────────
        spike = STATE.get("cost_spike", False)

        if missing_config:
            return self._fallback(prompt, spike, zero_cost=True)

        return self._call_api(prompt, spike)

    # ------------------------------------------------------------------
    def _call_api(self, prompt: str, spike: bool) -> LLMResponse:
        t0 = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=512 if not spike else 2048,
                temperature=0.2,
                extra_body={"enable_thinking": False},  # tắt thinking mode (Qwen3)
            )
            raw = response.choices[0].message.content or ""
            # Loại bỏ bất kỳ thẻ <think>...</think> nào còn sót lại
            import re as _re
            text = _re.sub(r"<think>.*?</think>", "", raw, flags=_re.DOTALL).strip()
            usage = response.usage
            input_tokens  = usage.prompt_tokens     if usage else max(20, len(prompt) // 4)
            output_tokens = usage.completion_tokens if usage else random.randint(80, 180)
            if spike:
                output_tokens *= 4
            return LLMResponse(
                text=text,
                usage=LLMUsage(input_tokens=input_tokens, output_tokens=output_tokens),
                model=self.model,
            )
        except Exception as e:
            # API call failed – graceful fallback
            latency = time.perf_counter() - t0
            # minimum sleep so latency metric is realistic
            if latency < 0.1:
                time.sleep(0.1 - latency)
            return self._fallback(prompt, spike, zero_cost=True)

    # ------------------------------------------------------------------
    def _fallback(self, prompt: str, spike: bool, zero_cost: bool = False) -> LLMResponse:
        """Deterministic structured fallback (mirrors FakeLLM logic)."""
        time.sleep(0.15)
        if zero_cost:
            input_tokens = 0
            output_tokens = 0
        else:
            input_tokens  = max(20, len(prompt) // 4)
            output_tokens = random.randint(80, 180)
            if spike:
                output_tokens *= 4

        answer = "Tôi là trợ lý ảo của công ty TNHH D5. Rất tiếc tôi không tìm thấy thông tin bạn yêu cầu."
        
        if not self.model:
            answer = "[CẢNH BÁO: Chưa cấu hình Model, API không được kích hoạt] " + answer

        prompt_lower = prompt.lower()

        # try to match against inline docs context supplied by agent
        if "Docs=[" in prompt:
            docs_part = prompt.split("Docs=[")[1].split("]")[0]
            if docs_part and "No domain document matched" not in docs_part:
                answer = f"Dựa trên quy định công ty D5: {docs_part.strip(chr(39) + chr(34))}"
        elif any(k in prompt_lower for k in ("giờ", "check-in", "chấm công")):
            answer = "Giờ làm việc: 08:30–17:30 (Thứ 2–6), Thứ 7 (08:30–12:00). Chấm công bằng FaceID."
        elif any(k in prompt_lower for k in ("phạt", "late", "trễ")):
            answer = "Đi trễ sau 15 phút: phạt 50.000 VNĐ/lần. Không đồng phục: 100.000 VNĐ/lần."
        elif any(k in prompt_lower for k in ("lương", "salary", "net", "gross")):
            answer = "Lương được nhận vào ngày 05 hàng tháng qua Techcombank. Thưởng tháng 13 cho nhân viên đủ 12 tháng."
        elif any(k in prompt_lower for k in ("bảo mật", "pii", "policy", "security")):
            answer = "Tuyệt đối không tiết lộ thông tin khách hàng. Không dùng USB ngoài. Đổi mật khẩu 3 tháng/lần."
        elif any(k in prompt_lower for k in ("refund", "hoàn tiền")):
            answer = "Hoàn tiền trong vòng 7 ngày với bằng chứng mua hàng."
        elif any(k in prompt_lower for k in ("monitoring", "alert", "trace", "log", "metric")):
            answer = "Metrics phát hiện sự cố. Traces khoanh vùng vị trí. Logs giải thích nguyên nhân gốc."

        return LLMResponse(
            text=answer,
            usage=LLMUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            model=self.model,
        )