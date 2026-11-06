from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from comparisons import prompts
from comparisons.prompts import read_rows

ITEM_FIELDS = (
    "contestant",
    "item_id",
    "set",
    "session_tokens",
    "budget_tokens",
    "input_tokens",
    "output_tokens",
    "summary_tokens",
    "ttft_ms",
    "total_ms",
    "cost_usd",
    "format_valid",
    "within_budget",
    "recall",
    "hallucination",
    "continuation",
    "item_score",
    "passed",
    "facts_asked",
    "facts_correct",
    "facts_confident_wrong",
    "lures_asked",
    "lures_taken",
    "commitments_judged",
    "commitments_passed",
    "commitments_confident_failures",
)
KINDS = {
    "M1": "microtensor",
    "M2": "microtensor",
    "M3": "microtensor",
    "B0": "base",
    "F1": "frontier",
    "F2": "frontier",
    "P1": "baseline",
    "C1": "reference",
    "C0": "reference",
}
MINERS = {
    "M1": {"uid": 2, "hotkey": "5HEtPjhaCs859sdCjMG1a3TEZWFftKRs4VAYzCjnNUf82iDL"},
    "M2": {"uid": 13, "hotkey": "5DfMHBFPnimZrQtfXa4owd6RRrgakSY68RA8Y2teja7qkNaj"},
    "M3": {"uid": 14, "hotkey": "5DewpgADz26vA9aWLQBEtyhGUhC7YGFMxzmTUENMGCd71RDd"},
}


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def build(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.out)
    analysis = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    report = json.loads(
        (Path(args.items).parent / "report.json").read_text(encoding="utf-8")
    )
    raw = read_rows(out / "raw.jsonl")
    work = out / "work"
    weights = {}
    for name in prompts.SUMMARISERS:
        rows = read_rows(work / "outputs" / f"{name}.jsonl")
        if rows and rows[0].get("weights_sha256"):
            weights[name] = rows[0]["weights_sha256"]
    listed = {line["contestant"]: line for line in analysis["summary"]}
    contestants = []
    for name in prompts.CONTESTANTS:
        held = {**prompts.SUMMARISERS, **prompts.REFERENCES}[name]
        line = listed.get(name) or {}
        entry: dict[str, Any] = {
            "id": name,
            "kind": KINDS[name],
            "label": held["label"],
            "runs_on": held.get("runs_on", "reader only"),
            "status": analysis["status"].get(name) or "not run yet",
            "metrics": {
                key: value
                for key, value in line.items()
                if key not in ("contestant", "label", "status") and value is not None
            },
        }
        if name in MINERS:
            entry.update(MINERS[name])
        if name in weights:
            entry["weights"] = weights[name]
        if held.get("model"):
            entry["model"] = (
                prompts.OPEN_MODELS.get(held["model"])
                or prompts.LIST_PRICES[held["model"]]["provider_model"]
            )
        contestants.append(entry)
    grader = (
        json.loads((work / "grader_info.json").read_text(encoding="utf-8"))
        if (work / "grader_info.json").is_file()
        else {}
    )
    complete = all(c["status"] == "complete" for c in contestants)
    return {
        "experiment": "exp1",
        "title": "Compaction models against larger open models",
        "run_date": args.date,
        "public": bool(args.public),
        "status": "complete" if complete else "partial",
        "dataset": {
            "name": "Woolford compaction study replication package",
            "url": "https://github.com/felixwoolford/compaction-study-replication",
            "commit": "8c7c35f5d3222909c1ac8ef4bc44f90ba6a61512",
            "licence": "MIT",
            "sets": {
                "A": "18 synthetic debugging sessions with 17 planted facts and 3 lures each",
                "B": "18 real public Pi sessions with 27 scored commitment probes",
            },
            "items": report["items"],
            "dropped": report["dropped_over_cap_or_thin"],
            "input_tokens": report["input_tokens"],
            "planted_facts": report["facts"],
            "commitments": report["commitments"],
            "items_sha256": hashlib.sha256(Path(args.items).read_bytes()).hexdigest(),
        },
        "settings": {
            "prompt": "the arena's compaction instruction and the canonically rendered session",
            "temperature": 0,
            "max_output_tokens": prompts.MAX_SUMMARY_TOKENS,
            "pass_threshold": 0.6,
            "engine": analysis["pod"].get("image"),
            "card": analysis["pod"].get("gpu"),
            "card_usd_per_hour": analysis["pod"].get("usd_per_hour"),
            "probe": grader.get("probe"),
            "probe_image": grader.get("probe_image"),
            "tokenizer": grader.get("tokenizer"),
            "reader": prompts.READER,
            "judge": prompts.JUDGE,
            "open_models": {
                "models": prompts.OPEN_MODELS,
                **(analysis.get("open_pod") or {}),
            },
        },
        "contestants": contestants,
        "tests": analysis["tests"],
        "judge_agreement": analysis["judge_agreement"],
        **(
            {
                "items": [
                    {key: row[key] for key in ITEM_FIELDS if row.get(key) is not None}
                    for row in raw
                ]
            }
            if args.rows
            else {}
        ),
        "notes": [
            "Continuation is measured on summaries that have all nine headings and fit the "
            "budget; the others score zero whatever it would be.",
            "33 of the 306 planted facts sit only in the agent's thinking blocks, which the "
            "canonical rendering does not carry, so 273 is the most a contestant can recall.",
            "Cost for the miner models is 4090 time at the pod's hourly price plus the list price "
            "of 0.01 USD per million input tokens with output free; the base model is 4090 time only.",
            "Qwen 3.8 27B and Gemma 4 31B are the open weight models the study itself ran, in the "
            "same quantised files. They ran on rented 48 GB cards with llama.cpp, thinking off, one "
            "request at a time, and their cost is card time at the pod's hourly price. Closed API "
            "models are not in this run.",
            "Qwen 3.8 27B is the reader and Gemma 4 31B the judge, with one vote per reply because "
            "the judge is deterministic. Qwen rescored a quarter of the replies and the two agreed "
            "with a kappa of 0.51, so the commitment column is noisy.",
            "The Pi prompt contestant writes Pi's own summary format, so it cannot pass the arena's "
            "format gate. Read its planted fact and commitment columns.",
            "For 21 of the 72 Qwen summaries the stream dropped and resumed from the server's "
            "cache, so their time is the measured generation time plus prompt time fitted on the "
            "other rows.",
        ],
        "source": {
            "repo": "microtensor-io/microtensor-comparisons",
            **(
                {"url": "https://github.com/microtensor-io/microtensor-comparisons"}
                if args.link
                else {}
            ),
            "path": "ctx_compress/exp1",
            "commit": _commit(),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="comparisons-document")
    parser.add_argument("--items", default="ctx_compress/exp1/data/items.jsonl")
    parser.add_argument("--out", default="ctx_compress/exp1/results")
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--rows", action="store_true")
    parser.add_argument("--link", action="store_true")
    parser.add_argument("--date", default="2026-11-06")
    args = parser.parse_args(argv)
    body = build(args)
    target = Path(args.out) / "comparison.json"
    target.write_text(json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
    print(target, len(json.dumps(body)), "bytes", body["status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
