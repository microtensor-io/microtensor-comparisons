from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx

API = os.environ.get("MT_API_URL", "https://api.microtensor.cloud")
MODEL = os.environ.get("MT_MODEL", "mt/ctx_compress")


def load_sessions(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def one(http: httpx.Client, key: str, row: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": row["system"]},
            {"role": "user", "content": row["user"]},
        ],
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    started = time.perf_counter()
    first = 0.0
    text: list[str] = []
    usage: dict[str, Any] = {}
    status = 0
    error = ""
    request_id = ""
    served_by: dict[str, Any] = {}
    try:
        with http.stream(
            "POST",
            API + "/v1/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {key}"},
            timeout=httpx.Timeout(600.0, connect=30.0),
        ) as response:
            status = response.status_code
            request_id = response.headers.get("x-request-id", "")
            if status != 200:
                error = response.read().decode("utf-8", "replace")[:300]
            else:
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except ValueError:
                        continue
                    if chunk.get("error"):
                        error = json.dumps(chunk["error"], ensure_ascii=False)[:300]
                        continue
                    if not first:
                        first = time.perf_counter()
                    for choice in chunk.get("choices") or []:
                        piece = (choice.get("delta") or {}).get("content")
                        if piece:
                            text.append(piece)
                    if chunk.get("usage"):
                        usage = dict(chunk["usage"])
                    if chunk.get("served_by"):
                        served_by = dict(chunk["served_by"])
                    if chunk.get("microtensor"):
                        served_by = dict(chunk["microtensor"])
    except httpx.HTTPError as exc:
        error = f"{type(exc).__name__}: {exc}"[:300]
    finished = time.perf_counter()
    if status == 200 and not error and not text:
        error = "the stream closed with no answer"
    return {
        "item_id": row["item_id"],
        "request_id": request_id,
        "status": status,
        "error": error,
        "ttft_s": round(first - started, 3) if first else None,
        "total_s": round(finished - started, 3),
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "session_tokens": row.get("input_tokens"),
        "served_by": served_by,
        "text": "".join(text),
        "started_at": time.time() - (finished - started),
    }


def read_url(url: str) -> str:
    try:
        with httpx.Client(timeout=15.0) as http:
            found = http.get(url)
        return found.text if found.status_code == 200 else ""
    except httpx.HTTPError:
        return ""


def parse_metrics(text: str) -> dict[str, float]:
    held: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        name, _, value = line.rpartition(" ")
        try:
            held[name] = held.get(name, 0.0) + float(value)
        except ValueError:
            continue
    return held


def bucket_quantile(
    before: dict[str, float], after: dict[str, float], metric: str, share: float
) -> float | None:
    rows: list[tuple[float, float]] = []
    for name, value in after.items():
        if not name.startswith(metric + "_bucket"):
            continue
        edge = name.split('le="', 1)[1].split('"', 1)[0]
        rows.append((float("inf") if edge == "+Inf" else float(edge), value - before.get(name, 0.0)))
    rows.sort()
    if not rows or rows[-1][1] <= 0:
        return None
    wanted = rows[-1][1] * share
    low, seen = 0.0, 0.0
    for edge, count in rows:
        if count >= wanted:
            if edge == float("inf") or count == seen:
                return round(low, 3)
            return round(low + (edge - low) * (wanted - seen) / (count - seen), 3)
        low, seen = edge, count
    return round(low, 3)


def engine_summary(before: dict[str, float], after: dict[str, float]) -> dict[str, Any]:
    def diff(metric: str) -> float:
        total = 0.0
        for name, value in after.items():
            if name == metric or name.startswith(metric + "{"):
                total += value - before.get(name, 0.0)
        return total

    def mean_ms(metric: str) -> float | None:
        count = diff(metric + "_count")
        return round(diff(metric + "_sum") / count * 1000, 2) if count else None

    ttft = "vllm:time_to_first_token_seconds"
    tpot = "vllm:request_time_per_output_token_seconds"
    e2e = "vllm:e2e_request_latency_seconds"
    tpot_p50 = bucket_quantile(before, after, tpot, 0.5)
    return {
        "engine_ttft_p50_s": bucket_quantile(before, after, ttft, 0.5),
        "engine_ttft_p95_s": bucket_quantile(before, after, ttft, 0.95),
        "engine_tpot_mean_ms": mean_ms(tpot),
        "engine_tpot_p50_ms": round(tpot_p50 * 1000, 2) if tpot_p50 is not None else None,
        "engine_total_p50_s": bucket_quantile(before, after, e2e, 0.5),
        "engine_total_p95_s": bucket_quantile(before, after, e2e, 0.95),
        "engine_requests": diff(e2e + "_count"),
        "engine_prompt_tokens": diff("vllm:prompt_tokens_total"),
        "engine_output_tokens": diff("vllm:generation_tokens_total"),
    }


def gpu_window(text: str, started: float, ended: float) -> dict[str, Any]:
    used: list[int] = []
    load: list[int] = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            moment = dt.datetime.fromisoformat(parts[0].replace("Z", "+00:00")).timestamp()
            if started <= moment <= ended:
                used.append(int(parts[1]))
                load.append(int(parts[3]))
        except ValueError:
            continue
    return {
        "gpu_memory_peak_mb": max(used) if used else None,
        "gpu_utilisation_mean": round(sum(load) / len(load), 1) if load else None,
    }


class CachePeak(threading.Thread):
    def __init__(self, url: str) -> None:
        super().__init__(daemon=True)
        self.url = url
        self.peak = 0.0
        self.running = True

    def run(self) -> None:
        while self.running:
            for name, value in parse_metrics(read_url(self.url)).items():
                if name.startswith(("vllm:gpu_cache_usage_perc", "vllm:kv_cache_usage_perc")):
                    self.peak = max(self.peak, value)
            time.sleep(5.0)


def level(
    sessions: list[dict[str, Any]],
    *,
    key: str,
    concurrency: int,
    seconds: float,
    out: Path,
    max_tokens: int,
    seed: int,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    order = list(sessions)
    rng.shuffle(order)
    cursor = {"n": 0}
    lock = threading.Lock()
    results: list[dict[str, Any]] = []
    deadline = time.monotonic() + seconds
    out.parent.mkdir(parents=True, exist_ok=True)
    handle = out.open("a", encoding="utf-8")

    def worker(index: int) -> None:
        with httpx.Client(http2=False) as http:
            while time.monotonic() < deadline:
                with lock:
                    row = order[cursor["n"] % len(order)]
                    cursor["n"] += 1
                found = one(http, key, row, max_tokens)
                if found["error"] or found["status"] != 200:
                    time.sleep(1.0)
                found["level"] = concurrency
                found["worker"] = index
                with lock:
                    results.append(found)
                    handle.write(json.dumps(found, ensure_ascii=False) + "\n")
                    handle.flush()
                    done = len(results)
                    errors = sum(1 for r in results if r["error"] or r["status"] != 200)
                print(
                    f"level {concurrency} worker {index}: {found['item_id']} status {found['status']} "
                    f"ttft {found['ttft_s']} total {found['total_s']} out {found['output_tokens']} "
                    f"({done} done, {errors} errors, {int(deadline - time.monotonic())}s left)",
                    flush=True,
                )

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(concurrency)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    handle.close()
    return results


def percentile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(share * (len(ordered) - 1))))
    return round(ordered[rank], 3)


def summarise(rows: list[dict[str, Any]], seconds: float) -> dict[str, Any]:
    ok = [r for r in rows if r["status"] == 200 and not r["error"]]
    ttft = [r["ttft_s"] for r in ok if r["ttft_s"] is not None]
    total = [r["total_s"] for r in ok]
    tpot = [
        (r["total_s"] - r["ttft_s"]) / r["output_tokens"] * 1000
        for r in ok
        if r["ttft_s"] is not None and r["output_tokens"]
    ]
    return {
        "requests": len(rows),
        "ok": len(ok),
        "errors": len(rows) - len(ok),
        "requests_per_hour": round(len(ok) / seconds * 3600, 1) if seconds else None,
        "ttft_p50_s": percentile(ttft, 0.5),
        "ttft_p95_s": percentile(ttft, 0.95),
        "tpot_ms": round(statistics.median(tpot), 1) if tpot else None,
        "total_p50_s": percentile(total, 0.5),
        "total_p95_s": percentile(total, 0.95),
        "input_tokens_mean": round(statistics.mean([r["input_tokens"] for r in ok if r["input_tokens"]]), 0)
        if any(r["input_tokens"] for r in ok)
        else None,
        "output_tokens_mean": round(statistics.mean([r["output_tokens"] for r in ok if r["output_tokens"]]), 0)
        if any(r["output_tokens"] for r in ok)
        else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", default="sessions.jsonl")
    parser.add_argument("--key-file", default="api_key.txt")
    parser.add_argument("--levels", default="1,4,8,16")
    parser.add_argument("--seconds", type=float, default=900.0)
    parser.add_argument("--max-tokens", type=int, default=3072)
    parser.add_argument("--out", default="results")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--pod-url", default="")
    args = parser.parse_args()
    key = Path(args.key_file).read_text(encoding="utf-8").strip()
    sessions = load_sessions(Path(args.sessions))
    out = Path(args.out)
    summary: dict[str, Any] = {}
    for n in [int(x) for x in args.levels.split(",") if x]:
        print(f"==> level {n} for {args.seconds:.0f}s", flush=True)
        started = time.time()
        before = parse_metrics(read_url(args.pod_url + "/vllm.prom")) if args.pod_url else {}
        watcher = CachePeak(args.pod_url + "/vllm.prom") if args.pod_url else None
        if watcher:
            watcher.start()
        rows = level(
            sessions,
            key=key,
            concurrency=n,
            seconds=args.seconds,
            out=out / f"level-{n}.jsonl",
            max_tokens=args.max_tokens,
            seed=args.seed + n,
        )
        ended = time.time()
        summary[str(n)] = {"started_at": started, "ended_at": ended, **summarise(rows, args.seconds)}
        if watcher:
            watcher.running = False
            time.sleep(6.0)
            after = parse_metrics(read_url(args.pod_url + "/vllm.prom"))
            summary[str(n)].update(engine_summary(before, after))
            summary[str(n)]["kv_cache_peak"] = round(watcher.peak, 4)
            summary[str(n)].update(gpu_window(read_url(args.pod_url + "/gpu.csv"), started, ended))
        (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        print(json.dumps(summary[str(n)]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
