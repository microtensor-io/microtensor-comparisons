from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import statistics
import sys
from collections.abc import Sequence
from math import comb
from pathlib import Path
from typing import Any

from comparisons import prompts
from comparisons.prompts import read_rows, write_rows

Z = 1.96
HAND_CHECKS = 10
HOURLY_FALLBACK = 0.89
POD_TIME = "measured on the RTX 4090 pod"
PROVIDER_TIME = "provider response time through the relay"
GROUPS = {
    "M1": "Miner models",
    "M2": "Miner models",
    "M3": "Miner models",
    "B0": "Base model",
    "F1": "Frontier models",
    "F2": "Frontier models",
    "F3": "Frontier models",
    "P1": "Frontier models",
}
COLOURS = {
    "Miner models": "#2a78d6",
    "Frontier models": "#eb6834",
    "Base model": "#1baf7a",
}
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
RULE = "#e3e2dc"
REFERENCE = "#8a8983"


def wilson(passed: int, total: int) -> tuple[float, float]:
    if not total:
        return 0.0, 0.0
    share = passed / total
    spread = Z * math.sqrt(share * (1 - share) / total + Z * Z / (4 * total * total))
    centre = share + Z * Z / (2 * total)
    bottom = 1 + Z * Z / total
    return max(0.0, (centre - spread) / bottom), min(1.0, (centre + spread) / bottom)


def mcnemar(first_only: int, second_only: int) -> float:
    total = first_only + second_only
    if not total:
        return 1.0
    tail = (
        sum(comb(total, k) for k in range(min(first_only, second_only) + 1)) / 2**total
    )
    return min(1.0, 2 * tail)


def kappa(pairs: Sequence[tuple[bool, bool]]) -> float | None:
    if not pairs:
        return None
    count = len(pairs)
    agree = sum(a == b for a, b in pairs) / count
    first = sum(a for a, _ in pairs) / count
    second = sum(b for _, b in pairs) / count
    chance = first * second + (1 - first) * (1 - second)
    return 1.0 if chance == 1 else (agree - chance) / (1 - chance)


def percentile(values: Sequence[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    at = share * (len(ordered) - 1)
    low = int(math.floor(at))
    high = min(len(ordered) - 1, low + 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (at - low)


def mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def rule_scorer(package: Path) -> Any:
    sys.path.insert(0, str(package / "harness" / "src"))
    from ceval import scoring

    return scoring


def score_fact(scoring: Any, probe: dict[str, Any], reply: str) -> dict[str, Any]:
    answers = scoring.parse_answers(reply)
    answer = answers.get(1)
    parsed = answer is not None
    if not parsed:
        answer = reply.strip() or None
    scored = scoring.score_trial(
        {
            "answer": answer,
            "is_lure": probe["kind"] == "lure",
            "accept": probe["accept"],
            "value": probe["value"],
            "intrusion": probe["intrusion"],
        }
    )
    return {
        "id": probe["id"],
        "kind": probe["kind"],
        "source": probe["source"],
        "in_cut": probe["in_session"],
        "answer": answer,
        "parsed": parsed,
        "category": scored["category"],
        "correct": scored["correct"],
        "confident_wrong": scored["confident_wrong"],
        "lure_taken": int(scored["category"] == "confabulation"),
    }


def parse_vote(text: str) -> dict[str, Any] | None:
    found = re.search(r"\{.*\}", text or "", re.DOTALL)
    if found is None:
        return None
    try:
        held = json.loads(found.group(0))
    except ValueError:
        return None
    if not isinstance(held, dict) or "pass" not in held:
        return None
    return {"pass": bool(held["pass"]), "confident": held.get("confident")}


def judged(work: Path) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    key_path = work / "judge.key.json"
    if not key_path.is_file():
        return {}, {"pairs": 0, "kappa": None}
    key = json.loads(key_path.read_text(encoding="utf-8"))
    rows = {row["id"]: row for row in read_rows(work / "judge.jobs.results.jsonl")}
    found: dict[tuple[str, str], dict[str, Any]] = {}
    pairs: list[tuple[bool, bool]] = []
    for blind, case in key.items():
        votes = []
        for vote in range(prompts.JUDGE_VOTES):
            held = rows.get(f"jd-{blind}-v{vote}") or {}
            parsed = (
                None if held.get("error") else parse_vote(str(held.get("text") or ""))
            )
            if parsed is not None:
                votes.append(parsed)
        if not votes:
            continue
        passes = sum(v["pass"] for v in votes)
        passed = passes * 2 > len(votes)
        failing = [v for v in votes if not v["pass"]]
        confident = not passed and sum(
            v["confident"] is True for v in failing
        ) * 2 > len(failing)
        found[(case["contestant"], case["probe"])] = {
            "passed": passed,
            "votes": [v["pass"] for v in votes],
            "confident_failure": confident,
        }
        second = rows.get(f"j2-{blind}") or {}
        other = (
            None if second.get("error") else parse_vote(str(second.get("text") or ""))
        )
        if other is not None and second:
            pairs.append((passed, other["pass"]))
            found[(case["contestant"], case["probe"])]["second_judge"] = other["pass"]
    return found, {"pairs": len(pairs), "kappa": kappa(pairs)}


def cost_of(
    contestant: str, row: dict[str, Any], hourly: float
) -> tuple[float | None, str]:
    held = prompts.SUMMARISERS[contestant]
    if held["runs_on"] == "relay":
        price = prompts.LIST_PRICES[held["model"]]
        cost = (
            row["input_tokens"] * price["in"] + row["output_tokens"] * price["out"]
        ) / 1e6
        return cost, "relay receipt tokens at list price"
    compute = hourly * float(row["total_ms"]) / 3_600_000
    if contestant == "B0":
        return compute, "4090 time at the pod's hourly price"
    listed = (
        row["input_tokens"] * prompts.LIST_PRICE_IN_PER_MTOK
        + row["output_tokens"] * prompts.LIST_PRICE_OUT_PER_MTOK
    ) / 1e6
    return (
        compute + listed,
        "4090 time at the pod's hourly price plus the list price of 0.01 USD per million "
        "input tokens, output free",
    )


def assemble(args: argparse.Namespace) -> dict[str, Any]:
    work = Path(args.work)
    items = prompts.load_items(Path(args.items))
    pod = (
        json.loads((work / "pod_info.json").read_text())
        if (work / "pod_info.json").is_file()
        else {}
    )
    hourly = float(pod.get("usd_per_hour") or HOURLY_FALLBACK)
    replies = {row["id"]: row for row in read_rows(work / "reader.jobs.results.jsonl")}
    verdicts, agreement = judged(work)
    scoring = rule_scorer(Path(args.package)) if replies else None
    raw: list[dict[str, Any]] = []
    status: dict[str, str] = {}
    for contestant in prompts.CONTESTANTS:
        summariser = contestant in prompts.SUMMARISERS
        outputs = (
            {
                r["item_id"]: r
                for r in read_rows(work / "outputs" / f"{contestant}.jsonl")
            }
            if summariser
            else {}
        )
        graded = (
            {
                r["item_id"]: r
                for r in read_rows(work / "graded" / f"{contestant}.jsonl")
            }
            if summariser
            else {}
        )
        ran = [r for r in outputs.values() if not r.get("error")]
        read = any(key.startswith(f"rd-{contestant}-") for key in replies)
        if summariser and len(ran) < len(items):
            status[contestant] = f"{len(ran)} of {len(items)} summaries"
            if not ran:
                continue
        elif summariser and len(graded) < len(items):
            status[contestant] = f"summaries done, {len(graded)} of {len(items)} graded"
        elif not summariser and not read:
            status[contestant] = "waiting for the reader"
            continue
        else:
            status[contestant] = (
                "complete" if read else "summaries and grades done, no reader yet"
            )
        for item in items:
            label = item["label"]
            out = outputs.get(item["item_id"]) or {}
            if summariser and (not out or out.get("error")):
                continue
            row: dict[str, Any] = {
                "contestant": contestant,
                "label": {**prompts.SUMMARISERS, **prompts.REFERENCES}[contestant][
                    "label"
                ],
                "item_id": item["item_id"],
                "set": label["paper"]["set"],
                "session_tokens": label["input_tokens"],
                "budget_tokens": label["budget_tokens"],
            }
            if summariser:
                relay = prompts.SUMMARISERS[contestant]["runs_on"] == "relay"
                cost, basis = cost_of(contestant, out, hourly)
                row.update(
                    summary=out["text"],
                    input_tokens=out["input_tokens"],
                    output_tokens=out["output_tokens"],
                    ttft_ms=out.get("ttft_ms"),
                    total_ms=out["total_ms"],
                    time_source=PROVIDER_TIME if relay else POD_TIME,
                    cost_usd=cost,
                    cost_basis=basis,
                    gpu_cost_usd=None
                    if relay
                    else hourly * float(out["total_ms"]) / 3_600_000,
                    relay_cost_micros=out.get("cost_micros"),
                    receipt=out.get("receipt"),
                )
                mark = graded.get(item["item_id"])
                if mark is not None:
                    row.update(
                        {
                            name: mark[name]
                            for name in (
                                "format_valid",
                                "within_budget",
                                "summary_tokens",
                                "recall",
                                "hallucination",
                                "continuation",
                                "item_score",
                                "passed",
                                "reason",
                            )
                        }
                    )
            probes = []
            for probe in label["attached"]:
                held = replies.get(f"rd-{contestant}-{probe['id']}")
                if held is None or held.get("error"):
                    continue
                reply = str(held.get("text") or "")
                if probe["kind"] == "commitment":
                    verdict = verdicts.get((contestant, probe["id"]))
                    probes.append(
                        {
                            "id": probe["id"],
                            "kind": "commitment",
                            "reply": reply,
                            **(verdict or {}),
                        }
                    )
                else:
                    probes.append(score_fact(scoring, probe, reply))
            facts = [p for p in probes if p["kind"] == "fact"]
            lures = [p for p in probes if p["kind"] == "lure"]
            commitments = [
                p for p in probes if p["kind"] == "commitment" and "passed" in p
            ]
            row.update(
                facts_asked=len(facts),
                facts_correct=sum(p["correct"] or 0 for p in facts),
                facts_in_cut=sum(1 for p in facts if p["in_cut"]),
                facts_in_cut_correct=sum(
                    p["correct"] or 0 for p in facts if p["in_cut"]
                ),
                facts_confident_wrong=sum(p["confident_wrong"] or 0 for p in facts),
                lures_asked=len(lures),
                lures_taken=sum(p["lure_taken"] for p in lures),
                commitments_judged=len(commitments),
                commitments_passed=sum(1 for p in commitments if p["passed"]),
                commitments_confident_failures=sum(
                    1 for p in commitments if p["confident_failure"]
                ),
                probes=probes,
            )
            raw.append(row)
    return {
        "items": items,
        "raw": raw,
        "status": status,
        "agreement": agreement,
        "pod": pod,
        "hourly": hourly,
    }


def summarise(found: dict[str, Any]) -> list[dict[str, Any]]:
    table = []
    for contestant in prompts.CONTESTANTS:
        rows = [r for r in found["raw"] if r["contestant"] == contestant]
        if not rows:
            continue
        line: dict[str, Any] = {
            "contestant": contestant,
            "label": rows[0]["label"],
            "status": found["status"].get(contestant, ""),
            "items": len(rows),
        }
        marked = [r for r in rows if "passed" in r]
        if marked:
            passed = sum(1 for r in marked if r["passed"])
            low, high = wilson(passed, len(marked))
            measured = [
                r["continuation"]
                for r in marked
                if r["continuation"] is not None
                and r["format_valid"]
                and r["within_budget"]
            ]
            line.update(
                graded_items=len(marked),
                passed=passed,
                pass_rate=passed / len(marked),
                pass_rate_lower=low,
                pass_rate_upper=high,
                recall=mean([r["recall"] for r in marked]),
                hallucination=mean([r["hallucination"] for r in marked]),
                continuation=mean(measured),
                continuation_items=len(measured),
                format_valid_rate=mean([float(r["format_valid"]) for r in marked]),
                format_valid_items=sum(1 for r in marked if r["format_valid"]),
                within_budget_rate=mean([float(r["within_budget"]) for r in marked]),
                mean_item_score=mean([r["item_score"] for r in marked]),
            )
        asked = sum(r["facts_asked"] for r in rows)
        if asked:
            right = sum(r["facts_correct"] for r in rows)
            low, high = wilson(right, asked)
            seen = sum(r["facts_in_cut"] for r in rows)
            lures = sum(r["lures_asked"] for r in rows)
            wrong = sum(r["facts_confident_wrong"] for r in rows) + sum(
                r["lures_taken"] for r in rows
            )
            line.update(
                facts_asked=asked,
                facts_correct=right,
                planted_fact_recall=right / asked,
                planted_fact_recall_lower=low,
                planted_fact_recall_upper=high,
                planted_fact_recall_in_cut=(
                    sum(r["facts_in_cut_correct"] for r in rows) / seen
                    if seen
                    else None
                ),
                lures_taken=sum(r["lures_taken"] for r in rows),
                confident_wrong=wrong,
                confident_wrong_rate=wrong / (asked + lures),
            )
        judged_count = sum(r["commitments_judged"] for r in rows)
        if judged_count:
            kept = sum(r["commitments_passed"] for r in rows)
            low, high = wilson(kept, judged_count)
            broke = sum(r["commitments_confident_failures"] for r in rows)
            line.update(
                commitments_judged=judged_count,
                commitments_passed=kept,
                commitment_pass=kept / judged_count,
                commitment_pass_lower=low,
                commitment_pass_upper=high,
                confident_commitment_failure=broke / judged_count,
            )
        timed = [r["total_ms"] / 1000 for r in rows if r.get("total_ms") is not None]
        if timed:
            first = [r["ttft_ms"] / 1000 for r in rows if r.get("ttft_ms") is not None]
            costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
            line.update(
                median_time_s=percentile(timed, 0.5),
                p95_time_s=percentile(timed, 0.95),
                median_ttft_s=percentile(first, 0.5),
                time_source=rows[0]["time_source"],
                cost_per_compaction_usd=mean(costs),
                gpu_cost_per_compaction_usd=(
                    mean(
                        [
                            r["gpu_cost_usd"]
                            for r in rows
                            if r.get("gpu_cost_usd") is not None
                        ]
                    )
                ),
                cost_basis=rows[0]["cost_basis"],
                mean_output_tokens=mean([r["output_tokens"] for r in rows]),
                mean_input_tokens=mean([r["input_tokens"] for r in rows]),
            )
        table.append(line)
    return table


def paired(found: dict[str, Any]) -> list[dict[str, Any]]:
    by: dict[str, dict[str, dict[str, Any]]] = {}
    for row in found["raw"]:
        by.setdefault(row["contestant"], {})[row["item_id"]] = row
    tests = []

    def outcomes(contestant: str, metric: str) -> dict[str, bool]:
        held: dict[str, bool] = {}
        for item_id, row in by.get(contestant, {}).items():
            if metric == "pass":
                if "passed" in row:
                    held[item_id] = bool(row["passed"])
            else:
                for probe in row["probes"]:
                    if metric == "planted fact recall" and probe["kind"] == "fact":
                        held[probe["id"]] = bool(probe["correct"])
                    if metric == "commitment pass" and "passed" in probe:
                        held[probe["id"]] = bool(probe["passed"])
        return held

    for other in ("F1", "F2", "F3", "P1"):
        for metric in ("pass", "planted fact recall", "commitment pass"):
            first, second = outcomes("M1", metric), outcomes(other, metric)
            shared = sorted(set(first) & set(second))
            if not shared:
                continue
            only_first = sum(1 for k in shared if first[k] and not second[k])
            only_second = sum(1 for k in shared if second[k] and not first[k])
            tests.append(
                {
                    "metric": metric,
                    "first": "M1",
                    "second": other,
                    "pairs": len(shared),
                    "first_rate": sum(first[k] for k in shared) / len(shared),
                    "second_rate": sum(second[k] for k in shared) / len(shared),
                    "both": sum(1 for k in shared if first[k] and second[k]),
                    "first_only": only_first,
                    "second_only": only_second,
                    "neither": sum(1 for k in shared if not first[k] and not second[k]),
                    "p_value": mcnemar(only_first, only_second),
                    "test": "exact McNemar, two sided",
                }
            )
    return tests


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(
                [
                    ""
                    if row.get(name) is None
                    else (
                        f"{row[name]:.6g}"
                        if isinstance(row[name], float)
                        else row[name]
                    )
                    for name in columns
                ]
            )


SUMMARY_COLUMNS = [
    "contestant",
    "label",
    "status",
    "items",
    "graded_items",
    "pass_rate",
    "pass_rate_lower",
    "pass_rate_upper",
    "recall",
    "hallucination",
    "continuation",
    "continuation_items",
    "format_valid_rate",
    "within_budget_rate",
    "mean_item_score",
    "planted_fact_recall",
    "planted_fact_recall_lower",
    "planted_fact_recall_upper",
    "planted_fact_recall_in_cut",
    "confident_wrong_rate",
    "lures_taken",
    "commitment_pass",
    "commitment_pass_lower",
    "commitment_pass_upper",
    "confident_commitment_failure",
    "median_time_s",
    "p95_time_s",
    "median_ttft_s",
    "time_source",
    "cost_per_compaction_usd",
    "cost_basis",
    "mean_input_tokens",
    "mean_output_tokens",
]
TEST_COLUMNS = [
    "metric",
    "first",
    "second",
    "pairs",
    "first_rate",
    "second_rate",
    "both",
    "first_only",
    "second_only",
    "neither",
    "p_value",
    "test",
]


def chart(table: list[dict[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    dots = [
        r
        for r in table
        if r.get("pass_rate") is not None and r.get("cost_per_compaction_usd")
    ]
    facts = {
        r["contestant"]: r for r in table if r.get("planted_fact_recall") is not None
    }
    panels = [("pass_rate", "Arena pass rate", "pass_rate_lower", "pass_rate_upper")]
    if any(r["contestant"] in facts for r in dots):
        panels.append(
            (
                "planted_fact_recall",
                "Planted fact recall",
                "planted_fact_recall_lower",
                "planted_fact_recall_upper",
            )
        )
    figure, axes = plt.subplots(
        1,
        len(panels),
        figsize=(6.4 * len(panels) + 0.6, 5.2),
        dpi=200,
        facecolor=SURFACE,
    )
    axes = [axes] if len(panels) == 1 else list(axes)
    for axis, (name, title, low, high) in zip(axes, panels, strict=True):
        axis.set_facecolor(SURFACE)
        shown = [r for r in dots if r.get(name) is not None]
        for row in shown:
            colour = COLOURS[GROUPS[row["contestant"]]]
            x, y = row["cost_per_compaction_usd"], row[name] * 100
            axis.plot(
                [x, x],
                [row[low] * 100, row[high] * 100],
                color=colour,
                linewidth=1,
                alpha=0.45,
            )
            axis.plot(
                x,
                y,
                "o",
                markersize=9,
                color=colour,
                markeredgecolor=SURFACE,
                markeredgewidth=2,
                zorder=3,
            )
            axis.annotate(
                f"{row['contestant']} {row['label']}",
                (x, y),
                xytext=(8, 6),
                textcoords="offset points",
                fontsize=7.5,
                color=INK_SOFT,
            )
        if name == "planted_fact_recall":
            for mark in ("C1", "C0"):
                if mark in facts:
                    level = facts[mark]["planted_fact_recall"] * 100
                    axis.axhline(
                        level, color=REFERENCE, linewidth=1, linestyle=(0, (4, 3))
                    )
                    axis.annotate(
                        f"{mark} {facts[mark]['label']} {level:.0f}%",
                        (1.0, level),
                        xycoords=("axes fraction", "data"),
                        xytext=(-4, 4),
                        textcoords="offset points",
                        ha="right",
                        fontsize=7.5,
                        color=INK_SOFT,
                    )
        axis.set_xscale("log")
        axis.set_ylim(-4, 104)
        axis.set_yticks(range(0, 101, 20))
        axis.set_yticklabels([f"{v}%" for v in range(0, 101, 20)])
        axis.grid(axis="y", color=RULE, linewidth=0.8)
        axis.set_axisbelow(True)
        for side in ("top", "right", "left"):
            axis.spines[side].set_visible(False)
        axis.spines["bottom"].set_color(RULE)
        axis.tick_params(colors=INK_SOFT, labelsize=8, length=0)
        axis.set_xlabel(
            "Cost per compaction, USD (log scale)", fontsize=8.5, color=INK_SOFT
        )
        axis.set_title(title, loc="left", fontsize=11, color=INK, pad=12)
        costs = [r["cost_per_compaction_usd"] for r in shown]
        if costs:
            axis.set_xlim(min(costs) / 2.2, max(costs) * 6)
    groups = [g for g in COLOURS if any(GROUPS[r["contestant"]] == g for r in dots)]
    figure.legend(
        handles=[
            Line2D(
                [],
                [],
                marker="o",
                linestyle="",
                markersize=7,
                color=COLOURS[g],
                markeredgecolor=SURFACE,
                label=g,
            )
            for g in groups
        ],
        loc="upper right",
        ncol=len(groups),
        frameon=False,
        fontsize=8,
        labelcolor=INK_SOFT,
        bbox_to_anchor=(0.985, 0.995),
    )
    figure.text(
        0.012,
        0.012,
        "Whiskers are Wilson 95% intervals. Dashed lines are the reader on the full cut (C1) "
        "and on its last 3,072 tokens (C0).",
        fontsize=7,
        color=INK_SOFT,
    )
    figure.tight_layout(rect=(0, 0.035, 1, 0.95))
    figure.savefig(path, facecolor=SURFACE)
    plt.close(figure)


def hand_check(found: dict[str, Any], path: Path) -> None:
    rows = [r for r in found["raw"] if r["contestant"] in prompts.SUMMARISERS]
    if not rows:
        return
    rng = random.Random(prompts.SEED)
    chosen = rng.sample(rows, min(HAND_CHECKS, len(rows)))
    lines = [
        "# Hand check",
        "",
        "Ten summaries drawn at random with seed "
        f"{prompts.SEED}. One person reads each summary against its session "
        "(`ctx_compress/exp1/data/items.jsonl`, field `task.user`) and fills the last three columns.",
        "",
        "| # | Contestant | Item | Score | Faithful (yes or no) | Invented detail (yes or no) | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for at, row in enumerate(chosen, 1):
        score = "" if row.get("item_score") is None else f"{row['item_score']:.2f}"
        lines.append(
            f"| {at} | {row['contestant']} | {row['item_id']} | {score} | | | |"
        )
    for at, row in enumerate(chosen, 1):
        lines += [
            "",
            f"## {at}. {row['contestant']} on {row['item_id']}",
            "",
            "```",
            row["summary"],
            "```",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="comparisons-analyse")
    parser.add_argument("--items", default="ctx_compress/exp1/data/items.jsonl")
    parser.add_argument("--work", default="ctx_compress/exp1/results/work")
    parser.add_argument("--out", default="ctx_compress/exp1/results")
    parser.add_argument("--package", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    found = assemble(args)
    table = summarise(found)
    tests = paired(found)
    write_rows(out / "raw.jsonl", found["raw"])
    write_csv(out / "summary.csv", table, SUMMARY_COLUMNS)
    write_csv(out / "tests.csv", tests, TEST_COLUMNS)
    chart(table, out / "chart.png")
    hand_check(found, out / "hand_check.md")
    (out / "analysis.json").write_text(
        json.dumps(
            {
                "status": found["status"],
                "judge_agreement": found["agreement"],
                "pod": found["pod"],
                "summary": table,
                "tests": tests,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    for line in table:
        print(
            line["contestant"],
            line["status"],
            {
                k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in line.items()
                if k
                in (
                    "graded_items",
                    "pass_rate",
                    "pass_rate_lower",
                    "recall",
                    "hallucination",
                    "continuation",
                    "format_valid_rate",
                    "within_budget_rate",
                    "planted_fact_recall",
                    "commitment_pass",
                    "median_time_s",
                    "p95_time_s",
                    "cost_per_compaction_usd",
                )
            },
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
