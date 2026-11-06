from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import microtensor_subnet
from huggingface_hub import hf_hub_download
from microtensor_subnet.validator import compress
from microtensor_subnet.validator.sandbox import judge as probe_judge
from microtensor_subnet.validator.sandbox.docker import pinned
from microtensor_subnet.validator.sandbox.slm import llama_command

log = logging.getLogger("comparisons.grade")

HOME = Path(os.environ.get("RUN_WORK", "ctx_compress/exp1/results/work"))
ITEMS = Path(os.environ.get("RUN_ITEMS", "ctx_compress/exp1/data/items.jsonl"))
CACHE = Path(os.environ.get("RUN_CACHE", ".cache"))
ARENA_URL = "https://api.microtensor.cloud/v2/arenas/ctx_compress"
PROBE_URL = os.environ.get("PROBE_URL", "http://localhost:8000")
THREADS = int(os.environ.get("PROBE_THREADS", "4"))
TOKENIZER_REVISION = "d5f01a3ea75f088947be3aae039f4ad52837dfde"
SCORED_FIRST = os.environ.get("SCORED_ONLY", "1") == "1"


def rows_of(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def grade_one(
    judge: compress.Judge, item: dict[str, Any], raw: str, skip_unscored: bool
) -> dict[str, Any]:
    label, task = item["label"], item["task"]
    text = raw.strip()
    valid = compress.sections(raw, judge.headings) is not None
    spent = judge.count_tokens(raw)
    budget = int(label["budget_tokens"])
    probes = label["probes"]
    skipped = skip_unscored and not (valid and spent <= budget)
    asked = bool(text) and not skipped
    answers = judge.answer(text, [str(p["question"]) for p in probes]) if asked else []
    answers = [*answers, *[""] * (len(probes) - len(answers))]
    scores = [compress.probe_score(p, a) for p, a in zip(probes, answers, strict=True)]
    replay = compress.Judge(
        count_tokens=judge.count_tokens,
        answer=lambda summary, questions: answers,
        pass_threshold=judge.pass_threshold,
        min_output_tokens=judge.min_output_tokens,
        max_output_share=judge.max_output_share,
        max_output_tokens=judge.max_output_tokens,
        headings=judge.headings,
    )
    verdict = compress.grade(raw, label, task, replay)
    return {
        "item_id": item["item_id"],
        "format_valid": valid,
        "summary_tokens": spent,
        "budget_tokens": budget,
        "within_budget": spent <= budget,
        "recall": compress.recall(text, label["facts"]),
        "facts_total": len(label["facts"]),
        "hallucination": compress.hallucination(text, str(task["user"])),
        "identifiers": len(compress.identifiers(text)),
        "continuation": None if skipped else (sum(scores) / len(probes) if probes else 1.0),
        "probe_skipped": skipped,
        "probe_answers": answers,
        "probe_scores": scores,
        "item_score": verdict.score,
        "passed": verdict.success,
        "reason": verdict.reason,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    wanted = sys.argv[1:]
    with urllib.request.urlopen(ARENA_URL, timeout=60) as response:
        definition = json.load(response)["definition"]
    grading = definition["grading"]
    spec = probe_judge.ProbeSpec.from_definition(definition)
    model_file = probe_judge.fetch_probe(spec, CACHE)
    llama = definition["evaluation"]["images"]["llama"]
    image = pinned(str(llama["image"]), str(llama["digest"]))
    tokenizer_dir = CACHE / "tokenizer"
    hf_hub_download(
        str(grading["tokenizer"]),
        "tokenizer.json",
        revision=TOKENIZER_REVISION,
        local_dir=str(tokenizer_dir),
    )
    command = [
        *llama_command(
            f"{probe_judge.LLAMA_GUEST}/{model_file.name}",
            threads=THREADS,
            max_model_len=spec.max_input_tokens,
        ),
        "--cache-reuse",
        str(probe_judge.LLAMA_CACHE_REUSE),
    ]
    (HOME / "probe_server.json").write_text(
        json.dumps({"image": image, "model_dir": str(model_file.parent), "command": command}),
        encoding="utf-8",
    )
    if wanted == ["prepare"]:
        print(json.dumps({"image": image, "model_dir": str(model_file.parent)}))
        print(" ".join(command))
        return 0
    items = {row["item_id"]: row for row in rows_of(ITEMS)}
    agent = probe_judge.ProbeAgent(
        None,
        image,
        model_file.parent,
        "",
        max_tokens=spec.max_tokens,
        max_model_len=spec.max_input_tokens,
        backend=probe_judge.LLAMA_BACKEND,
        model_file=model_file.name,
        threads=THREADS,
    )
    agent.url = PROBE_URL
    judge = compress.Judge(
        count_tokens=probe_judge.token_counter(tokenizer_dir),
        answer=agent.answer,
        pass_threshold=float(grading.get("pass_threshold") or 0.6),
        min_output_tokens=int(grading.get("min_output_tokens") or 1000),
        max_output_share=float(grading.get("max_output_share") or 0.05),
        max_output_tokens=int(grading.get("max_output_tokens") or 3072),
        headings=tuple(str(h) for h in grading.get("headings") or compress.HEADINGS),
    )
    (HOME / "grader_info.json").write_text(
        json.dumps(
            {
                "subnet_version": getattr(microtensor_subnet, "__version__", ""),
                "probe": {"model": spec.model, "revision": spec.revision, "file": spec.file},
                "probe_image": image,
                "probe_threads": THREADS,
                "probe_command": command,
                "tokenizer": f"{grading['tokenizer']}@{TOKENIZER_REVISION}",
                "grading": grading,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    if True:
        for contestant in wanted:
            out = HOME / "graded" / f"{contestant}.jsonl"
            out.parent.mkdir(parents=True, exist_ok=True)
            kept = [row for row in rows_of(out) if SCORED_FIRST or not row.get("probe_skipped")]
            with out.open("w", encoding="utf-8") as handle:
                for row in kept:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            have = {row["item_id"] for row in kept}
            for row in rows_of(HOME / "outputs" / f"{contestant}.jsonl"):
                if row["item_id"] in have or row.get("error"):
                    continue
                started = time.monotonic()
                found = grade_one(
                    judge, items[row["item_id"]], str(row.get("text") or ""), SCORED_FIRST
                )
                found["contestant"] = contestant
                with out.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(found, ensure_ascii=False) + "\n")
                log.info(
                    "%s %s score %.3f %s in %.0f s",
                    contestant,
                    row["item_id"],
                    found["item_score"],
                    found["reason"],
                    time.monotonic() - started,
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
