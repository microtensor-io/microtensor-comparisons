from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from comparisons import analyse, prompts

REPAIRED = {"R1": {"label": "UID 2 model with the repair step", "runs_on": "4090"}}
CONTESTANTS = ["M1", "R1"]


def rows_of(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def repair_stats(work: Path) -> dict[str, Any]:
    rows = rows_of(work / "outputs" / "R1.jsonl")
    reports = [row.get("repair") or {} for row in rows]
    fixed = [report for report in reports if report.get("repaired")]
    return {
        "items": len(rows),
        "repaired": len(fixed),
        "valid_after": sum(1 for report in fixed if report.get("valid_after")),
        "headings_added": sum(
            len(report.get("headings_added") or []) for report in fixed
        ),
        "repeated_lines_dropped": sum(
            int(report.get("lines_dropped") or 0) for report in fixed
        ),
        "repeated_words_dropped": sum(
            int(report.get("words_dropped") or 0) for report in fixed
        ),
        "lines_trimmed_for_budget": sum(
            int(report.get("lines_trimmed") or 0) for report in fixed
        ),
        "median_repair_ms": statistics.median(
            [float(r.get("repair_ms") or 0.0) for r in reports]
        )
        if reports
        else None,
        "max_repair_ms": max(
            (float(r.get("repair_ms") or 0.0) for r in reports), default=None
        ),
    }


def same_as_exp1(work: Path, exp1: Path) -> dict[str, Any]:
    old = {
        row["item_id"]: row["text"] for row in rows_of(exp1 / "outputs" / "M1.jsonl")
    }
    new = {
        row["item_id"]: row.get("text")
        for row in rows_of(work / "outputs" / "M1.jsonl")
    }
    shared = [item for item in new if item in old]
    return {
        "compared": len(shared),
        "identical": sum(1 for item in shared if new[item] == old[item]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="comparisons-exp2")
    parser.add_argument("--items", default="ctx_compress/exp1/data/items.jsonl")
    parser.add_argument("--work", default="ctx_compress/exp2/results/work")
    parser.add_argument("--exp1-work", default="ctx_compress/exp1/results/work")
    parser.add_argument("--out", default="ctx_compress/exp2/results")
    parser.add_argument("--package", required=True)
    args = parser.parse_args(argv)
    prompts.SUMMARISERS.update(REPAIRED)
    prompts.CONTESTANTS[:] = CONTESTANTS
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    found = analyse.assemble(args)
    table = analyse.summarise(found)
    analyse.write_rows(out / "raw.jsonl", found["raw"])
    analyse.write_csv(out / "summary.csv", table, analyse.SUMMARY_COLUMNS)
    (out / "analysis.json").write_text(
        json.dumps(
            {
                "status": found["status"],
                "judge_agreement": found["agreement"],
                "pod": found["pod"],
                "open_pod": found.get("open_pod") or {},
                "rerun_against_exp1": same_as_exp1(
                    Path(args.work), Path(args.exp1_work)
                ),
                "repair": repair_stats(Path(args.work)),
                "summary": table,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    for line in table:
        print(
            json.dumps(
                {
                    k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in line.items()
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
