from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import http.client
import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

API = os.environ.get("MT_API", "https://api.microtensor.cloud")
CHAIN = os.environ.get("MT_CHAIN_RPC", "https://test.finney.opentensor.ai")
ARENA_FILE = "https://raw.githubusercontent.com/microtensor-io/microtensor-arenas/{ref}/{arena}/arena.yaml"
SAMPLE_BLOCKS = 10
SLM_POOL = "slm"
BARE = "B0"
ID_PREFIX = "token_id:"
SEED_MASK = 2**63 - 1
PORT = 8000
MODEL_NAME = "slm"
WEIGHT_SUFFIXES = (".safetensors", ".gguf")
MEMORY_SHARE = 0.9
READY_SECONDS = 1800
CALL_SECONDS = 900
AGENT = "microtensor-rerun/1"


def fetch(url: str, *, data: bytes | None = None, timeout: float = 300.0) -> bytes:
    headers = {"User-Agent": AGENT, "Accept": "*/*"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    last: Exception | None = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except OSError as exc:
            last = exc
            time.sleep(2 + attempt * 3)
    raise SystemExit(f"{url} could not be read: {last}")


def fetch_json(url: str) -> Any:
    return json.loads(fetch(url))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def answer_sha256(ids: list[int], text: str) -> str:
    if not ids:
        return sha256(canonical(list(ids)))
    return sha256(canonical([list(ids), text]))


def unpacked(raw: bytes) -> bytes:
    return gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def block_hash(number: int) -> str:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "chain_getBlockHash", "params": [number]}
    )
    found = json.loads(fetch(CHAIN, data=body.encode()))
    value = found.get("result")
    if not isinstance(value, str) or not value.startswith("0x"):
        raise SystemExit(f"the chain gave no hash for block {number}: {found}")
    return value


def render(template: str, task: dict[str, Any]) -> str:
    rendered = template
    for key, value in task.items():
        rendered = rendered.replace("{" + str(key) + "}", str(value))
    return rendered


def eligible(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    for position, row in enumerate(
        r for r in transcript.get("items") or [] if isinstance(r, dict)
    ):
        for call in row.get("calls") or []:
            if not isinstance(call, dict) or str(call.get("kind", "")) != "slm":
                continue
            if call.get("fault") or not call.get("output_tokens"):
                continue
            found.append(
                {
                    "row": position,
                    "item_id": str(row.get("item_id", "")),
                    "condition": str(row.get("condition", "")),
                    "pool": str(row.get("pool", "")),
                    "seq": int(call.get("seq") or 0),
                    "call": call,
                }
            )
    return found


def draw(
    transcript: dict[str, Any], transcript_sha256: str, hash_of_block: str, count: int
) -> list[dict[str, Any]]:
    pool = eligible(transcript)
    digest = hashlib.sha256(f"{transcript_sha256}:{hash_of_block}".encode()).digest()
    picked = random.Random(int.from_bytes(digest[:8], "big")).sample(
        pool, min(count, len(pool))
    )
    return sorted(picked, key=lambda d: (d["row"], d["seq"]))


def arena_settings(arena: str, ref: str) -> dict[str, Any]:
    import yaml

    raw = fetch(ARENA_FILE.format(ref=ref, arena=arena))
    found = yaml.safe_load(raw)
    evaluation = found.get("evaluation") or {}
    slm = found.get("slm") or {}
    overrides = (found.get("envelope") or {}).get("overrides") or {}
    engine = (evaluation.get("images") or {}).get("engine") or {}
    profiles = list(evaluation.get("profiles") or [])
    return {
        "arena_file_sha256": sha256(raw),
        "arena_ref": ref,
        "prompt": str(slm["prompt"]),
        "min_calls": int((evaluation.get("spot_check") or {}).get("min_calls") or 40),
        "max_model_len": int(overrides["max_input_tokens"])
        + int(overrides["max_output_tokens"]),
        "engine_image": str(engine.get("image", "")),
        "engine_digest": str(engine.get("digest", "")),
        "profile": profiles[0] if profiles else "P1",
    }


def plan(args: argparse.Namespace) -> int:
    base = f"{API}/v2/arenas/{args.arena}/epochs/{args.epoch}"
    settings = arena_settings(args.arena, args.arena_ref)
    epoch = fetch_json(base)
    batch = epoch.get("batch") or {}
    if batch.get("state") != "settled":
        raise SystemExit(f"epoch {args.epoch} is {batch.get('state')}, not settled")
    inputs = fetch_json(f"{base}/documents/inputs")["body"]
    bundle = fetch(f"{base}/inputs/bundle", timeout=900)
    if sha256(bundle) != inputs["bundle_sha256"]:
        raise SystemExit("the inputs bundle does not match its published hash")
    items: dict[str, dict[str, Any]] = {}
    import io
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:*") as archive:
        member = archive.extractfile("inputs.jsonl")
        if member is None:
            raise SystemExit("the bundle holds no inputs.jsonl")
        for line in member.read().decode("utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                items[str(row["item_id"])] = row
    listing = fetch_json(f"{base}/transcripts").get("transcripts") or []
    spot_reports = fetch_json(f"{base}/documents/spotcheck")["body"]["reports"]
    mirror = fetch_json(f"{base}/mirror")["body"]["miners"]
    checked: dict[str, dict[str, Any]] = {}
    for report in spot_reports:
        for hotkey, row in (report.get("miners") or {}).items():
            if isinstance(row, dict) and isinstance(row.get("spot_check"), dict):
                checked[hotkey] = {
                    "transcript_sha256": row.get("transcript_sha256"),
                    **row["spot_check"],
                }
    miners = []
    for upload in listing:
        hotkey = str(upload["hotkey"])
        sha = str(upload["transcript_sha256"])
        spot = checked.get(hotkey)
        if spot is None or spot.get("transcript_sha256") != sha:
            print(f"{hotkey}: no spot check for this transcript, skipped", flush=True)
            continue
        raw = fetch(f"{API}/v2/mirror/{sha}", timeout=900)
        if sha256(raw) != sha:
            raise SystemExit(
                f"{hotkey}: the transcript does not match its published hash"
            )
        transcript = json.loads(unpacked(raw))
        weights = mirror.get(hotkey) or {}
        if str(transcript.get("weights_sha256", "")).removeprefix(
            "sha256:"
        ) != weights.get("weights_sha256"):
            raise SystemExit(
                f"{hotkey}: the transcript and the mirror name different weights"
            )
        seed_block = int(upload["received_block"]) + SAMPLE_BLOCKS
        hash_of_block = block_hash(seed_block)
        drawn = draw(transcript, sha, hash_of_block, settings["min_calls"])
        keys = {(d["item_id"], d["seq"]) for d in drawn}
        timed = [(str(t[0]), int(t[1])) for t in spot.get("timing") or []]
        same_draw = bool(timed) and all(t in keys for t in timed)
        calls = []
        for chosen in drawn:
            if not (chosen["pool"] == SLM_POOL or chosen["condition"] == BARE):
                continue
            item = items.get(chosen["item_id"])
            if item is None:
                continue
            prompt = render(settings["prompt"], item["task"])
            call = chosen["call"]
            calls.append(
                {
                    "item_id": chosen["item_id"],
                    "condition": chosen["condition"],
                    "pool": chosen["pool"],
                    "seq": chosen["seq"],
                    "prompt": prompt,
                    "prompt_ok": sha256(prompt.encode("utf-8"))
                    == call.get("prompt_sha256"),
                    "max_tokens": int(call.get("max_tokens") or 0),
                    "stop": [str(s) for s in call.get("stop") or []],
                    "seed": int(call.get("seed") or 0),
                    "recorded_ids": [int(t) for t in call.get("output_tokens") or []],
                    "recorded_text": str(call.get("output_text") or ""),
                }
            )
        miners.append(
            {
                "hotkey": hotkey,
                "transcript_sha256": sha,
                "received_block": int(upload["received_block"]),
                "seed_block": seed_block,
                "seed_block_hash": hash_of_block,
                "drawn": len(drawn),
                "same_draw_as_coordinator": same_draw,
                "coordinator_calls": int(spot.get("calls") or 0),
                "coordinator_matched": int(spot.get("matched") or 0),
                "repo": weights.get("slm", {}).get("repo", ""),
                "revision": weights.get("slm", {}).get("revision", ""),
                "files": weights.get("slm", {}).get("files", {}),
                "weights_sha256": weights.get("weights_sha256", ""),
                "calls": calls,
            }
        )
        rebuilt = sum(1 for c in calls if c["prompt_ok"])
        print(
            f"{hotkey[:10]} drew {len(drawn)}, same draw as the coordinator: {same_draw}, "
            f"rebuilt from public inputs: {rebuilt} of {len(calls)}",
            flush=True,
        )
    found = {
        "arena": args.arena,
        "epoch": args.epoch,
        "api": API,
        "chain": CHAIN,
        "bundle_sha256": inputs["bundle_sha256"],
        "settings": settings,
        "miners": miners,
    }
    Path(args.out).write_text(json.dumps(found), encoding="utf-8")
    total = sum(1 for m in miners for c in m["calls"] if c["prompt_ok"])
    print(
        f"plan written: {total} calls to rerun across {len(miners)} miners", flush=True
    )
    return 0


def weight_hash(files: dict[str, str]) -> str:
    lines = [
        f"{name} {digest.removeprefix('sha256:')}"
        for name, digest in sorted(files.items())
        if name.endswith(WEIGHT_SUFFIXES)
    ]
    return sha256("\n".join(lines).encode("utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(miner: dict[str, Any], into: Path) -> None:
    from huggingface_hub import hf_hub_download

    into.mkdir(parents=True, exist_ok=True)
    for name, digest in sorted(miner["files"].items()):
        target = into / name
        if not target.is_file():
            hf_hub_download(
                miner["repo"], name, revision=miner["revision"], local_dir=str(into)
            )
        if file_sha256(target) != digest.removeprefix("sha256:"):
            raise SystemExit(
                f"{miner['repo']} {name} does not match the committed hash"
            )
    if weight_hash(miner["files"]) != miner["weights_sha256"]:
        raise SystemExit(
            f"{miner['repo']}: the weight files do not add up to the scored hash"
        )


def engine_argv(model_dir: Path, max_model_len: int) -> list[str]:
    return [
        "vllm",
        "serve",
        "--model",
        str(model_dir),
        "--served-model-name",
        MODEL_NAME,
        "--port",
        str(PORT),
        "--host",
        "127.0.0.1",
        "--max-model-len",
        str(max_model_len),
        "--seed",
        "0",
        "--gpu-memory-utilization",
        str(MEMORY_SHARE),
        "--max-num-seqs",
        "1",
        "--dtype",
        "bfloat16",
        "--max-logprobs",
        "1",
        "--no-enable-prefix-caching",
    ]


def ready() -> bool:
    try:
        connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
        connection.request("GET", "/health")
        ok = connection.getresponse().status == 200
        connection.close()
        return ok
    except OSError:
        return False


def ids_from(choice: dict[str, Any]) -> list[int]:
    listed = choice.get("token_ids")
    if isinstance(listed, list):
        return [int(t) for t in listed]
    logprobs = choice.get("logprobs") or {}
    found = []
    for token in (logprobs.get("tokens") if isinstance(logprobs, dict) else None) or []:
        text = str(token)
        if text.startswith(ID_PREFIX) and text[len(ID_PREFIX) :].isdigit():
            found.append(int(text[len(ID_PREFIX) :]))
    return found


def generate(call: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": MODEL_NAME,
        "prompt": call["prompt"],
        "max_tokens": call["max_tokens"],
        "temperature": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
        "logprobs": 1,
        "return_token_ids": True,
        "return_tokens_as_token_ids": True,
    }
    if call["stop"]:
        request["stop"] = call["stop"]
    request["seed"] = int(call["seed"]) & SEED_MASK
    started = time.perf_counter()
    text: list[str] = []
    ids: list[int] = []
    connection = http.client.HTTPConnection("127.0.0.1", PORT, timeout=CALL_SECONDS)
    try:
        connection.request(
            "POST",
            "/v1/completions",
            body=json.dumps(request).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        if response.status != 200:
            return {
                "error": f"the engine answered {response.status}: {response.read(300)!r}",
                "ids": [],
                "text": "",
                "seconds": 0.0,
            }
        while True:
            raw = response.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except ValueError:
                continue
            for choice in chunk.get("choices") or []:
                text.append(str(choice.get("text") or ""))
                ids += ids_from(choice)
    finally:
        connection.close()
    return {
        "error": "",
        "ids": ids,
        "text": "".join(text),
        "seconds": round(time.perf_counter() - started, 2),
    }


def gpu() -> dict[str, str]:
    try:
        line = (
            subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .splitlines()[0]
        )
        name, memory, driver = (part.strip() for part in line.split(","))
    except (OSError, subprocess.CalledProcessError, ValueError, IndexError):
        name, memory, driver = "unknown", "", ""
    try:
        import torch
        import vllm

        versions = {
            "vllm": vllm.__version__,
            "torch": torch.__version__,
            "cuda": str(torch.version.cuda),
        }
    except ImportError:
        versions = {}
    return {"gpu": name, "gpu_memory": memory, "driver": driver, **versions}


def start_engine(
    model_dir: Path, length: int, log: Any, repo: str
) -> subprocess.Popen[bytes]:
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "VLLM_NO_USAGE_STATS": "1"}
    engine = subprocess.Popen(
        engine_argv(model_dir, length), env=env, stdout=log, stderr=subprocess.STDOUT
    )
    deadline = time.time() + READY_SECONDS
    while not ready():
        if engine.poll() is not None or time.time() > deadline:
            stop_engine(engine)
            raise SystemExit(f"the engine did not start for {repo}; read {log.name}")
        time.sleep(5)
    return engine


def stop_engine(engine: subprocess.Popen[bytes]) -> None:
    engine.terminate()
    try:
        engine.wait(timeout=60)
    except subprocess.TimeoutExpired:
        engine.kill()
        engine.wait(timeout=60)
    deadline = time.time() + 120
    while ready() and time.time() < deadline:
        time.sleep(2)


def compare(call: dict[str, Any], ours: dict[str, Any]) -> dict[str, Any]:
    match = (
        not ours["error"]
        and ours["ids"] == call["recorded_ids"]
        and ours["text"] == call["recorded_text"]
    )
    first_diff = next(
        (
            i
            for i, (a, b) in enumerate(zip(ours["ids"], call["recorded_ids"]))
            if a != b
        ),
        min(len(ours["ids"]), len(call["recorded_ids"])),
    )
    return {
        "our_output_sha256": answer_sha256(ours["ids"], ours["text"])
        if not ours["error"]
        else "",
        "coordinator_output_sha256": answer_sha256(
            call["recorded_ids"], call["recorded_text"]
        ),
        "match": "match" if match else "no match",
        "output_tokens": len(ours["ids"]),
        "first_differing_token": "" if match else first_diff,
        "seconds": ours["seconds"],
        "error": ours["error"],
    }


def run(args: argparse.Namespace) -> int:
    found = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    models = Path(args.models)
    started = time.time()
    rows = []
    for miner in found["miners"]:
        calls = [c for c in miner["calls"] if c["prompt_ok"]]
        if args.only:
            wanted = set(args.only.split(","))
            calls = [c for c in calls if f"{c['item_id']}#{c['seq']}" in wanted]
        if not calls:
            continue
        model_dir = models / miner["weights_sha256"][:16]
        fetched = time.time()
        download(miner, model_dir)
        print(
            f"{miner['repo']} downloaded and checked in {time.time() - fetched:.0f} s",
            flush=True,
        )
        length = found["settings"]["max_model_len"]
        log = (out / f"engine-{miner['weights_sha256'][:16]}.log").open("ab")
        engine = start_engine(model_dir, length, log, miner["repo"])
        try:
            missed = []
            for call in calls:
                ours = generate(call)
                row = {
                    "miner_hotkey": miner["hotkey"],
                    "item_id": call["item_id"],
                    "condition": call["condition"],
                    "call_seq": call["seq"],
                    "model_hash": miner["weights_sha256"],
                    **compare(call, ours),
                    "retry_output_sha256": "",
                    "match_on_retry": "",
                    "retry_same_as_first": "",
                }
                rows.append(row)
                if row["match"] != "match":
                    missed.append((call, ours, row))
                print(
                    f"{call['item_id']} #{call['seq']} {row['match']} {row['output_tokens']} tokens {row['seconds']} s",
                    flush=True,
                )
            if missed and not args.no_retry:
                stop_engine(engine)
                engine = start_engine(model_dir, length, log, miner["repo"])
                for call, first, row in missed:
                    again = generate(call)
                    checked = compare(call, again)
                    row["retry_output_sha256"] = checked["our_output_sha256"]
                    row["match_on_retry"] = checked["match"]
                    row["retry_same_as_first"] = (
                        "yes"
                        if again["ids"] == first["ids"]
                        and again["text"] == first["text"]
                        else "no"
                    )
                    print(
                        f"{call['item_id']} #{call['seq']} after an engine restart: {checked['match']}, "
                        f"same as our first run: {row['retry_same_as_first']}",
                        flush=True,
                    )
        finally:
            stop_engine(engine)
            log.close()
        if not args.keep_models:
            shutil.rmtree(model_dir, ignore_errors=True)
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]) if rows else ["item_id"]
        )
        writer.writeheader()
        writer.writerows(rows)
    matched = sum(1 for r in rows if r["match"] == "match")
    settled = matched + sum(1 for r in rows if r["match_on_retry"] == "match")
    summary = {
        "arena": found["arena"],
        "epoch": found["epoch"],
        "calls": len(rows),
        "matched": matched,
        "matched_after_retry": settled,
        "result": f"{matched} of {len(rows)} matched on the first run, {settled} of {len(rows)} after one rerun of each mismatch",
        "minutes": round((time.time() - started) / 60, 1),
        "started_at": dt.datetime.fromtimestamp(started, dt.UTC).isoformat(),
        "ended_at": dt.datetime.now(dt.UTC).isoformat(),
        "script_sha256": file_sha256(Path(__file__)),
        "bundle_sha256": found["bundle_sha256"],
        "settings": found["settings"],
        "miners": [
            {
                k: m[k]
                for k in (
                    "hotkey",
                    "repo",
                    "revision",
                    "weights_sha256",
                    "transcript_sha256",
                    "seed_block",
                    "seed_block_hash",
                    "drawn",
                    "same_draw_as_coordinator",
                    "coordinator_calls",
                    "coordinator_matched",
                )
            }
            | {"rerun": sum(1 for c in m["calls"] if c["prompt_ok"])}
            for m in found["miners"]
        ],
        **gpu(),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        summary["result"],
        f"in {summary['minutes']} min on {summary['gpu']}",
        flush=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="rerun")
    sub = parser.add_subparsers(dest="command", required=True)
    first = sub.add_parser("plan")
    first.add_argument("--arena", default="ctx_compress")
    first.add_argument("--epoch", type=int, default=0)
    first.add_argument("--arena-ref", default="main")
    first.add_argument("--out", default="plan.json")
    second = sub.add_parser("run")
    second.add_argument("--plan", default="plan.json")
    second.add_argument("--out", default="out")
    second.add_argument("--models", default="models")
    second.add_argument("--keep-models", action="store_true")
    second.add_argument("--no-retry", action="store_true")
    second.add_argument("--only", default="")
    args = parser.parse_args()
    return plan(args) if args.command == "plan" else run(args)


if __name__ == "__main__":
    sys.exit(main())
