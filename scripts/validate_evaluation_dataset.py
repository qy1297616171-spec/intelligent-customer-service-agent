import json
from collections import Counter
from pathlib import Path


def main() -> None:
    root = Path(__file__).parents[1]
    dataset = root / "evaluation" / "datasets" / "ecommerce_qa_v1.jsonl"
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    ids = [case["id"] for case in cases]
    required = {
        "id", "category", "question", "expected_answer_type",
        "expected_keywords", "forbidden_keywords", "tenant_id", "risk_level",
    }
    assert 100 <= len(cases) <= 300
    assert len(ids) == len(set(ids))
    assert all(required <= case.keys() for case in cases)
    assert all(case["question"].strip() for case in cases)
    categories = Counter(case["category"] for case in cases)
    types = Counter(case["expected_answer_type"] for case in cases)
    report = [
        "# 电商客服评测集质量报告",
        "",
        f"- 数据集版本：ecommerce_qa_v1",
        f"- 用例总数：{len(cases)}",
        f"- 场景分类数：{len(categories)}",
        f"- ID 唯一性：通过",
        f"- 必填字段完整性：通过",
        "",
        "## 答案类型分布",
        "",
    ]
    report.extend(f"- {key}: {value}" for key, value in sorted(types.items()))
    report.extend(["", "## 场景分布", ""])
    report.extend(f"- {key}: {value}" for key, value in sorted(categories.items()))
    report_path = root / "evaluation" / "reports" / "dataset_quality.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"validated {len(cases)} cases; report: {report_path}")


if __name__ == "__main__":
    main()
