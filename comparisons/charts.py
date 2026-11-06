from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

from comparisons.prompts import read_rows

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
RULE = "#e3e2dc"
SERIES = ["#1e46b4", "#3b78e7", "#79b0f2", "#8a877f"]
COLOURS = {
    "M1": "#1e46b4",
    "M2": "#3b78e7",
    "M3": "#79b0f2",
    "B0": "#8a877f",
    "F1": "#8f3a12",
    "F2": "#e8742c",
    "P1": "#1a9a6c",
}
SHORT = {"F1": "Qwen\n27B", "F2": "Gemma\n31B", "P1": "Qwen\nPi prompt"}
PASSED = "#1e46b4"
NEUTRAL = "#c9c7c0"
FAILED = "#e8742c"
LIMIT = "#8a877f"
DPI = 200
SEED = 20261106


def colour(row: dict[str, Any]) -> str:
    return COLOURS.get(str(row.get("contestant")), LIMIT)


def short(row: dict[str, Any]) -> str:
    if row.get("contestant") in SHORT:
        return SHORT[row["contestant"]]
    label = str(row["label"])
    if label.startswith("UID"):
        return " ".join(label.split()[:2])
    return "Base" if "base" in label.lower() else label


def style(axis: Any) -> None:
    axis.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.spines["bottom"].set_color(RULE)
    axis.tick_params(colors=INK_SOFT, labelsize=8, length=0)
    axis.set_axisbelow(True)


def quality(table: list[dict[str, Any]], out: Path, plt: Any) -> None:
    panels = [
        ("Pass rate", lambda r: r["pass_rate"], True),
        ("Recall of key facts", lambda r: r["recall"], False),
        ("Kept all 9 headings", lambda r: r["format_valid_rate"], False),
    ]
    figure, axes = plt.subplots(
        1, 3, figsize=(12.6, 3.9), dpi=DPI, facecolor=SURFACE, sharey=True
    )
    for axis, (title, value, whiskers) in zip(axes, panels, strict=True):
        style(axis)
        for at, row in enumerate(table):
            height = value(row) * 100
            axis.bar(at, height, width=0.62, color=colour(row))
            top = height
            if whiskers:
                low, high = row["pass_rate_lower"] * 100, row["pass_rate_upper"] * 100
                axis.plot([at, at], [low, high], color=INK, linewidth=1)
                for edge in (low, high):
                    axis.plot(
                        [at - 0.09, at + 0.09], [edge, edge], color=INK, linewidth=1
                    )
                top = high
            axis.text(
                at,
                top + 2,
                f"{height:.1f}%",
                ha="center",
                fontsize=8,
                color=INK,
                weight="bold",
            )
        axis.set_xticks(range(len(table)))
        axis.set_xticklabels([short(r) for r in table], fontsize=7.5, color=INK_SOFT)
        axis.set_ylim(0, 110)
        axis.set_yticks(range(0, 101, 20))
        axis.set_yticklabels([f"{v}%" for v in range(0, 101, 20)])
        axis.grid(axis="y", color=RULE, linewidth=0.7)
        axis.set_title(title, loc="left", fontsize=10, color=INK, pad=8)
    figure.text(
        0.012,
        0.012,
        f"{table[0]['graded_items']} items per model. Whiskers are Wilson 95% intervals.",
        fontsize=7,
        color=INK_SOFT,
    )
    figure.tight_layout(rect=(0, 0.05, 1, 1))
    figure.savefig(out, facecolor=SURFACE)
    plt.close(figure)


def failures(table: list[dict[str, Any]], out: Path, plt: Any) -> None:
    from matplotlib.patches import Patch

    figure, axis = plt.subplots(figsize=(9.6, 2.6), dpi=DPI, facecolor=SURFACE)
    style(axis)
    total = max(r["graded_items"] for r in table)
    for at, row in enumerate(table):
        passed = row["passed"]
        scored = max(0, row["format_valid_items"] - passed)
        broken = row["graded_items"] - row["format_valid_items"]
        left = 0
        for count, colour, ink in (
            (passed, PASSED, "white"),
            (scored, NEUTRAL, INK),
            (broken, FAILED, INK),
        ):
            if not count:
                continue
            axis.barh(
                at,
                count,
                left=left,
                height=0.58,
                color=colour,
                edgecolor=SURFACE,
                linewidth=2,
            )
            axis.text(
                left + count / 2,
                at,
                str(count),
                ha="center",
                va="center",
                fontsize=8,
                color=ink,
                weight="bold",
            )
            left += count
    axis.set_yticks(range(len(table)))
    axis.set_yticklabels([short(r) for r in table], fontsize=8.5, color=INK)
    axis.invert_yaxis()
    axis.set_xlim(0, total)
    axis.set_xticks(range(0, total + 1, 9))
    axis.set_xlabel(f"Items, out of {total}", fontsize=8, color=INK_SOFT)
    axis.grid(axis="x", color=RULE, linewidth=0.7)
    axis.legend(
        handles=[
            Patch(color=PASSED, label="Passed"),
            Patch(color=NEUTRAL, label="Right format, score under 0.60"),
            Patch(color=FAILED, label="Failed a format gate"),
        ],
        loc="lower center",
        bbox_to_anchor=(0.5, 1.0),
        ncol=3,
        frameon=False,
        fontsize=8,
        labelcolor=INK_SOFT,
    )
    figure.tight_layout()
    figure.savefig(out, facecolor=SURFACE)
    plt.close(figure)


def lengths(
    table: list[dict[str, Any]],
    raw: list[dict[str, Any]],
    limit: int,
    out: Path,
    plt: Any,
) -> None:
    from matplotlib.lines import Line2D

    rng = random.Random(SEED)
    figure, axis = plt.subplots(figsize=(9.6, 3.0), dpi=DPI, facecolor=SURFACE)
    style(axis)
    for at, row in enumerate(table):
        mine = [r for r in raw if r["contestant"] == row["contestant"]]
        for item in mine:
            y = at + rng.uniform(-0.24, 0.24)
            whole = bool(item.get("format_valid"))
            axis.plot(
                item["output_tokens"],
                y,
                "o",
                markersize=5.5,
                markerfacecolor=colour(row) if whole else SURFACE,
                markeredgecolor=colour(row) if not whole else SURFACE,
                markeredgewidth=1.2,
            )
        capped = sum(1 for r in mine if r["output_tokens"] >= limit)
        axis.text(
            limit + 45,
            at,
            f"{capped} of {len(mine)} at the limit",
            va="center",
            fontsize=8,
            color=INK_SOFT,
        )
    axis.axvline(limit, color=LIMIT, linewidth=1, linestyle=(0, (4, 3)))
    axis.text(
        limit,
        -0.72,
        f"{limit:,} token limit",
        ha="center",
        fontsize=7.5,
        color=INK_SOFT,
    )
    axis.set_yticks(range(len(table)))
    axis.set_yticklabels([short(r) for r in table], fontsize=8.5, color=INK)
    axis.set_ylim(len(table) - 0.45, -0.95)
    axis.set_xlim(0, limit + 620)
    axis.set_xlabel("Output tokens of each summary", fontsize=8, color=INK_SOFT)
    axis.grid(axis="x", color=RULE, linewidth=0.7)
    axis.legend(
        handles=[
            Line2D(
                [],
                [],
                marker="o",
                linestyle="",
                markersize=5.5,
                color=INK_SOFT,
                label="Kept all 9 headings",
            ),
            Line2D(
                [],
                [],
                marker="o",
                linestyle="",
                markersize=5.5,
                markerfacecolor=SURFACE,
                markeredgecolor=INK_SOFT,
                label="Missing headings",
            ),
        ],
        loc="lower center",
        bbox_to_anchor=(0.5, 1.0),
        ncol=2,
        frameon=False,
        fontsize=8,
        labelcolor=INK_SOFT,
    )
    figure.tight_layout()
    figure.savefig(out, facecolor=SURFACE)
    plt.close(figure)


def dataset(items: list[dict[str, Any]], cap: int, out: Path, plt: Any) -> None:
    rng = random.Random(SEED)
    names = {"A": "Set A, planted facts", "B": "Set B, real sessions"}
    figure, axis = plt.subplots(figsize=(9.6, 2.3), dpi=DPI, facecolor=SURFACE)
    style(axis)
    for at, (key, name) in enumerate(names.items()):
        mine = [
            i["label"]["input_tokens"]
            for i in items
            if i["label"]["paper"]["set"] == key
        ]
        for tokens in mine:
            axis.plot(
                tokens / 1000,
                at + rng.uniform(-0.2, 0.2),
                "o",
                markersize=6,
                color=SERIES[0] if key == "A" else SERIES[1],
                markeredgecolor=SURFACE,
                markeredgewidth=1,
            )
        axis.text(
            2,
            at - 0.36,
            f"{name}: {len(mine)} items, {min(mine):,} to {max(mine):,} tokens",
            fontsize=8,
            color=INK,
        )
    axis.axvline(cap / 1000, color=LIMIT, linewidth=1, linestyle=(0, (4, 3)))
    axis.text(
        cap / 1000 - 1.5,
        1.42,
        f"arena limit {cap:,}",
        ha="right",
        fontsize=7.5,
        color=INK_SOFT,
    )
    axis.set_yticks([])
    axis.set_ylim(1.6, -0.7)
    axis.set_xlim(0, cap / 1000 + 6)
    axis.set_xlabel("Rendered session, thousand tokens", fontsize=8, color=INK_SOFT)
    axis.grid(axis="x", color=RULE, linewidth=0.7)
    figure.tight_layout()
    figure.savefig(out, facecolor=SURFACE)
    plt.close(figure)


def main(argv: list[str] | None = None) -> int:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    parser = argparse.ArgumentParser(prog="comparisons-charts")
    parser.add_argument("--items", default="ctx_compress/exp1/data/items.jsonl")
    parser.add_argument("--out", default="ctx_compress/exp1/results")
    args = parser.parse_args(argv)
    out = Path(args.out)
    analysis = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    table = [row for row in analysis["summary"] if row.get("pass_rate") is not None]
    raw = [
        row
        for row in read_rows(out / "raw.jsonl")
        if row.get("output_tokens") is not None
    ]
    items = read_rows(Path(args.items))
    document = json.loads((out / "comparison.json").read_text(encoding="utf-8"))
    limit = int(document["settings"]["max_output_tokens"])
    folder = out / "charts"
    folder.mkdir(parents=True, exist_ok=True)
    quality(table, folder / "quality.png", plt)
    failures(table, folder / "failures.png", plt)
    lengths(table, raw, limit, folder / "output_length.png", plt)
    dataset(items, 122_880, folder / "dataset.png", plt)
    print("wrote", ", ".join(sorted(p.name for p in folder.glob("*.png"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
