import argparse
import concurrent.futures
import json
import time
import uuid
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8009"
QUERIES = Path("data/sample_queries.jsonl")

STUDY_ABROAD_QUERIES = {
    "qa": [
        "Visa du học Mỹ cần những giấy tờ gì?",
        "Học bổng toàn phần tại Úc có những loại nào?",
        "Thời gian xử lý hồ sơ visa Canada bao lâu?",
        "Yêu cầu IELTS cho đại học Anh là bao nhiêu?",
        "Chi phí sinh hoạt hàng tháng tại Singapore?",
    ],
    "summary": [
        "Tóm tắt yêu cầu visa du học Đức cho chương trình thạc sĩ",
        "Tổng hợp các bước xin học bổng chính phủ Nhật Bản MEXT",
        "Tóm tắt quy trình công nhận bằng cấp tại Úc",
    ],
    "document_review": [
        "Kiểm tra SOP này có đủ yêu cầu cho Harvard không?",
        "Review CV của tôi cho chương trình交换 sinh viên",
        "Đánh giá thư giới thiệu này có đủ mạnh không?",
    ],
    "visa_check": [
        "Kiểm tra danh sách giấy tờ visa du học Hàn Quốc D-2",
        "Visa F-1 Mỹ cần chứng minh tài chính bao nhiêu?",
        "Yêu cầu health insurance cho visa du học Úc subclass 500?",
    ],
}


def send_request(client: httpx.Client, payload: dict) -> dict:
    try:
        start = time.perf_counter()
        r = client.post(f"{BASE_URL}/chat", json=payload)
        latency = (time.perf_counter() - start) * 1000
        data = r.json()
        print(f"[{r.status_code}] {data.get('correlation_id', 'N/A')} | {payload['feature']} | {latency:.1f}ms | quality={data.get('quality_score', 'N/A')}")
        return {"status": r.status_code, "latency_ms": latency}
    except Exception as e:
        print(f"Error: {e}")
        return {"status": 0, "latency_ms": 0, "error": str(e)}


def generate_scenario_payload(scenario: str | None = None) -> dict:
    """Generate a realistic study abroad chatbot request."""
    import random

    feature = scenario or random.choice(list(STUDY_ABROAD_QUERIES.keys()))
    message = random.choice(STUDY_ABROAD_QUERIES[feature])
    return {
        "user_id": f"u_{uuid.uuid4().hex[:8]}",
        "session_id": f"s_{uuid.uuid4().hex[:6]}",
        "feature": feature,
        "message": message,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Load test for Study Abroad Document Chatbot")
    parser.add_argument("--concurrency", type=int, default=1, help="Number of concurrent requests")
    parser.add_argument("--count", type=int, default=0, help="Number of requests (0 = use sample_queries.jsonl)")
    parser.add_argument("--scenario", type=str, choices=["qa", "summary", "document_review", "visa_check"], help="Force specific feature type")
    parser.add_argument("--duration", type=int, default=0, help="Run for N seconds (0 = run once)")
    args = parser.parse_args()

    payloads = []

    if args.count > 0:
        payloads = [generate_scenario_payload(args.scenario) for _ in range(args.count)]
    elif args.duration > 0:
        print(f"Running for {args.duration}s with concurrency={args.concurrency}...")
        start_time = time.time()
        with httpx.Client(timeout=30.0) as client:
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                while time.time() - start_time < args.duration:
                    payload = generate_scenario_payload(args.scenario)
                    executor.submit(send_request, client, payload)
                    time.sleep(0.5)
        return
    else:
        if QUERIES.exists():
            payloads = [json.loads(line) for line in QUERIES.read_text(encoding="utf-8").splitlines() if line.strip()]
        else:
            payloads = [generate_scenario_payload(args.scenario) for _ in range(10)]

    if not payloads:
        print("No payloads to send!")
        return

    print(f"Sending {len(payloads)} requests with concurrency={args.concurrency}...")
    print("-" * 60)

    results = []
    with httpx.Client(timeout=30.0) as client:
        if args.concurrency > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                futures = [executor.submit(send_request, client, payload) for payload in payloads]
                results = [f.result() for f in concurrent.futures.as_completed(futures)]
        else:
            for payload in payloads:
                results.append(send_request(client, payload))

    print("-" * 60)
    success = sum(1 for r in results if r.get("status") == 200)
    failed = len(results) - success
    latencies = [r["latency_ms"] for r in results if r.get("latency_ms", 0) > 0]

    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        print(f"Results: {success} success, {failed} failed")
        print(f"Avg latency: {avg_lat:.1f}ms")
        print(f"Check dashboard at: http://localhost:27100")


if __name__ == "__main__":
    main()
