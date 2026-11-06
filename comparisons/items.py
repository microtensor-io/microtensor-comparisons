from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from arenas.compress import build
from arenas.compress.facts import mentions
from arenas.compress.sources import Session, parse, pi_row
from arenas.pool import Pool, write

ARENA = "ctx_compress"
SEED = 1
MIN_PROBES = 2
TESTS = ["slm"]


def _flat(text: str) -> str:
    return " ".join(text.split())


def _fact(fact: dict[str, Any], session: str) -> dict[str, Any]:
    lure = bool(fact["is_lure"])
    found = None if lure else re.search(fact["accept"], session, re.IGNORECASE)
    return {
        "id": fact["uid"],
        "kind": "lure" if lure else "fact",
        "source": fact["source"],
        "detail": fact["kind"],
        "question": fact["question"],
        "value": fact["value"],
        "value_old": fact["value_old"],
        "accept": fact["accept"],
        "intrusion": fact["intrusion"],
        "keys": [] if lure else [found.group(0) if found else fact["value"]],
        "in_session": bool(found),
    }


def _commitment(
    probe: dict[str, Any], session: str, skipped: set[str]
) -> dict[str, Any]:
    flat = _flat(session)
    keys = [str(key) for key in probe["dependency_text"]]
    return {
        "id": probe["pid"],
        "kind": "commitment",
        "location": probe["location"],
        "type": probe["type"],
        "dependency": probe["dependency"],
        "violation": probe["violation"],
        "instruction": probe["instruction"],
        "control_instruction": probe["control_instruction"],
        "criterion": probe["pass_rule"]["judged"],
        "repaired": bool(probe.get("repaired")),
        "scored": probe["pid"] not in skipped,
        "keys": keys,
        "in_session": all(_flat(key) in flat for key in keys),
    }


def _keep_visible(item: dict[str, Any]) -> dict[str, int]:
    session = item["task"]["user"]
    label = item["label"]
    facts = [
        f for f in label["facts"] if any(mentions(session, a) for a in f["aliases"])
    ]
    probes = [
        p
        for p in label["probes"]
        if p.get("type", "exact") != "exact"
        or any(mentions(session, a) for a in p["answers"])
    ]
    pruned = {
        "facts": len(label["facts"]) - len(facts),
        "probes": len(label["probes"]) - len(probes),
    }
    label["facts"], label["probes"] = facts, probes
    return pruned


def _item(
    session: Session, item_id: str, count: Callable[[str], int]
) -> tuple[dict[str, Any], dict[str, int]] | None:
    item = build.make_item(
        session,
        len(session.steps),
        count,
        item_id,
        TESTS,
        min_tokens=0,
        min_probes=MIN_PROBES,
    )
    if item is None:
        return None
    return item, _keep_visible(item)


def set_a(
    folder: Path, count: Callable[[str], int]
) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    dropped: list[str] = []
    for path in sorted(folder.glob("*.jsonl")):
        plan = json.loads(path.with_suffix(".plan.json").read_text(encoding="utf-8"))
        row = pi_row(path)
        row.update(
            session_id=plan["session_id"], repo=f"s1-{plan['story']}", license="MIT"
        )
        made = _item(parse(row, "pi"), f"exp1-a-{plan['session_id']}", count)
        if made is None:
            dropped.append(plan["session_id"])
            continue
        item, pruned = made
        session = item["task"]["user"]
        item["label"]["attached"] = [_fact(fact, session) for fact in plan["facts"]]
        item["label"]["paper"] = {
            "set": "A",
            "session": plan["session_id"],
            "story": plan["story"],
            "phases": plan["phases_written"],
            "licence": "MIT",
            "labels_not_rendered": pruned,
        }
        items.append(item)
    return items, dropped


def set_b(
    folder: Path, package: Path, count: Callable[[str], int]
) -> tuple[list[dict[str, Any]], list[str]]:
    selection = json.loads(
        (package / "materials/s4/selection.json").read_text(encoding="utf-8")
    )
    probes = json.loads(
        (package / "materials/s4/probes.json").read_text(encoding="utf-8")
    )
    config = json.loads(
        (package / "replication.config.json").read_text(encoding="utf-8")
    )
    skipped = set(config["study4"]["skip_probes"])
    items: list[dict[str, Any]] = []
    dropped: list[str] = []
    for chosen in sorted(selection["selected"], key=lambda row: row["sid"]):
        sid = chosen["sid"]
        row = pi_row(folder / f"{sid}.jsonl")
        row.update(session_id=sid, repo=chosen["src"], license=chosen["licence"])
        made = _item(parse(row, "pi"), f"exp1-b-{sid}", count)
        if made is None:
            dropped.append(sid)
            continue
        item, pruned = made
        session = item["task"]["user"]
        item["label"]["attached"] = [
            _commitment(probe, session, skipped)
            for probe in probes
            if probe["sid"] == sid
        ]
        item["label"]["paper"] = {
            "set": "B",
            "session": sid,
            "source": chosen["src"],
            "file": chosen["file"],
            "sha256": chosen["sha256"],
            "licence": chosen["licence"],
            "labels_not_rendered": pruned,
        }
        items.append(item)
    return items, dropped


def report(pool: Pool, dropped: dict[str, list[str]], tokenizer: str) -> dict[str, Any]:
    attached = [p for item in pool.items for p in item["label"]["attached"]]
    facts = [p for p in attached if p["kind"] == "fact"]
    commitments = [p for p in attached if p["kind"] == "commitment"]
    by_source: dict[str, list[int]] = {}
    for probe in facts:
        held = by_source.setdefault(probe["source"], [0, 0])
        held[0] += int(probe["in_session"])
        held[1] += 1
    return {
        "tokenizer": tokenizer,
        "items": len(pool.items),
        "by_set": {
            name: sum(1 for i in pool.items if i["label"]["paper"]["set"] == name)
            for name in ("A", "B")
        },
        "dropped_over_cap_or_thin": dropped,
        "input_tokens": build.stats([i["label"]["input_tokens"] for i in pool.items]),
        "facts": {
            "planted": len(facts),
            "in_session": sum(1 for p in facts if p["in_session"]),
            "by_source": {
                k: {"in_session": v[0], "planted": v[1]} for k, v in by_source.items()
            },
            "lures": sum(1 for p in attached if p["kind"] == "lure"),
        },
        "commitments": {
            "probes": len(commitments),
            "scored": sum(1 for p in commitments if p["scored"]),
            "in_session": sum(1 for p in commitments if p["in_session"]),
        },
        "arena_labels": {
            "not_rendered": {
                kind: sum(
                    i["label"]["paper"]["labels_not_rendered"][kind] for i in pool.items
                )
                for kind in ("facts", "probes")
            },
            "facts": build.stats([len(i["label"]["facts"]) for i in pool.items]),
            "probes": build.stats([len(i["label"]["probes"]) for i in pool.items]),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="comparisons-items")
    parser.add_argument("--package", required=True)
    parser.add_argument("--set-a", required=True)
    parser.add_argument("--set-b", required=True)
    parser.add_argument("--out", default="ctx_compress/exp1/data")
    args = parser.parse_args(argv)
    count, tokenizer = build.counter()
    pool = Pool(arena_id=ARENA, seed=SEED)
    first, dropped_a = set_a(Path(args.set_a), count)
    second, dropped_b = set_b(Path(args.set_b), Path(args.package), count)
    pool.items = [*first, *second]
    build.add_goal_probes(pool, random.Random(SEED))
    problems = build.check(pool)
    out = Path(args.out)
    write(pool, out)
    found = report(pool, {"A": dropped_a, "B": dropped_b}, tokenizer)
    found["problems"] = problems
    (out / "report.json").write_text(json.dumps(found, indent=2), encoding="utf-8")
    print(json.dumps(found, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
