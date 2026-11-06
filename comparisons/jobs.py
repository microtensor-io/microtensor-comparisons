from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

from comparisons import prompts
from comparisons.prompts import read_rows, write_rows

MAX_RELAY_CHARS = 600_000


def _relay(contestant: str) -> bool:
    return prompts.SUMMARISERS[contestant]["runs_on"] == "relay"


def _chars(messages: list[dict[str, str]]) -> int:
    return sum(len(m["content"]) for m in messages)


def summaries(args: argparse.Namespace) -> int:
    work = Path(args.work)
    items = prompts.load_items(Path(args.items))
    pi = prompts.pi_prompts(Path(args.pi))
    (work / "pi_prompt.json").parent.mkdir(parents=True, exist_ok=True)
    (work / "pi_prompt.json").write_text(json.dumps(pi, indent=1), encoding="utf-8")
    rows = []
    for contestant in prompts.SUMMARISERS:
        if not _relay(contestant):
            continue
        for item in items:
            messages = prompts.summary_messages(contestant, item, pi)
            if _chars(messages) > MAX_RELAY_CHARS:
                raise ValueError(f"{item['item_id']} is over the relay's character limit")
            rows.append(
                {
                    "id": f"sum-{contestant}-{item['item_id']}",
                    "model": prompts.SUMMARISERS[contestant]["model"],
                    "messages": messages,
                    "max_tokens": prompts.MAX_SUMMARY_TOKENS,
                }
            )
    write_rows(work / "summaries.jobs.jsonl", rows)
    print(f"{len(rows)} summary jobs")
    return 0


def collect(args: argparse.Namespace) -> int:
    work = Path(args.work)
    found = {row["id"]: row for row in read_rows(work / "summaries.jobs.results.jsonl")}
    items = prompts.load_items(Path(args.items))
    for contestant in prompts.SUMMARISERS:
        if not _relay(contestant):
            continue
        rows = []
        for item in items:
            held = found.get(f"sum-{contestant}-{item['item_id']}") or {}
            row: dict[str, Any] = {"contestant": contestant, "item_id": item["item_id"]}
            if not held or held.get("error"):
                row["error"] = held.get("error") or "no result"
            else:
                row.update(
                    text=held["text"],
                    input_tokens=held["tokens_in"],
                    output_tokens=held["tokens_out"],
                    ttft_ms=None,
                    total_ms=held["latency_ms"],
                    wall_ms=held["wall_ms"],
                    cost_micros=held.get("cost_micros"),
                    finish_reason=held["finish_reason"],
                    receipt=held.get("receipt"),
                    model=held["model"],
                )
            rows.append(row)
        write_rows(work / "outputs" / f"{contestant}.jsonl", rows)
        missing = sum(1 for row in rows if row.get("error"))
        print(f"{contestant}: {len(rows) - missing} of {len(rows)} outputs")
    return 0


def floor_text(text: str, tokenizer: Any) -> str:
    offsets = tokenizer.encode(text, add_special_tokens=False).offsets
    if len(offsets) <= prompts.FLOOR_TOKENS:
        return text
    return text[offsets[-prompts.FLOOR_TOKENS][0] :]


def contexts(work: Path, items: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    from arenas.compress import build
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_pretrained(build.TOKENIZER, revision=build.TOKENIZER_REVISION)
    found: dict[tuple[str, str], str] = {}
    for contestant in prompts.SUMMARISERS:
        rows = {row["item_id"]: row for row in read_rows(work / "outputs" / f"{contestant}.jsonl")}
        for item in items:
            row = rows.get(item["item_id"])
            if row is None or row.get("error"):
                raise ValueError(f"{contestant} has no output for {item['item_id']}")
            found[(contestant, item["item_id"])] = str(row["text"]).strip()
    for item in items:
        found[("C1", item["item_id"])] = item["task"]["user"]
        found[("C0", item["item_id"])] = floor_text(item["task"]["user"], tokenizer)
    return found


def probes_of(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        probe
        for probe in item["label"]["attached"]
        if probe["kind"] != "commitment" or probe["scored"]
    ]


def reader(args: argparse.Namespace) -> int:
    work = Path(args.work)
    items = prompts.load_items(Path(args.items))
    template = (Path(args.package) / "materials/prompts/probe.md").read_text(encoding="utf-8")
    held = contexts(work, items)
    rows = []
    for contestant in prompts.CONTESTANTS:
        for item in items:
            context = held[(contestant, item["item_id"])]
            for probe in probes_of(item):
                commitment = probe["kind"] == "commitment"
                message = (
                    prompts.commitment_message(probe)
                    if commitment
                    else prompts.fact_message(template, probe["question"])
                )
                rows.append(
                    {
                        "id": f"rd-{contestant}-{probe['id']}",
                        "model": prompts.READER,
                        "messages": prompts.reader_messages(context, message),
                        "max_tokens": prompts.REPLY_TOKENS
                        if commitment
                        else prompts.FACT_ANSWER_TOKENS,
                    }
                )
    over = [row["id"] for row in rows if _chars(row["messages"]) > MAX_RELAY_CHARS]
    if over:
        raise ValueError(f"over the relay's character limit: {over[:5]}")
    write_rows(work / "reader.jobs.jsonl", rows)
    floors = {
        item["item_id"]: held[("C0", item["item_id"])] for item in items
    }
    (work / "floor_contexts.json").write_text(
        json.dumps(floors, ensure_ascii=False), encoding="utf-8"
    )
    print(f"{len(rows)} reader jobs")
    return 0


def judge(args: argparse.Namespace) -> int:
    work = Path(args.work)
    items = prompts.load_items(Path(args.items))
    brief = (Path(args.package) / "materials/s4/scorer.md").read_text(encoding="utf-8")
    replies = {row["id"]: row for row in read_rows(work / "reader.jobs.results.jsonl")}
    cases = []
    for contestant in prompts.CONTESTANTS:
        for item in items:
            for probe in probes_of(item):
                if probe["kind"] != "commitment":
                    continue
                held = replies.get(f"rd-{contestant}-{probe['id']}") or {}
                if not held or held.get("error"):
                    raise ValueError(f"no reader reply for {contestant} {probe['id']}")
                cases.append((contestant, probe, str(held["text"])))
    rng = random.Random(prompts.SEED)
    order = list(range(len(cases)))
    rng.shuffle(order)
    second = set(rng.sample(order, round(prompts.SECOND_JUDGE_SHARE * len(order))))
    key: dict[str, dict[str, str]] = {}
    first_rows, second_rows = [], []
    for blind, at in enumerate(order):
        contestant, probe, reply = cases[at]
        name = f"{blind:04d}"
        key[name] = {"contestant": contestant, "probe": probe["id"]}
        messages = prompts.judge_messages(brief, probe, reply)
        for vote in range(prompts.JUDGE_VOTES):
            first_rows.append(
                {
                    "id": f"jd-{name}-v{vote}",
                    "model": prompts.JUDGE,
                    "messages": messages,
                    "max_tokens": prompts.JUDGE_TOKENS,
                }
            )
        if at in second:
            second_rows.append(
                {
                    "id": f"j2-{name}",
                    "model": prompts.SECOND_JUDGE,
                    "messages": messages,
                    "max_tokens": prompts.JUDGE_TOKENS,
                }
            )
    write_rows(work / "judge.jobs.jsonl", [*first_rows, *second_rows])
    (work / "judge.key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    print(f"{len(first_rows)} judge jobs, {len(second_rows)} second judge jobs")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="comparisons-jobs")
    parser.add_argument("step", choices=["summaries", "collect", "reader", "judge"])
    parser.add_argument("--items", default="ctx_compress/exp1/data/items.jsonl")
    parser.add_argument("--work", default="ctx_compress/exp1/results/work")
    parser.add_argument("--package", default="")
    parser.add_argument("--pi", default="")
    args = parser.parse_args(argv)
    return int(
        {"summaries": summaries, "collect": collect, "reader": reader, "judge": judge}[args.step](
            args
        )
    )


if __name__ == "__main__":
    sys.exit(main())
