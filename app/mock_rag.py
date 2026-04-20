from __future__ import annotations

import time

from .incidents import STATE

CORPUS = {
    "refund": ["Refunds are available within 7 days with proof of purchase."],
    "monitoring": ["Metrics detect incidents, traces localize them, logs explain root cause."],
    "policy": ["Do not expose PII in logs. Use sanitized summaries only."],
    "giờ": ["Giờ làm việc: 08:30 - 17:30 (Thứ 2 - Thứ 6), Thứ 7 (08:30 - 12:00). Nghỉ trưa: 12:00 - 13:30. Chấm công bằng FaceID."],
    "xe": ["Gửi xe máy tại hầm B1, ô tô tại hầm B2. Miễn phí khi có thẻ nhân viên."],
    "bảo mật": ["Tuyệt đối không tiết lộ thông tin khách hàng. Không dùng USB ngoài. Đổi mật khẩu 3 tháng/lần."],
    "phạt": ["Đi trễ phạt 50k, không đồng phục phạt 100k, hút thuốc sai chỗ phạt 200k."],
    "lương": ["Nhận lương ngày 05 hàng tháng qua Techcombank. Thưởng tháng 13 cho nhân viên đủ 12 tháng."],
    "thuế": ["Lương Net = Gross - Bảo hiểm (BHXH, BHYT, BHTN) - Thuế TNCN. Công ty hỗ trợ 100% bảo hiểm."],
}


def retrieve(message: str) -> list[str]:
    if STATE["tool_fail"]:
        raise RuntimeError("Vector store timeout")
    if STATE["rag_slow"]:
        time.sleep(2.5)
    lowered = message.lower()
    for key, docs in CORPUS.items():
        if key in lowered:
            return docs
    return ["No domain document matched. Use general fallback answer."]
