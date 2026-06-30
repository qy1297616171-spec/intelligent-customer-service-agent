import argparse
import asyncio
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    return ordered[min(math.ceil(len(ordered) * ratio) - 1, len(ordered) - 1)]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", default="ChangeMe123!")
    args = parser.parse_args()
    timeout = httpx.Timeout(20)
    limits = httpx.Limits(max_connections=args.concurrency)
    latencies: list[float] = []
    statuses: dict[int, int] = {}
    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(
        base_url=args.base_url, timeout=timeout, limits=limits, trust_env=False
    ) as client:
        login = await client.post("/api/v1/auth/login", json={"email": args.email, "password": args.password})
        if login.status_code not in {200, 404}:
            raise RuntimeError(f"login failed: {login.status_code} {login.text}")

        async def request_once(index: int) -> None:
            async with semaphore:
                started = perf_counter()
                response = await client.post(
                    "/api/v1/conversations/ask",
                    json={
                        "tenant_id": "demo-company",
                        "customer_id": "customer-2846",
                        "question": "我的快递到哪了" if index % 2 == 0 else "查看我的订单详情",
                    },
                )
                latencies.append((perf_counter() - started) * 1000)
                statuses[response.status_code] = statuses.get(response.status_code, 0) + 1

        started = perf_counter()
        await asyncio.gather(*(request_once(index) for index in range(args.requests)))
        elapsed = perf_counter() - started

    success = sum(count for status, count in statuses.items() if status < 400)
    result = {
        "measured_at": datetime.now(UTC).isoformat(),
        "target": args.base_url,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "duration_seconds": round(elapsed, 3),
        "throughput_rps": round(args.requests / elapsed, 2),
        "success_rate": round(success / args.requests, 4),
        "latency_ms": {
            "min": round(min(latencies), 2), "mean": round(sum(latencies) / len(latencies), 2),
            "p50": round(percentile(latencies, .50), 2),
            "p95": round(percentile(latencies, .95), 2),
            "p99": round(percentile(latencies, .99), 2), "max": round(max(latencies), 2),
        },
        "status_codes": statuses,
    }
    root = Path(__file__).parents[1]
    report_dir = root / "evaluation" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "load_test_latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    latency = result["latency_ms"]
    markdown = f"""# 本地 API 压测实测报告

- 测量时间：{result['measured_at']}
- 请求数 / 并发数：{args.requests} / {args.concurrency}
- 成功率：{result['success_rate'] * 100:.2f}%
- 吞吐量：{result['throughput_rps']} RPS
- 平均 / P50 / P95 / P99：{latency['mean']} / {latency['p50']} / {latency['p95']} / {latency['p99']} ms
- 状态码：{result['status_codes']}

> 指标来自当前目标地址的实测；模型仍为 mock，不等同于真实模型端到端容量，生产上线前应在目标服务器和真实模型链路复测。
"""
    (report_dir / "load_test_latest.md").write_text(markdown, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
