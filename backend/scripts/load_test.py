"""Reliable async load test runner for VisionSafe FastAPI backend.

Capabilities:
- 100-1000+ concurrent HTTP users
- burst traffic against incidents endpoint
- concurrent WebSocket users
- retries with exponential backoff
- fail-fast if early failure rate is too high
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import websockets
from websockets.exceptions import ConnectionClosed


DEFAULT_INCIDENT_PATH = "/api/v1/incidents"
DEFAULT_WS_PATH = "/api/v1/ws/incidents"
DEFAULT_HEALTH_PATH = "/api/health"
MAX_RETRIES = 3
FAIL_FAST_WINDOW_SEC = 10
FAIL_FAST_ERROR_THRESHOLD = 0.50


@dataclass
class EndpointStats:
    request_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    def record(self, status_code: int, latency_ms: float) -> None:
        self.request_count += 1
        self.latencies_ms.append(latency_ms)
        if status_code < 400:
            self.success_count += 1
        else:
            self.failed_count += 1

    def to_summary(self) -> dict[str, float | int]:
        success_rate = (self.success_count / self.request_count * 100.0) if self.request_count else 0.0
        avg_latency = statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0
        return {
            "request_count": self.request_count,
            "success_rate_pct": round(success_rate, 2),
            "avg_latency_ms": round(avg_latency, 2),
        }


@dataclass
class MetricsCollector:
    total_requests: int = 0
    success_requests: int = 0
    failed_requests: int = 0
    total_rate_limited: int = 0
    total_ws_attempts: int = 0
    total_ws_connected: int = 0
    total_ws_errors: int = 0
    response_times_ms: list[float] = field(default_factory=list)
    status_counts: dict[int, int] = field(default_factory=dict)
    rate_limit_retry_after: list[int] = field(default_factory=list)
    endpoint_stats: dict[str, EndpointStats] = field(default_factory=dict)
    started_at: float = 0.0
    ended_at: float = 0.0

    def mark_start(self) -> None:
        self.started_at = time.perf_counter()

    def mark_end(self) -> None:
        self.ended_at = time.perf_counter()

    def record_http(
        self,
        endpoint: str,
        elapsed_ms: float,
        status_code: int,
        retry_after: str | None = None,
    ) -> None:
        self.total_requests += 1
        self.response_times_ms.append(elapsed_ms)
        self.status_counts[status_code] = self.status_counts.get(status_code, 0) + 1

        stats = self.endpoint_stats.setdefault(endpoint, EndpointStats())
        stats.record(status_code=status_code, latency_ms=elapsed_ms)

        if status_code < 400:
            self.success_requests += 1
        else:
            self.failed_requests += 1

        if status_code == 429:
            self.total_rate_limited += 1
            if retry_after is not None:
                try:
                    self.rate_limit_retry_after.append(int(float(retry_after)))
                except ValueError:
                    pass

    def record_ws_attempt(self) -> None:
        self.total_ws_attempts += 1

    def record_ws_connected(self) -> None:
        self.total_ws_connected += 1

    def record_ws_error(self) -> None:
        self.total_ws_errors += 1

    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests

    def _percentile(self, percentile: int) -> float:
        if not self.response_times_ms:
            return 0.0
        if percentile == 50:
            return statistics.median(self.response_times_ms)
        if percentile == 95:
            if len(self.response_times_ms) >= 20:
                return statistics.quantiles(self.response_times_ms, n=100)[94]
            return max(self.response_times_ms)
        if percentile == 99:
            if len(self.response_times_ms) >= 100:
                return statistics.quantiles(self.response_times_ms, n=100)[98]
            return max(self.response_times_ms)
        raise ValueError("Unsupported percentile")

    def _rps(self) -> float:
        duration = max(0.0, self.ended_at - self.started_at)
        if duration <= 0 or self.total_requests == 0:
            return 0.0
        return self.total_requests / duration

    def summary(self) -> dict[str, Any]:
        avg = statistics.mean(self.response_times_ms) if self.response_times_ms else 0.0
        p50 = self._percentile(50)
        p95 = self._percentile(95)
        p99 = self._percentile(99)

        error_rate_pct = self.error_rate() * 100.0
        success_rate_pct = 100.0 - error_rate_pct
        rate_limited_pct = (
            (self.total_rate_limited / self.total_requests) * 100.0 if self.total_requests else 0.0
        )
        ws_error_rate_pct = (
            (self.total_ws_errors / self.total_ws_attempts) * 100.0 if self.total_ws_attempts else 0.0
        )

        endpoint_breakdown = {
            endpoint: stats.to_summary() for endpoint, stats in sorted(self.endpoint_stats.items())
        }

        return {
            "total_requests": self.total_requests,
            "success_requests": self.success_requests,
            "failed_requests": self.failed_requests,
            "success_rate_pct": round(success_rate_pct, 2),
            "error_rate_pct": round(error_rate_pct, 2),
            "rps": round(self._rps(), 2),
            "rate_limited": self.total_rate_limited,
            "rate_limited_pct": round(rate_limited_pct, 2),
            "avg_latency_ms": round(avg, 2),
            "p50_latency_ms": round(p50, 2),
            "p95_latency_ms": round(p95, 2),
            "p99_latency_ms": round(p99, 2),
            "ws_attempts": self.total_ws_attempts,
            "ws_connected": self.total_ws_connected,
            "ws_errors": self.total_ws_errors,
            "ws_error_rate_pct": round(ws_error_rate_pct, 2),
            "status_counts": dict(sorted(self.status_counts.items())),
            "retry_after_samples": self.rate_limit_retry_after[:20],
            "endpoint_breakdown": endpoint_breakdown,
        }


@dataclass
class RequestExecutor:
    client: httpx.AsyncClient
    metrics: MetricsCollector
    slow_threshold_ms: float
    debug: bool

    async def post_with_retry(
        self,
        endpoint: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> None:
        for attempt in range(1, MAX_RETRIES + 1):
            start = time.perf_counter()
            try:
                response = await self.client.post(endpoint, json=payload, headers=headers)
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                self.metrics.record_http(
                    endpoint=endpoint,
                    elapsed_ms=elapsed_ms,
                    status_code=response.status_code,
                    retry_after=response.headers.get("retry-after"),
                )

                if self.debug and elapsed_ms > self.slow_threshold_ms:
                    print(
                        f"[debug] slow request endpoint={endpoint} "
                        f"latency_ms={elapsed_ms:.2f} status={response.status_code}"
                    )

                should_retry = response.status_code >= 500
                if should_retry and attempt < MAX_RETRIES:
                    backoff = 0.25 * (2 ** (attempt - 1))
                    if self.debug:
                        print(
                            f"[debug] retrying request_id={headers.get('x-request-id')} "
                            f"endpoint={endpoint} status={response.status_code} "
                            f"attempt={attempt} backoff={backoff:.2f}s"
                        )
                    await asyncio.sleep(backoff)
                    continue
                return

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                if attempt < MAX_RETRIES:
                    backoff = 0.25 * (2 ** (attempt - 1))
                    if self.debug:
                        print(
                            f"[debug] request exception type={type(exc).__name__} endpoint={endpoint} "
                            f"attempt={attempt} backoff={backoff:.2f}s err={exc}"
                        )
                    await asyncio.sleep(backoff)
                    continue

                if self.debug:
                    print(
                        f"[debug] request failed permanently endpoint={endpoint} "
                        f"type={type(exc).__name__} err={exc}"
                    )
                self.metrics.record_http(endpoint=endpoint, elapsed_ms=elapsed_ms, status_code=599)
                return


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_headers(token: str | None, request_id: str) -> dict[str, str]:
    headers = {"x-request-id": request_id, "content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    return headers


def _incident_payload(source_id: str, index: int) -> dict[str, Any]:
    stamp = _now_utc()
    return {
        "id": f"LT-{source_id}-{index}-{uuid.uuid4().hex[:8]}",
        "zone": random.choice(["Zone A", "Zone B", "Zone C", "Forklift Lane", "Dock 04"]),
        "classification": random.choice(["Fall", "Near Miss", "Forklift Proximity", "Unsafe Posture"]),
        "severity": random.choice(["Low", "Medium", "High"]),
        "root_cause": random.choice(
            [
                "Temporary obstruction in aisle",
                "Operator blind spot",
                "Loss of balance",
                "Unsafe hand placement",
            ]
        ),
        "corrective_action": random.choice(
            [
                "Review signage and barriers",
                "Increase safety briefing",
                "Inspect camera view",
                "Reinforce PPE compliance",
            ]
        ),
        "created_at": stamp,
    }


async def _precheck_backend(client: httpx.AsyncClient, base_url: str, debug: bool) -> None:
    """Check backend reachability before launching load traffic."""
    try:
        response = await client.get(DEFAULT_HEALTH_PATH)
    except Exception as exc:
        if debug:
            print(f"[debug] backend pre-check exception: {type(exc).__name__}: {exc}")
        raise SystemExit(f"Backend is not running on {base_url}") from exc

    if response.status_code >= 500:
        if debug:
            print(f"[debug] health endpoint returned status={response.status_code} body={response.text[:200]}")
        raise SystemExit(f"Backend is not running on {base_url}")


async def _burst_incident_writer(
    executor: RequestExecutor,
    incidents_path: str,
    token: str | None,
    source_id: str,
    burst_size: int,
    burst_pause_sec: float,
    stop_event: asyncio.Event,
    user_index: int,
) -> None:
    """One task per user to preserve concurrency accuracy.

    Each user sends burst_size sequential requests then pauses.
    """

    seq = 0
    while not stop_event.is_set():
        for _ in range(burst_size):
            if stop_event.is_set():
                break
            seq += 1
            request_id = f"lt-{user_index}-{seq}-{uuid.uuid4().hex[:8]}"
            payload = _incident_payload(source_id=source_id, index=seq)
            headers = _build_headers(token, request_id)
            await executor.post_with_retry(endpoint=incidents_path, payload=payload, headers=headers)

        if burst_pause_sec > 0:
            await asyncio.sleep(burst_pause_sec)


async def _ws_user(
    ws_path: str,
    ws_base_url: str,
    token: str | None,
    metrics: MetricsCollector,
    duration_sec: float,
    user_index: int,
    debug: bool,
) -> None:
    metrics.record_ws_attempt()
    request_id = f"ws-{user_index}-{uuid.uuid4().hex[:8]}"
    ws_url = f"{ws_base_url.rstrip('/')}{ws_path}"
    if token:
        ws_url = f"{ws_url}?token={token}"

    headers = {"x-request-id": request_id}
    if token:
        headers["authorization"] = f"Bearer {token}"

    try:
        async with websockets.connect(ws_url, extra_headers=headers, open_timeout=10, close_timeout=5) as ws:
            metrics.record_ws_connected()
            deadline = time.perf_counter() + duration_sec
            while time.perf_counter() < deadline:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    await asyncio.sleep(0.25)
                except ConnectionClosed:
                    break
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        metrics.record_ws_error()
        if debug:
            print(f"[debug] websocket user={user_index} error type={type(exc).__name__} err={exc}")


async def _fail_fast_guard(
    metrics: MetricsCollector,
    stop_event: asyncio.Event,
    debug: bool,
) -> None:
    await asyncio.sleep(FAIL_FAST_WINDOW_SEC)
    if stop_event.is_set():
        return

    if metrics.total_requests == 0:
        if debug:
            print("[debug] fail-fast guard skipped (no requests in first window)")
        return

    if metrics.error_rate() > FAIL_FAST_ERROR_THRESHOLD:
        print(
            "Fail-fast triggered: more than 50% of requests failed in the first 10 seconds. "
            "Stopping test early."
        )
        stop_event.set()


async def _runner(args: argparse.Namespace) -> MetricsCollector:
    metrics = MetricsCollector()
    stop_event = asyncio.Event()

    timeout = httpx.Timeout(20.0, connect=10.0)
    # Keep transport bounded while still supporting target user concurrency.
    limits = httpx.Limits(max_connections=max(args.users, 100), max_keepalive_connections=max(args.users, 50))

    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout, limits=limits) as client:
        await _precheck_backend(client, args.base_url, args.debug)

        executor = RequestExecutor(
            client=client,
            metrics=metrics,
            slow_threshold_ms=args.slow_threshold_ms,
            debug=args.debug,
        )

        metrics.mark_start()

        burst_tasks = [
            asyncio.create_task(
                _burst_incident_writer(
                    executor=executor,
                    incidents_path=args.incidents_path,
                    token=args.token,
                    source_id=args.source_id,
                    burst_size=args.burst_size,
                    burst_pause_sec=args.burst_pause_sec,
                    stop_event=stop_event,
                    user_index=i,
                )
            )
            for i in range(args.users)
        ]

        ws_tasks = [
            asyncio.create_task(
                _ws_user(
                    ws_path=args.ws_path,
                    ws_base_url=args.ws_base_url,
                    token=args.token,
                    metrics=metrics,
                    duration_sec=args.duration,
                    user_index=i,
                    debug=args.debug,
                )
            )
            for i in range(args.ws_users)
        ]

        fail_fast_task = asyncio.create_task(_fail_fast_guard(metrics, stop_event, args.debug))

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=args.duration)
        except asyncio.TimeoutError:
            pass
        finally:
            stop_event.set()
            for task in burst_tasks:
                task.cancel()
            await asyncio.gather(*burst_tasks, return_exceptions=True)
            await asyncio.gather(*ws_tasks, return_exceptions=True)
            fail_fast_task.cancel()
            await asyncio.gather(fail_fast_task, return_exceptions=True)
            metrics.mark_end()

    return metrics


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VisionSafe 360 load test runner")
    parser.add_argument("--base-url", default=os.getenv("VISIONSAFE_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--ws-base-url", default=os.getenv("VISIONSAFE_WS_BASE_URL", "ws://127.0.0.1:8000"))
    parser.add_argument("--incidents-path", default=os.getenv("VISIONSAFE_INCIDENTS_PATH", DEFAULT_INCIDENT_PATH))
    parser.add_argument("--ws-path", default=os.getenv("VISIONSAFE_WS_PATH", DEFAULT_WS_PATH))
    parser.add_argument("--users", type=int, default=100, help="Concurrent HTTP users (100-1000 recommended)")
    parser.add_argument("--ws-users", type=int, default=20, help="Concurrent websocket users")
    parser.add_argument("--duration", type=float, default=60.0, help="Test duration in seconds")
    parser.add_argument("--burst-size", type=int, default=10, help="Requests per user per burst")
    parser.add_argument("--burst-pause-sec", type=float, default=0.2, help="Pause between bursts")
    parser.add_argument(
        "--token",
        default=os.getenv("VISIONSAFE_TOKEN"),
        help="Bearer token. Auto-injected from VISIONSAFE_TOKEN if not passed.",
    )
    parser.add_argument("--allow-missing-token", action="store_true", help="Bypass token requirement.")
    parser.add_argument("--source-id", default=os.getenv("VISIONSAFE_SOURCE_ID", "cam_01"), help="Incident source identifier")
    parser.add_argument("--slow-threshold-ms", type=float, default=1000.0, help="Slow request threshold for debug logging")
    parser.add_argument("--debug", action="store_true", help="Print detailed request and websocket errors")
    parser.add_argument("--output-json", action="store_true", help="Print final results as JSON")
    parser.add_argument("--output-json-file", default="", help="Optional file path to export JSON summary")
    parser.add_argument("--history-file", default="results.json", help="JSON file to append historical run results")
    parser.add_argument("--set-baseline", action="store_true", help="Save current run as performance baseline")
    parser.add_argument("--compare-baseline", action="store_true", help="Compare current run against saved baseline")
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> None:
    if args.users < 1:
        raise SystemExit("--users must be at least 1")
    if args.ws_users < 0:
        raise SystemExit("--ws-users cannot be negative")
    if args.duration <= 0:
        raise SystemExit("--duration must be positive")
    if args.burst_size < 1:
        raise SystemExit("--burst-size must be at least 1")
    if args.slow_threshold_ms <= 0:
        raise SystemExit("--slow-threshold-ms must be positive")

    token_required = not args.allow_missing_token
    if token_required and not args.token:
        raise SystemExit("Missing VISIONSAFE_TOKEN. Please login and export the token.")


def _print_endpoint_breakdown(summary: dict[str, Any]) -> None:
    breakdown = summary.get("endpoint_breakdown", {})
    if not breakdown:
        return

    print("Endpoint Breakdown:")
    print("  Endpoint                    Requests   Success%   AvgLatency(ms)")
    for endpoint, stats in breakdown.items():
        print(
            f"  {endpoint:<27} {stats['request_count']:>8}   "
            f"{stats['success_rate_pct']:>7.2f}%   {stats['avg_latency_ms']:>13.2f}"
        )


def _print_human_summary(summary: dict[str, Any]) -> None:
    print("===== LOAD TEST SUMMARY =====")
    print(f"Users: {summary['users']}")
    print(f"Duration: {int(summary['duration_sec'])}s")
    print(f"Total Requests: {summary['total_requests']}")
    print(f"RPS: {summary['rps']}")
    print(f"Success Rate: {summary['success_rate_pct']}%")
    print(f"Avg Latency: {summary['avg_latency_ms']} ms")
    print(f"P50 Latency: {summary['p50_latency_ms']} ms")
    print(f"P95 Latency: {summary['p95_latency_ms']} ms")
    print(f"P99 Latency: {summary['p99_latency_ms']} ms")
    print(f"Errors: {summary['failed_requests']}")
    print("============================")

    print(f"Rate Limited (429): {summary['rate_limited']} ({summary['rate_limited_pct']}%)")
    print(f"WebSocket Connected: {summary['ws_connected']}/{summary['ws_attempts']}")
    print(f"Status Codes: {summary['status_counts']}")
    if summary["retry_after_samples"]:
        print(f"Retry-After Samples: {summary['retry_after_samples']}")
    _print_endpoint_breakdown(summary)


def _comparison_delta_pct(current: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0
    return ((current - baseline) / baseline) * 100.0


def _build_history_record(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": _utc_iso(),
        "users": summary.get("users"),
        "duration": summary.get("duration_sec"),
        "rps": summary.get("rps"),
        "p50": summary.get("p50_latency_ms"),
        "p95": summary.get("p95_latency_ms"),
        "p99": summary.get("p99_latency_ms"),
        "error_rate": summary.get("error_rate_pct"),
    }


def _read_json_file(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _append_history(history_file: Path, record: dict[str, Any]) -> None:
    existing = _read_json_file(history_file)
    if existing is None:
        payload: list[dict[str, Any]] = []
    elif isinstance(existing, list):
        payload = existing
    else:
        # Recover gracefully if file previously held a single object.
        payload = [existing]
    payload.append(record)
    _write_json_file(history_file, payload)


def _baseline_file_from_history(history_file: Path) -> Path:
    return history_file.with_name(f"{history_file.stem}.baseline{history_file.suffix}")


def _save_baseline(history_file: Path, record: dict[str, Any]) -> Path:
    baseline_file = _baseline_file_from_history(history_file)
    _write_json_file(baseline_file, record)
    return baseline_file


def _load_baseline(history_file: Path) -> dict[str, Any] | None:
    baseline_file = _baseline_file_from_history(history_file)
    payload = _read_json_file(baseline_file)
    if isinstance(payload, dict):
        return payload
    return None


def _compare_with_baseline(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    rps_change_pct = _comparison_delta_pct(float(current.get("rps", 0.0)), float(baseline.get("rps", 0.0)))
    p95_change_pct = _comparison_delta_pct(float(current.get("p95", 0.0)), float(baseline.get("p95", 0.0)))
    error_rate_change = float(current.get("error_rate", 0.0)) - float(baseline.get("error_rate", 0.0))

    regression = p95_change_pct > 20.0 or error_rate_change > 5.0
    return {
        "rps_change_pct": round(rps_change_pct, 2),
        "p95_change_pct": round(p95_change_pct, 2),
        "error_rate_change_pct_points": round(error_rate_change, 2),
        "regression_detected": regression,
    }


def _print_baseline_comparison(comparison: dict[str, Any]) -> None:
    print("Baseline Comparison:")
    print(f"  RPS Change: {comparison['rps_change_pct']}%")
    print(f"  P95 Change: {comparison['p95_change_pct']}%")
    print(f"  Error Rate Change: {comparison['error_rate_change_pct_points']} pp")
    if comparison.get("regression_detected"):
        print("Performance regression detected")


def main() -> None:
    args = _parse_args()
    _validate_args(args)

    try:
        metrics = asyncio.run(_runner(args))
    except KeyboardInterrupt:
        raise SystemExit("Load test interrupted by user")

    summary = metrics.summary()
    summary.update(
        {
            "base_url": args.base_url,
            "ws_base_url": args.ws_base_url,
            "incidents_path": args.incidents_path,
            "ws_path": args.ws_path,
            "users": args.users,
            "ws_users": args.ws_users,
            "duration_sec": args.duration,
            "burst_size": args.burst_size,
            "burst_pause_sec": args.burst_pause_sec,
            "token_provided": bool(args.token),
            "slow_threshold_ms": args.slow_threshold_ms,
        }
    )

    history_file = Path(args.history_file)
    history_record = _build_history_record(summary)
    _append_history(history_file, history_record)

    if args.set_baseline:
        baseline_path = _save_baseline(history_file, history_record)
        summary["baseline_file"] = str(baseline_path)

    if args.compare_baseline:
        baseline = _load_baseline(history_file)
        if baseline is None:
            summary["baseline_comparison"] = {
                "available": False,
                "message": "No baseline found. Run with --set-baseline first.",
            }
        else:
            comparison = _compare_with_baseline(history_record, baseline)
            comparison["available"] = True
            summary["baseline_comparison"] = comparison

    if args.output_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _print_human_summary(summary)
        print(f"History File: {history_file}")
        if args.set_baseline:
            print(f"Baseline saved to: {summary.get('baseline_file')}")
        if args.compare_baseline:
            baseline_comparison = summary.get("baseline_comparison", {})
            if baseline_comparison.get("available"):
                _print_baseline_comparison(baseline_comparison)
            else:
                print(str(baseline_comparison.get("message", "No baseline comparison available.")))

    if args.output_json_file:
        with open(args.output_json_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, sort_keys=True)
        if args.debug:
            print(f"[debug] JSON summary written to {args.output_json_file}")


if __name__ == "__main__":
    main()
