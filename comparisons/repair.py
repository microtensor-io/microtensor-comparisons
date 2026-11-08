from __future__ import annotations

import argparse
import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from microtensor_subnet.validator import compress
from microtensor_subnet.validator.sandbox import judge as probe_judge

MISSING = "Not recorded."
MAX_SPAN = 40
MARKUP = re.compile(r"^[\s#*_>:-]+|[\s#*_:]+$")


def heading_of(line: str) -> str:
    stripped = line.strip()
    if not stripped or not stripped.startswith(("#", "**")):
        return ""
    name = MARKUP.sub("", stripped).strip().lower()
    for heading in compress.HEADINGS:
        if name == heading.lower():
            return heading
    return ""


def squeeze(line: str) -> tuple[str, int]:
    lead = line[: len(line) - len(line.lstrip())]
    words = line.split()
    kept: list[str] = []
    dropped = 0
    index = 0
    while index < len(words):
        for span in range(min(MAX_SPAN, len(kept), len(words) - index), 1, -1):
            if words[index : index + span] == kept[-span:]:
                index += span
                dropped += span
                break
        else:
            kept.append(words[index])
            index += 1
    return lead + " ".join(kept), dropped


def sections_of(text: str) -> tuple[dict[str, list[str]], dict[str, int]]:
    found: dict[str, list[str]] = {heading: [] for heading in compress.HEADINGS}
    present: list[str] = []
    seen: set[str] = set()
    counts = {"lines_dropped": 0, "words_dropped": 0}
    current = compress.HEADINGS[0]
    for raw in text.strip().split("\n"):
        heading = heading_of(raw)
        if heading:
            current = heading
            if heading not in present:
                present.append(heading)
            continue
        line, dropped = squeeze(raw.rstrip())
        counts["words_dropped"] += dropped
        key = " ".join(line.split()).lower()
        if key and key in seen:
            counts["lines_dropped"] += 1
            continue
        if key:
            seen.add(key)
        found[current].append(line)
    counts["headings_found"] = len(present)
    return found, counts


def render(found: dict[str, list[str]]) -> str:
    parts = []
    for heading in compress.HEADINGS:
        body = "\n".join(found[heading]).strip()
        parts.append(f"{compress.HEADING_MARK}{heading}\n{body or MISSING}")
    return "\n\n".join(parts) + "\n"


def trim(found: dict[str, list[str]], budget: int, count: Callable[[str], int]) -> int:
    trimmed = 0
    while count(render(found)) > budget:
        longest = max(compress.HEADINGS, key=lambda h: count("\n".join(found[h])))
        lines = [line for line in found[longest] if line.strip()]
        if len(lines) <= 1:
            break
        while found[longest] and not found[longest][-1].strip():
            found[longest].pop()
        found[longest].pop()
        trimmed += 1
    return trimmed


def repair(
    text: str, budget: int, count: Callable[[str], int]
) -> tuple[str, dict[str, Any]]:
    started = time.perf_counter()
    valid = compress.sections(text, compress.HEADINGS) is not None
    if valid and count(text) <= budget:
        return text, {
            "repaired": False,
            "repair_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    found, counts = sections_of(text)
    added = [
        heading
        for heading in compress.HEADINGS
        if not "\n".join(found[heading]).strip()
    ]
    trimmed = trim(found, budget, count)
    fixed = render(found)
    return fixed, {
        "repaired": True,
        "was_valid": valid,
        "headings_added": added,
        "lines_trimmed": trimmed,
        **counts,
        "valid_after": compress.sections(fixed, compress.HEADINGS) is not None,
        "tokens_before": count(text),
        "tokens_after": count(fixed),
        "repair_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="comparisons-repair")
    parser.add_argument("--items", default="ctx_compress/exp1/data/items.jsonl")
    parser.add_argument("--work", default="ctx_compress/exp2/results/work")
    parser.add_argument("--source", default="M1")
    parser.add_argument("--out", default="R1")
    parser.add_argument("--cache", default=".cache")
    args = parser.parse_args()
    count = probe_judge.token_counter(Path(args.cache) / "tokenizer")
    items = {
        row["item_id"]: row
        for row in (
            json.loads(line)
            for line in Path(args.items).read_text(encoding="utf-8").splitlines()
            if line
        )
    }
    source = Path(args.work) / "outputs" / f"{args.source}.jsonl"
    target = Path(args.work) / "outputs" / f"{args.out}.jsonl"
    rows = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line
    ]
    written = []
    for row in rows:
        budget = int(items[row["item_id"]]["label"]["budget_tokens"])
        text, report = repair(str(row.get("text") or ""), budget, count)
        fixed = {
            **row,
            "contestant": args.out,
            "repaired_from": args.source,
            "text": text,
            "repair": report,
        }
        if isinstance(row.get("total_ms"), int | float):
            fixed["total_ms"] = round(float(row["total_ms"]) + report["repair_ms"], 1)
        written.append(json.dumps(fixed, ensure_ascii=False))
        print(
            row["item_id"],
            json.dumps({k: v for k, v in report.items() if k != "headings_added"}),
            flush=True,
        )
    target.write_text("\n".join(written) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
