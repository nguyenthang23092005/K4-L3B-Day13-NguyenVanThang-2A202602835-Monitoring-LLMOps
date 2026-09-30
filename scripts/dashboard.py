from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
DASHBOARD_PATH = REPO_ROOT / "dashboard" / "index.html"
CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (AttributeError, ValueError):
        return None


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def load_records(now: datetime) -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    cutoff = now - timedelta(minutes=60)
    records: list[dict[str, Any]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        timestamp = parse_timestamp(record.get("ts", ""))
        if timestamp is not None and timestamp >= cutoff:
            record["_timestamp"] = timestamp
            records.append(record)
    return records


def minute_key(timestamp: datetime) -> str:
    return timestamp.replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z")


def aggregate_dashboard() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    records = load_records(now)
    responses = [record for record in records if record.get("event") == "response_sent"]
    requests = [record for record in records if record.get("event") == "request_received"]
    failures = [record for record in records if record.get("event") == "request_failed"]
    tool_events = [record for record in records if record.get("tool_success") is not None]

    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "requests": 0,
            "failures": 0,
            "latencies": [],
            "ttfts": [],
            "cost": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
            "qualities": [],
            "tool_total": 0,
            "tool_success": 0,
        }
    )
    for record in records:
        bucket = buckets[minute_key(record["_timestamp"])]
        event = record.get("event")
        if event == "request_received":
            bucket["requests"] += 1
        elif event == "request_failed":
            bucket["failures"] += 1
        elif event == "response_sent":
            bucket["latencies"].append(float(record.get("latency_ms", 0)))
            bucket["ttfts"].append(float(record.get("ttft_ms", 0)))
            bucket["cost"] += float(record.get("cost_usd", 0))
            bucket["tokens_in"] += int(record.get("tokens_in", 0))
            bucket["tokens_out"] += int(record.get("tokens_out", 0))
            bucket["qualities"].append(float(record.get("quality_score", 0)))
        if record.get("tool_success") is not None:
            bucket["tool_total"] += 1
            bucket["tool_success"] += int(record.get("tool_success") is True)

    points: list[dict[str, Any]] = []
    for timestamp in sorted(buckets):
        bucket = buckets[timestamp]
        request_count = bucket["requests"]
        tool_total = bucket["tool_total"]
        points.append(
            {
                "ts": timestamp,
                "latency_p95": round(percentile(bucket["latencies"], 0.95), 2),
                "ttft_p95": round(percentile(bucket["ttfts"], 0.95), 2),
                "requests": request_count,
                "error_rate": round(bucket["failures"] / request_count * 100, 2) if request_count else 0,
                "retrieval_success": round(bucket["tool_success"] / tool_total * 100, 2) if tool_total else 100,
                "cost": round(bucket["cost"], 6),
                "tokens_in": bucket["tokens_in"],
                "tokens_out": bucket["tokens_out"],
                "quality": round(sum(bucket["qualities"]) / len(bucket["qualities"]), 3) if bucket["qualities"] else 0,
            }
        )

    latencies = [float(record.get("latency_ms", 0)) for record in responses]
    ttfts = [float(record.get("ttft_ms", 0)) for record in responses]
    qualities = [float(record.get("quality_score", 0)) for record in responses]
    with CONFIG_PATH.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)["dashboard"]
    thresholds = {
        panel["id"]: panel["threshold"]["value"] for panel in config["panels"]
    }

    return {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "time_range_minutes": config["time_range_minutes"],
        "refresh_seconds": config["refresh_seconds"],
        "thresholds": thresholds,
        "summary": {
            "latency_p50": round(percentile(latencies, 0.50), 2),
            "latency_p95": round(percentile(latencies, 0.95), 2),
            "latency_p99": round(percentile(latencies, 0.99), 2),
            "ttft_p95": round(percentile(ttfts, 0.95), 2),
            "request_count": len(requests),
            "rate_per_minute": round(len(requests) / 60, 2),
            "error_rate": round(len(failures) / len(requests) * 100, 2) if requests else 0,
            "retrieval_success": round(sum(record.get("tool_success") is True for record in tool_events) / len(tool_events) * 100, 2) if tool_events else 100,
            "cost_total": round(sum(float(record.get("cost_usd", 0)) for record in responses), 6),
            "tokens_in": sum(int(record.get("tokens_in", 0)) for record in responses),
            "tokens_out": sum(int(record.get("tokens_out", 0)) for record in responses),
            "quality_avg": round(sum(qualities) / len(qualities), 3) if qualities else 0,
        },
        "points": points,
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/dashboard":
            payload = json.dumps(aggregate_dashboard(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path in {"/", "/index.html"}:
            payload = DASHBOARD_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_error(404)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[dashboard] {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the six-panel JSONL dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8501, type=int)
    args = parser.parse_args()
    if not DASHBOARD_PATH.exists():
        print(f"Dashboard UI not found: {DASHBOARD_PATH}", file=sys.stderr)
        raise SystemExit(1)
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Dashboard: http://{args.host}:{args.port}")
    print(f"Source: {LOG_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
