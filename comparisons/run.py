from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

from comparisons import prompts
from comparisons.prompts import read_rows

SEED = 0
API_SEED = 576
CALL_SECONDS = 900.0
ATTEMPTS = 3
PAUSE_SECONDS = 20.0
STREAM_QUIET_SECONDS = float(os.environ.get("STREAM_QUIET_SECONDS", "45"))
STREAM_ATTEMPTS = 8
STREAM_PAUSE_SECONDS = 5.0
WARM_PROMPT = "Reply with the single word ready."
SERVED_NAME = "slm"
LOCK = threading.Lock()


def render(template: str, task: dict[str, Any]) -> str:
    rendered = template
    for key, value in task.items():
        rendered = rendered.replace("{" + str(key) + "}", str(value))
    return rendered


def arena_prompt(arena_id: str) -> tuple[str, list[str]]:
    from arenas import definition

    slm = definition.load(arena_id)["slm"]
    return str(slm["prompt"]), [str(s) for s in slm.get("stop") or []]


def append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def done(path: Path, key: str) -> set[str]:
    return {row[key] for row in read_rows(path) if not row.get("error")}


def generate(
    endpoint: str, prompt: str, stop: list[str], max_tokens: int
) -> dict[str, Any]:
    body = {
        "model": SERVED_NAME,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0,
        "seed": SEED,
        "stream": True,
        "stream_options": {"include_usage": True},
        "stop": stop,
    }
    started = time.perf_counter()
    first: float | None = None
    text: list[str] = []
    usage: dict[str, Any] = {}
    with httpx.Client(timeout=CALL_SECONDS) as http:
        with http.stream(
            "POST", endpoint.rstrip("/") + "/v1/completions", json=body
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                if chunk.get("usage"):
                    usage = dict(chunk["usage"])
                for choice in chunk.get("choices") or []:
                    piece = str(choice.get("text") or "")
                    if piece and first is None:
                        first = time.perf_counter()
                    text.append(piece)
    ended = time.perf_counter()
    return {
        "text": "".join(text),
        "input_tokens": int(usage.get("prompt_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or 0),
        "ttft_ms": round(((first or ended) - started) * 1000, 1),
        "total_ms": round((ended - started) * 1000, 1),
    }


def engine(args: argparse.Namespace) -> int:
    items = prompts.load_items(Path(args.items))
    template, stop = arena_prompt(args.arena)
    out = Path(args.work) / "outputs" / f"{args.contestant}.jsonl"
    have = done(out, "item_id")
    generate(
        args.endpoint, render(template, {"system": "", "user": WARM_PROMPT}), stop, 8
    )
    for position, item in enumerate(items, 1):
        if item["item_id"] in have:
            continue
        row: dict[str, Any] = {
            "contestant": args.contestant,
            "item_id": item["item_id"],
            "weights_sha256": args.weights,
            "card": args.card,
            "max_tokens": prompts.MAX_SUMMARY_TOKENS,
            "seed": SEED,
        }
        try:
            row.update(
                generate(
                    args.endpoint,
                    render(template, item["task"]),
                    stop,
                    prompts.MAX_SUMMARY_TOKENS,
                )
            )
        except (httpx.HTTPError, ValueError) as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"[:400]
        append(out, row)
        print(
            position,
            item["item_id"],
            row.get("output_tokens"),
            row.get("total_ms"),
            flush=True,
        )
    return 0


def stream_chat(endpoint: str, key: str, job: dict[str, Any]) -> dict[str, Any]:
    body = {
        "model": job["model"],
        "messages": job["messages"],
        "max_tokens": job.get("max_tokens") or prompts.MAX_SUMMARY_TOKENS,
        "temperature": 0,
        "seed": API_SEED,
        "stream": True,
        "stream_options": {"include_usage": True},
        "return_progress": True,
        "cache_prompt": bool(job.get("cache_prompt", True)),
        "chat_template_kwargs": {"enable_thinking": False},
    }
    started = time.perf_counter()
    first: float | None = None
    text: list[str] = []
    usage: dict[str, Any] = {}
    timings: dict[str, Any] = {}
    finish = ""
    quiet = httpx.Timeout(CALL_SECONDS, read=STREAM_QUIET_SECONDS)
    with httpx.Client(timeout=quiet) as http:
        with http.stream(
            "POST",
            endpoint.rstrip("/") + "/chat/completions",
            json=body,
            headers={"authorization": f"Bearer {key}"},
        ) as response:
            if response.status_code >= 400:
                response.read()
                raise ValueError(f"{response.status_code}: {response.text[:200]}")
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                if chunk.get("error"):
                    raise ValueError(str(chunk["error"])[:200])
                if chunk.get("usage"):
                    usage = dict(chunk["usage"])
                if chunk.get("timings"):
                    timings = dict(chunk["timings"])
                for choice in chunk.get("choices") or []:
                    piece = str((choice.get("delta") or {}).get("content") or "")
                    if piece and first is None:
                        first = time.perf_counter()
                    text.append(piece)
                    finish = str(choice.get("finish_reason") or finish)
    ended = time.perf_counter()
    if not usage:
        raise ValueError("the stream ended without usage")
    elapsed = round((ended - started) * 1000)
    return {
        "text": "".join(text),
        "finish_reason": finish,
        "tokens_in": int(usage.get("prompt_tokens") or 0),
        "tokens_out": int(usage.get("completion_tokens") or 0),
        "ttft_ms": round(((first or ended) - started) * 1000),
        "latency_ms": elapsed,
        "wall_ms": elapsed,
        "cached_tokens": int(timings.get("cache_n") or 0),
        "server_prompt_ms": round(float(timings.get("prompt_ms") or 0)),
        "server_predicted_ms": round(float(timings.get("predicted_ms") or 0)),
    }


def chat(endpoint: str, key: str, job: dict[str, Any]) -> dict[str, Any]:
    listed = prompts.LIST_PRICES.get(job["model"]) or {}
    body = {
        "model": listed.get("provider_model") or job["model"],
        "messages": job["messages"],
        "max_tokens": job.get("max_tokens") or prompts.MAX_SUMMARY_TOKENS,
        "temperature": 0,
        "seed": API_SEED,
    }
    started = time.perf_counter()
    with httpx.Client(timeout=CALL_SECONDS) as http:
        response = http.post(
            endpoint.rstrip("/") + "/chat/completions",
            json=body,
            headers={"authorization": f"Bearer {key}"},
        )
    response.raise_for_status()
    found = response.json()
    elapsed = round((time.perf_counter() - started) * 1000)
    choice = (found.get("choices") or [{}])[0]
    usage = found.get("usage") or {}
    return {
        "text": str((choice.get("message") or {}).get("content") or ""),
        "finish_reason": str(choice.get("finish_reason") or ""),
        "tokens_in": int(usage.get("prompt_tokens") or 0),
        "tokens_out": int(usage.get("completion_tokens") or 0),
        "latency_ms": elapsed,
        "wall_ms": elapsed,
    }


def jobs(args: argparse.Namespace) -> int:
    path = Path(args.jobs)
    out = path.with_suffix(".results.jsonl")
    key = os.environ.get(args.key_env, "")
    if not key:
        raise SystemExit(f"set {args.key_env} to the API key")
    have = done(out, "id")
    todo = [job for job in read_rows(path) if job["id"] not in have]
    if args.only:
        todo = [job for job in todo if job["model"] == args.only]
    todo = [job for at, job in enumerate(todo) if at % args.of == args.part]
    send = stream_chat if args.stream else chat
    print(f"{len(todo)} jobs to run", flush=True)

    def work(job: dict[str, Any]) -> None:
        row: dict[str, Any] = {"id": job["id"], "model": job["model"]}
        for attempt in range(STREAM_ATTEMPTS if args.stream else ATTEMPTS):
            try:
                row.update(send(args.endpoint, key, job))
                row.pop("error", None)
                row["attempts"] = attempt + 1
                break
            except (httpx.HTTPError, ValueError) as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"[:300]
                if "exceed_context_size" in row["error"]:
                    break
                time.sleep(
                    STREAM_PAUSE_SECONDS if args.stream else PAUSE_SECONDS * (attempt + 1)
                )
        append(out, row)
        print(
            row["id"], row.get("tokens_in"), row.get("tokens_out"), row.get("wall_ms"),
            row.get("error", ""), flush=True,
        )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, todo))
    failed = len(todo) - len(done(out, "id") - have)
    print(f"finished, {failed} failed", flush=True)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="comparisons-run")
    sub = parser.add_subparsers(dest="mode", required=True)
    local = sub.add_parser("engine", help="summarise every item on a local engine")
    local.add_argument("--endpoint", default="http://localhost:8000")
    local.add_argument("--contestant", required=True, choices=["M1", "M2", "M3", "B0"])
    local.add_argument("--arena", default="ctx_compress")
    local.add_argument("--items", default="ctx_compress/exp1/data/items.jsonl")
    local.add_argument("--work", default="ctx_compress/exp1/results/work")
    local.add_argument("--weights", default="")
    local.add_argument("--card", default="")
    local.set_defaults(handler=engine)
    api = sub.add_parser("jobs", help="run a jobs file on a chat completions API")
    api.add_argument("--endpoint", default="https://openrouter.ai/api/v1")
    api.add_argument("--key-env", default="OPENROUTER_API_KEY")
    api.add_argument("--jobs", required=True)
    api.add_argument("--workers", type=int, default=4)
    api.add_argument("--stream", action="store_true")
    api.add_argument("--only", default="")
    api.add_argument("--part", type=int, default=0)
    api.add_argument("--of", type=int, default=1)
    api.set_defaults(handler=jobs)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
