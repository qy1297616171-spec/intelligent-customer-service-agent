import argparse
import json
import os
import sys

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="智能客服部署验收")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:9091")
    parser.add_argument("--grafana-url", default="http://127.0.0.1:3001")
    parser.add_argument("--email", default=os.getenv("VERIFY_EMAIL", "admin@example.com"))
    parser.add_argument("--password", default=os.getenv("VERIFY_PASSWORD", "ChangeMe123!"))
    parser.add_argument("--require-real-model", action="store_true")
    args = parser.parse_args()
    checks: list[dict] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    try:
        with httpx.Client(timeout=10, trust_env=False) as client:
            health = client.get(f"{args.base_url}/health")
            record("api_health", health.status_code == 200 and health.json().get("status") == "ok", health.text)
            login = client.post(f"{args.base_url}/api/v1/auth/login", json={"email": args.email, "password": args.password})
            record("authentication", login.status_code == 200, str(login.status_code))
            model = client.get(f"{args.base_url}/model-status")
            model_data = model.json() if model.status_code == 200 else {}
            real_model = bool(model_data.get("configured")) and model_data.get("provider") != "mock"
            record("real_model", real_model or not args.require_real_model, json.dumps(model_data, ensure_ascii=False))
            metrics = client.get(f"{args.base_url}/metrics")
            record("metrics", metrics.status_code == 200 and "customer_service_http_requests_total" in metrics.text, str(metrics.status_code))
            prometheus = client.get(f"{args.prometheus_url}/-/ready")
            record("prometheus", prometheus.status_code == 200, prometheus.text)
            grafana = client.get(f"{args.grafana_url}/api/health")
            record("grafana", grafana.status_code == 200 and grafana.json().get("database") == "ok", grafana.text)
    except httpx.HTTPError as exc:
        record("connectivity", False, str(exc))

    passed = all(check["passed"] for check in checks)
    print(json.dumps({"passed": passed, "checks": checks}, ensure_ascii=False, indent=2))
    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
