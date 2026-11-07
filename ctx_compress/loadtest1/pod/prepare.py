from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

from microtensor_subnet.artifact.validate import weights_sha256
from microtensor_subnet.serving.host.fetch import fetch
from microtensor_subnet.serving.shim import weights_of

SERVER = os.environ.get("MT_SERVER_URL", "https://api.microtensor.cloud")
MODEL = os.environ.get("MT_MODEL", "mt/ctx_compress")
ROOT = Path(os.environ.get("MT_SYSTEM_DIR", "/opt/system"))
CACHE = Path(os.environ.get("MT_CACHE_DIR", "/data/cache"))
MAX_SEQS = int(os.environ.get("MT_MAX_SEQS", "16"))


def main() -> int:
    with urllib.request.urlopen(SERVER + "/v1/public/inference/catalogue", timeout=60) as response:
        catalogue = json.load(response)
    entry = next((m for m in catalogue["models"] if m.get("model") == MODEL), None)
    if entry is None:
        print(f"{MODEL} is not in the catalogue", file=sys.stderr)
        return 2
    CACHE.mkdir(parents=True, exist_ok=True)
    fetched = fetch(entry, CACHE)
    ROOT.mkdir(parents=True, exist_ok=True)
    for source, name in ((fetched.artifact_dir, "artifact"), (fetched.slm_dir, "slm")):
        target = ROOT / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    files = weights_of(ROOT / "slm")
    engine = dict((entry.get("images") or {}).get("engine") or {})
    build = {
        "arena": entry.get("arena", ""),
        "epoch": entry.get("epoch"),
        "hotkey": entry.get("hotkey", ""),
        "model": entry["model"],
        "artifact_digest": entry["artifact_digest"],
        "weights_sha256": weights_sha256(files),
        "slm_files": files,
        "engine": {
            "image": engine.get("image", ""),
            "digest": engine.get("digest", ""),
            "flags": [],
            "env": {},
        },
        "max_model_len": int(entry.get("context") or 0) + int(entry.get("max_output") or 0),
        "max_seqs": MAX_SEQS,
        "dtype": "",
        "config": fetched.config,
        "slm_prompt": entry.get("slm_prompt", ""),
        "grader": entry.get("grader", ""),
        "envelope": entry.get("envelope") or {},
        "image_digest": "",
    }
    (ROOT / "build.json").write_text(json.dumps(build, indent=1, sort_keys=True), encoding="utf-8")
    print(
        f"prepared {build['model']} artifact {build['artifact_digest'][:12]} "
        f"weights {build['weights_sha256'][:12]} max_model_len {build['max_model_len']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
