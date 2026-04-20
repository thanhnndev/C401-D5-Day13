from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from urllib.request import Request, urlopen
from urllib.error import URLError
import json

from .incidents import STATE


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeResponse:
    text: str
    usage: FakeUsage
    model: str


class FakeLLM:
    def __init__(self, model: str = "qwen/qwen3-8b") -> None:
        self.model = os.getenv("LLM_MODEL", model)
        self.base_url = os.getenv("LM_STUDIO_URL", "http://localhost:1234").rstrip("/v1")

    def generate(self, prompt: str) -> FakeResponse:
        if STATE.get("tool_fail"):
            raise RuntimeError("LLM tool_fail incident active")
        if STATE.get("rag_slow"):
            time.sleep(2.5)

        input_tokens = max(20, len(prompt) // 4)

        if STATE.get("cost_spike"):
            output_tokens = random.randint(320, 720)
        else:
            output_tokens = random.randint(80, 180)

        try:
            start = time.perf_counter()
            payload = json.dumps({
                "model": self.model,
                "input": prompt,
            }).encode("utf-8")
            req = Request(
                f"{self.base_url}/api/v1/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            text = ""
            for item in result.get("output", []):
                if item.get("type") == "message":
                    text += item.get("content", "")

            stats = result.get("stats", {})
            actual_in = stats.get("input_tokens", input_tokens)
            actual_out = stats.get("total_output_tokens", output_tokens)

            return FakeResponse(
                text=text,
                usage=FakeUsage(input_tokens=actual_in, output_tokens=actual_out),
                model=self.model,
            )
        except (URLError, OSError, json.JSONDecodeError, KeyError):
            pass

        return FakeResponse(
            text=self._fallback(prompt),
            usage=FakeUsage(input_tokens, output_tokens),
            model=self.model,
        )

    def _fallback(self, prompt: str) -> str:
        time.sleep(0.15)
        prompt_lower = prompt.lower()

        if "Docs=[" in prompt:
            docs_part = prompt.split("Docs=[")[1].split("]")[0]
            if docs_part and "No domain document matched" not in docs_part:
                return f"Dựa trên quy định công ty D5: {docs_part.strip(chr(39) + chr(34))}"
        elif any(k in prompt_lower for k in ("giờ", "check-in", "chấm công")):
            return "Giờ làm việc: 08:30–17:30 (Thứ 2–6), Thứ 7 (08:30–12:00). Chấm công bằng FaceID."
        elif any(k in prompt_lower for k in ("phạt", "late", "trễ")):
            return "Đi trễ sau 15 phút: phạt 50.000 VNĐ/lần. Không đồng phục: 100.000 VNĐ/lần."
        elif any(k in prompt_lower for k in ("lương", "salary", "net", "gross")):
            return "Lương được nhận vào ngày 05 hàng tháng qua Techcombank. Thưởng tháng 13 cho nhân viên đủ 12 tháng."
        elif any(k in prompt_lower for k in ("bảo mật", "pii", "policy", "security")):
            return "Tuyệt đối không tiết lộ thông tin khách hàng. Không dùng USB ngoài. Đổi mật khẩu 3 tháng/lần."
        elif any(k in prompt_lower for k in ("refund", "hoàn tiền")):
            return "Hoàn tiền trong vòng 7 ngày với bằng chứng mua hàng."
        elif any(k in prompt_lower for k in ("monitoring", "alert", "trace", "log", "metric")):
            return "Metrics phát hiện sự cố. Traces khoanh vùng vị trí. Logs giải thích nguyên nhân gốc."

        return "Tôi là trợ lý ảo của công ty TNHH D5. Rất tiếc tôi không tìm thấy thông tin bạn yêu cầu."
