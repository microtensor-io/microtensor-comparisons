from __future__ import annotations

import json
import os
import random
import sys
import urllib.request
from pathlib import Path

from microtensor_subnet.chain.config import ChainConfig
from microtensor_subnet.chain.wallet import load_wallet
from microtensor_subnet.serving.probes import loop as probes
from microtensor_subnet.validator import compress
from microtensor_subnet.validator.sandbox import judge as probe_judge

CACHE = Path("/lt/cache")
SERVER = os.environ.get("MT_SERVER_URL", "https://api.microtensor.cloud")
GATEWAY = os.environ.get("MT_GATEWAY_URL", "https://api.microtensor.cloud")
JUDGE_URL = os.environ.get("PROBE_URL", "http://127.0.0.1:8100")


def judge() -> compress.Judge:
    with urllib.request.urlopen(SERVER + "/v2/arenas/ctx_compress", timeout=60) as response:
        definition = json.load(response)["definition"]
    grading = definition["grading"]
    spec = probe_judge.ProbeSpec.from_definition(definition)
    model_file = probe_judge.fetch_probe(spec, CACHE)
    agent = probe_judge.ProbeAgent(
        None,
        "",
        model_file.parent,
        "",
        max_tokens=spec.max_tokens,
        max_model_len=spec.max_input_tokens,
        backend=probe_judge.LLAMA_BACKEND,
        model_file=model_file.name,
        threads=4,
    )
    agent.url = JUDGE_URL
    return compress.Judge(
        count_tokens=probe_judge.token_counter(CACHE / "tokenizer"),
        answer=agent.answer,
        pass_threshold=float(grading.get("pass_threshold") or 0.6),
        min_output_tokens=int(grading.get("min_output_tokens") or 1000),
        max_output_share=float(grading.get("max_output_share") or 0.05),
        max_output_tokens=int(grading.get("max_output_tokens") or 3072),
        headings=tuple(str(h) for h in grading.get("headings") or compress.HEADINGS),
    )


def main() -> int:
    wallet = load_wallet(ChainConfig.from_env())
    found = probes.cycle_gpus(
        server=SERVER,
        gateway=GATEWAY,
        credential=os.environ["MT_SERVE_CREDENTIAL"],
        wallet=wallet,
        sets=None,
        floor=0.9,
        chance=0.0,
        rng=random.Random(),
        grader_judge=judge(),
    )
    for row in found:
        print(
            json.dumps(
                {
                    "operator": row.operator[:12],
                    "gpu": row.gpu,
                    "kind": row.kind,
                    "success": row.success,
                    "verdict": row.verdict,
                    "quality": row.quality,
                    "inside": row.within_envelope,
                    "reason": str(row.reason)[:160],
                }
            ),
            flush=True,
        )
    print("probes", len(found), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
