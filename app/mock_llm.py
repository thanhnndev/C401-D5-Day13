from __future__ import annotations

import random
import time
from dataclasses import dataclass

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
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model

    def generate(self, prompt: str) -> FakeResponse:
        time.sleep(0.15)
        input_tokens = max(20, len(prompt) // 4)
        output_tokens = random.randint(80, 180)
        if STATE["cost_spike"]:
            output_tokens *= 4
        answer = "Tôi là trợ lý ảo của công ty TNHH D5. Rất tiếc tôi không tìm thấy thông tin bạn yêu cầu."
        if "Docs=[" in prompt:
            docs_part = prompt.split("Docs=[")[1].split("]")[0]
            if docs_part and "No domain document matched" not in docs_part:
                clean_docs = docs_part.strip("'\"")
                answer = f"Dựa trên quy định công ty D5: {clean_docs}"
        elif "policy" in prompt.lower():
            answer = "Quy định bảo mật: Không tiết lộ PII, dùng bản tóm tắt đã xóa dữ liệu nhạy cảm."

        return FakeResponse(text=answer, usage=FakeUsage(input_tokens, output_tokens), model=self.model)
