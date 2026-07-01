import argparse
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from time import perf_counter, sleep

import httpx


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    index = max(0, min(round((len(ordered) - 1) * ratio), len(ordered) - 1))
    return ordered[index]


def login(client: httpx.Client, email: str, password: str) -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    if response.status_code == 404:
        return
    response.raise_for_status()


def seed_knowledge(client: httpx.Client, root: Path, tenant_id: str) -> int:
    existing = client.get("/api/v1/knowledge/documents", params={"tenant_id": tenant_id})
    existing.raise_for_status()
    existing_sources = {item["source"] for item in existing.json()}
    fixtures = json.loads(
        (root / "evaluation" / "fixtures" / "knowledge_baseline.json").read_text(encoding="utf-8")
    )
    created = 0
    for item in fixtures:
        if item["source"] in existing_sources:
            continue
        response = client.post(
            "/api/v1/knowledge/documents", json={"tenant_id": tenant_id, **item}
        )
        response.raise_for_status()
        created += 1
    return created


def ask_with_retry(client: httpx.Client, payload: dict) -> httpx.Response:
    for attempt in range(8):
        response = client.post("/api/v1/conversations/ask", json=payload)
        if response.status_code != 429:
            return response
        sleep(min(2 ** attempt, 15))
    return response


def main() -> None:
    parser = argparse.ArgumentParser(description="执行电商客服评测集并生成报告")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--dataset", default="evaluation/datasets/ecommerce_qa_v1.jsonl")
    parser.add_argument("--email", default=os.getenv("EVAL_EMAIL", "admin@example.com"))
    parser.add_argument("--password", default=os.getenv("EVAL_PASSWORD", "ChangeMe123!"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed-knowledge", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).parents[1]
    cases = [
        json.loads(line)
        for line in (root / args.dataset).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit:
        cases = cases[: args.limit]

    details = []
    client_latencies = []
    started_all = perf_counter()
    with httpx.Client(base_url=args.base_url, timeout=30, trust_env=False) as client:
        login(client, args.email, args.password)
        seeded = seed_knowledge(client, root, "demo-company") if args.seed_knowledge else 0
        for case in cases:
            started = perf_counter()
            response = ask_with_retry(
                client,
                {
                    "tenant_id": case["tenant_id"],
                    "customer_id": case.get("customer_id"),
                    "question": case["question"],
                },
            )
            client_ms = (perf_counter() - started) * 1000
            client_latencies.append(client_ms)
            if response.status_code != 200:
                details.append({"id": case["id"], "category": case["category"], "http_status": response.status_code, "passed": False})
                continue
            answer = response.json()
            content = answer["answer"]
            expected_keywords = case["expected_keywords"]
            type_match = answer["answer_type"] == case["expected_answer_type"]
            keyword_hit = not expected_keywords or any(word in content for word in expected_keywords)
            forbidden_hit = any(word in content for word in case["forbidden_keywords"])
            refusal_grounding_ok = case["expected_answer_type"] != "refusal" or not answer["grounded"]
            details.append(
                {
                    "id": case["id"], "category": case["category"],
                    "expected_type": case["expected_answer_type"], "actual_type": answer["answer_type"],
                    "type_match": type_match, "keyword_hit": keyword_hit,
                    "forbidden_hit": forbidden_hit, "grounding_ok": refusal_grounding_ok,
                    "server_latency_ms": answer["latency_ms"], "client_latency_ms": round(client_ms, 2),
                    "passed": type_match and keyword_hit and not forbidden_hit and refusal_grounding_ok,
                }
            )

    total = len(details)
    successful_http = [item for item in details if item.get("http_status", 200) == 200]
    category_stats = defaultdict(lambda: {"total": 0, "passed": 0})
    for item in details:
        stats = category_stats[item["category"]]
        stats["total"] += 1
        stats["passed"] += int(item["passed"])
    result = {
        "measured_at": datetime.now(UTC).isoformat(), "target": args.base_url,
        "dataset": args.dataset, "cases": total, "seeded_documents": seeded,
        "http_success_rate": len(successful_http) / total if total else 0,
        "case_pass_rate": sum(item["passed"] for item in details) / total if total else 0,
        "type_accuracy": sum(item.get("type_match", False) for item in details) / total if total else 0,
        "keyword_hit_rate": sum(item.get("keyword_hit", False) for item in details) / total if total else 0,
        "unsafe_output_rate": sum(item.get("forbidden_hit", False) for item in details) / total if total else 0,
        "latency_ms": {
            "mean": round(mean(client_latencies), 2),
            "p50": round(percentile(client_latencies, .50), 2),
            "p95": round(percentile(client_latencies, .95), 2),
            "p99": round(percentile(client_latencies, .99), 2),
        },
        "duration_seconds": round(perf_counter() - started_all, 2),
        "categories": {key: {**value, "pass_rate": value["passed"] / value["total"]} for key, value in sorted(category_stats.items())},
        "details": details,
    }
    report_dir = root / "evaluation" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "evaluation_latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 电商客服自动评测报告", "",
        f"- 测量时间：{result['measured_at']}", f"- 目标环境：{args.base_url}",
        f"- 用例数：{total}", f"- HTTP 成功率：{pct(result['http_success_rate'])}",
        f"- 综合通过率：{pct(result['case_pass_rate'])}", f"- 答案类型准确率：{pct(result['type_accuracy'])}",
        f"- 关键词命中率：{pct(result['keyword_hit_rate'])}", f"- 不安全输出率：{pct(result['unsafe_output_rate'])}",
        f"- P50 / P95 / P99：{result['latency_ms']['p50']} / {result['latency_ms']['p95']} / {result['latency_ms']['p99']} ms", "",
        "## 分类结果", "", "| 分类 | 通过数 | 总数 | 通过率 |", "|---|---:|---:|---:|",
    ]
    lines.extend(f"| {key} | {value['passed']} | {value['total']} | {pct(value['pass_rate'])} |" for key, value in result["categories"].items())
    lines.extend(["", "> 当前报告反映被测环境的真实结果；mock 模型结果不得替代真实模型上线验收。", ""])
    (report_dir / "evaluation_latest.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "details"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
