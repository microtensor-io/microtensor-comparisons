from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REST = "https://rest.runpod.io/v1"
IMAGE = "vllm/vllm-openai@sha256:6ee133356d49ed24cee03dd0cda3d3980279a11c107ce3e752c89e76540f41c9"
HERE = Path(__file__).resolve().parent
CHUNK = 4000
START = (
    "mkdir -p /work && cd /work && "
    'for i in $(seq 0 $((RERUN_PARTS-1))); do v="RERUN_$i"; printf %s "${!v}"; done | base64 -d > /work/rerun.py && '
    "(python3 -m http.server 8070 --directory /work > /work/http.log 2>&1 &) && "
    "nvidia-smi > /work/nvidia-smi.txt 2>&1; "
    "python3 /work/rerun.py plan --arena-ref ${ARENA_REF} --out /work/plan.json > /work/rerun.log 2>&1 && "
    "python3 /work/rerun.py run --plan /work/plan.json --out /work/out --models /work/models >> /work/rerun.log 2>&1; "
    "touch /work/DONE; sleep infinity"
)


def call(method: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        REST + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "microtensor-rerun/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{path} answered {exc.code}: {exc.read()[:300]!r}") from exc
    return json.loads(raw) if raw else {}


def pod_env() -> dict[str, str]:
    packed = base64.b64encode((HERE / "rerun.py").read_bytes()).decode()
    parts = [packed[i : i + CHUNK] for i in range(0, len(packed), CHUNK)]
    env = {f"RERUN_{i}": part for i, part in enumerate(parts)}
    env.update(
        {
            "RERUN_PARTS": str(len(parts)),
            "ARENA_REF": os.environ.get("ARENA_REF", "main"),
            "VLLM_NO_USAGE_STATS": "1",
        }
    )
    return env


def update(pod: str) -> int:
    found = call(
        "POST", f"/pods/{pod}/update", {"env": pod_env(), "dockerStartCmd": [START]}
    )
    print(json.dumps({k: found.get(k) for k in ("id", "desiredStatus", "costPerHr")}))
    return 0


def up() -> int:
    env = pod_env()
    found = call(
        "POST",
        "/pods",
        {
            "name": "microtensor-rerun-e0",
            "imageName": os.environ.get("RERUN_IMAGE", IMAGE),
            "gpuTypeIds": os.environ.get(
                "RUNPOD_GPUS", "NVIDIA GeForce RTX 4090"
            ).split(","),
            "gpuCount": 1,
            "gpuTypePriority": "custom",
            "allowedCudaVersions": ["13.0"],
            "cloudType": os.environ.get("RUNPOD_CLOUD", "COMMUNITY"),
            "computeType": "GPU",
            "containerDiskInGb": 60,
            "volumeInGb": 0,
            "ports": ["8070/http"],
            "dockerEntrypoint": ["/bin/bash", "-c"],
            "dockerStartCmd": [START],
            "env": env,
        },
    )
    print(
        json.dumps(
            {k: found.get(k) for k in ("id", "desiredStatus", "costPerHr", "machineId")}
        )
    )
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("up", "update", "status", "down"):
        raise SystemExit(
            "usage: runpod.py up | update <pod id> | status <pod id> | down <pod id>"
        )
    if sys.argv[1] == "up":
        return up()
    if sys.argv[1] == "update":
        return update(sys.argv[2])
    if sys.argv[1] == "status":
        found = call("GET", f"/pods/{sys.argv[2]}")
        print(
            json.dumps(
                {
                    k: found.get(k)
                    for k in ("id", "desiredStatus", "costPerHr", "runtime", "gpu")
                }
            )[:800]
        )
        return 0
    call("DELETE", f"/pods/{sys.argv[2]}")
    print("deleted", sys.argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
