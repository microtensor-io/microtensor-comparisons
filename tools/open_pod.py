from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REST = "https://rest.runpod.io/v1"
GRAPHQL = "https://api.runpod.io/graphql"
IMAGE = (
    "ghcr.io/ggml-org/llama.cpp@"
    "sha256:821d0ae4e5d4e82a2ad8d08973b5f9cd5d0b84524b1d2439ed1f3e41ebc6b4c7"
)
PORT = 8000
DISK_GB = 60
MODELS = {
    "qwen-3-8-27b": "unsloth/Qwen3.8-27B-GGUF:UD-Q6_K_XL",
    "gemma-4-31b": "unsloth/gemma-4-31B-it-GGUF:UD-Q5_K_XL",
}
CARDS = ["NVIDIA A40", "NVIDIA RTX A6000"]


def call(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    with httpx.Client(timeout=60) as http:
        response = http.request(
            method,
            REST + path,
            json=body,
            headers={"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"},
        )
    if response.status_code >= 400:
        raise SystemExit(f"{path} answered {response.status_code}: {response.text[:300]}")
    return response.json() if response.content else {}


def price(card: str, cloud: str) -> float:
    query = '{ gpuTypes(input: {id: "' + card + '"}) { communityPrice securePrice } }'
    with httpx.Client(timeout=60) as http:
        response = http.post(
            GRAPHQL,
            json={"query": query},
            headers={"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"},
        )
    row = ((response.json().get("data") or {}).get("gpuTypes") or [{}])[0]
    return float(row.get("communityPrice" if cloud == "COMMUNITY" else "securePrice") or 0.0)


def arguments(model: str, token: str, context: int, slots: int) -> list[str]:
    return [
        "-hf",
        MODELS[model],
        "--no-mmproj",
        "--host",
        "0.0.0.0",
        "--port",
        str(PORT),
        "--alias",
        model,
        "--api-key",
        token,
        "-c",
        str(context),
        "-np",
        str(slots),
        "-ngl",
        "999",
        "-fa",
        "on",
        "--jinja",
        "--reasoning-budget",
        "0",
        "--cache-reuse",
        "256",
    ]


def up(args: argparse.Namespace) -> int:
    state = Path(args.state)
    held = json.loads(state.read_text()) if state.is_file() else {}
    if args.name in held:
        raise SystemExit(f"{args.name} is already recorded")
    token = secrets.token_urlsafe(32)
    for card in CARDS if args.card == "" else [args.card]:
        for cloud in ["COMMUNITY", "SECURE"] if args.cloud == "" else [args.cloud]:
            hourly = price(card, cloud)
            if not hourly or hourly > args.max_price:
                continue
            try:
                found = call(
                    "POST",
                    "/pods",
                    {
                        "name": args.name,
                        "imageName": IMAGE,
                        "gpuTypeIds": [card],
                        "gpuCount": 1,
                        "cloudType": cloud,
                        "computeType": "GPU",
                        "containerDiskInGb": DISK_GB,
                        "volumeInGb": 0,
                        "ports": [f"{PORT}/http"],
                        "dockerEntrypoint": [],
                        "dockerStartCmd": arguments(args.model, token, args.context, args.slots),
                        "env": {"LLAMA_CACHE": "/models"},
                    },
                )
            except SystemExit as exc:
                print(f"no {card} on {cloud}: {str(exc)[:160]}", flush=True)
                continue
            pod_id = str(found.get("id") or "")
            if not pod_id:
                continue
            held[args.name] = {
                "pod_id": pod_id,
                "token": token,
                "model": args.model,
                "card": card,
                "cloud": cloud,
                "usd_per_hour": hourly,
                "context": args.context,
                "slots": args.slots,
                "image": IMAGE,
                "endpoint": f"https://{pod_id}-{PORT}.proxy.runpod.net/v1",
                "started": time.time(),
            }
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps(held, indent=1))
            print(f"{args.name}: pod {pod_id} on {card} {cloud} at {hourly} USD an hour", flush=True)
            return 0
    raise SystemExit("no pod could be started")


def wait(args: argparse.Namespace) -> int:
    held = json.loads(Path(args.state).read_text())[args.name]
    deadline = time.monotonic() + args.seconds
    url = held["endpoint"].removesuffix("/v1") + "/health"
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=20) as http:
                response = http.get(url)
            if response.status_code == 200:
                print(f"{args.name} is ready", flush=True)
                return 0
            print(f"{args.name}: {response.status_code} {response.text[:80]}", flush=True)
        except httpx.HTTPError as exc:
            print(f"{args.name}: {type(exc).__name__}", flush=True)
        time.sleep(20)
    return 1


def down(args: argparse.Namespace) -> int:
    state = Path(args.state)
    held = json.loads(state.read_text()) if state.is_file() else {}
    names = [args.name] if args.name else list(held)
    for name in names:
        row = held.get(name)
        if row is None:
            continue
        if not row.get("stopped"):
            call("DELETE", f"/pods/{row['pod_id']}")
            row["stopped"] = time.time()
            print(f"{name}: pod {row['pod_id']} deleted", flush=True)
    state.write_text(json.dumps(held, indent=1))
    return 0


def listing(args: argparse.Namespace) -> int:
    for row in call("GET", "/pods"):
        print(row.get("id"), row.get("name"), row.get("desiredStatus"), row.get("costPerHr"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="open-pod")
    parser.add_argument("step", choices=["up", "wait", "down", "list"])
    parser.add_argument("--name", default="")
    parser.add_argument("--model", default="qwen-3-8-27b", choices=sorted(MODELS))
    parser.add_argument("--context", type=int, default=131072)
    parser.add_argument("--slots", type=int, default=1)
    parser.add_argument("--card", default="")
    parser.add_argument("--cloud", default="")
    parser.add_argument("--max-price", type=float, default=0.6)
    parser.add_argument("--seconds", type=float, default=1800)
    parser.add_argument("--state", default="ctx_compress/exp1/results/work/open_pods.json")
    args = parser.parse_args(argv)
    return int({"up": up, "wait": wait, "down": down, "list": listing}[args.step](args))


if __name__ == "__main__":
    sys.exit(main())
