from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MAX_SUMMARY_TOKENS = 3072
FLOOR_TOKENS = 3072
FACT_ANSWER_TOKENS = 200
REPLY_TOKENS = 1500
JUDGE_TOKENS = 300
JUDGE_VOTES = 1
SECOND_JUDGE_SHARE = 0.25
SEED = 20261106

SUMMARISERS = {
    "M1": {"label": "UID 2 model", "runs_on": "4090"},
    "M2": {"label": "UID 13 model", "runs_on": "4090"},
    "M3": {"label": "UID 14 model", "runs_on": "4090"},
    "B0": {"label": "Granite 4.0 H Micro base", "runs_on": "4090"},
    "F1": {
        "label": "Qwen 3.8 27B",
        "runs_on": "rented GPU",
        "model": "qwen-3-8-27b",
    },
    "F2": {
        "label": "Gemma 4 31B",
        "runs_on": "rented GPU",
        "model": "gemma-4-31b",
    },
    "P1": {
        "label": "Qwen 3.8 27B, Pi prompt",
        "runs_on": "rented GPU",
        "model": "qwen-3-8-27b",
        "prompt": "pi",
    },
}
REFERENCES = {
    "C1": {"label": "Ceiling: full cut"},
    "C0": {"label": "Floor: last 3,072 tokens"},
}
CONTESTANTS = [*SUMMARISERS, *REFERENCES]
READER = "qwen-3-8-27b"
JUDGE = "gemma-4-31b"
SECOND_JUDGE = "qwen-3-8-27b"
OPEN_MODELS = {
    "qwen-3-8-27b": "unsloth/Qwen3.8-27B-GGUF:UD-Q6_K_XL",
    "gemma-4-31b": "unsloth/gemma-4-31B-it-GGUF:UD-Q5_K_XL",
}
LIST_PRICES = {
    "claude-haiku-5-5": {
        "provider_model": "anthropic/claude-haiku-5.5",
        "in": 0.10,
        "out": 0.50,
    },
    "glm-5-3-flash": {"provider_model": "z-ai/glm-5.3-flash", "in": 0.15, "out": 0.50},
    "claude-sonnet-5-5": {
        "provider_model": "anthropic/claude-sonnet-5.5",
        "in": 2.0,
        "out": 10.0,
    },
    "claude-opus-5-5": {
        "provider_model": "anthropic/claude-opus-5.5",
        "in": 4.0,
        "out": 20.0,
    },
}
LIST_PRICE_IN_PER_MTOK = 0.01
LIST_PRICE_OUT_PER_MTOK = 0.0

READER_SYSTEM = (
    "You are the coding agent in the session recorded below. That record is all that is left of "
    "the session: you cannot see the earlier messages, run commands, read files or use tools. "
    "Reply to the user's message from the record alone."
)
READER_USER = "<context>\n{context}\n</context>\n\n{message}"
JUDGE_INSTRUCTION = (
    'Score this one item. Reply with ONLY a JSON object: {"pass": true|false, "confident": '
    'true|false|null, "note": "one short abstract reason"}. confident is null when pass is true.'
    "\n\nITEM:\n"
)
MEMORY_NOTE = (
    "(In this reply you have no shell, file or repository access: you cannot run commands or "
    "read files. Answer from what you know of this conversation; if you have a tool for "
    "searching the conversation's history, you may use it. Do not try to verify the working tree.)"
)
PI_USER = "<conversation>\n{conversation}\n</conversation>\n\n{prompt}"


def load_items(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _literal(source: str, name: str) -> str:
    found = re.search(r"const " + re.escape(name) + r" = `(.*?)`;", source, re.DOTALL)
    if found is None:
        raise ValueError(f"{name} is not in the Pi package")
    return found.group(1)


def pi_prompts(package: Path) -> dict[str, str]:
    folder = package / "dist" / "core" / "compaction"
    return {
        "system": _literal(
            (folder / "utils.js").read_text(encoding="utf-8"),
            "SUMMARIZATION_SYSTEM_PROMPT",
        ),
        "prompt": _literal(
            (folder / "compaction.js").read_text(encoding="utf-8"),
            "SUMMARIZATION_PROMPT",
        ),
    }


def summary_messages(
    contestant: str, item: dict[str, Any], pi: dict[str, str]
) -> list[dict[str, str]]:
    task = item["task"]
    if SUMMARISERS[contestant].get("prompt") == "pi":
        return [
            {"role": "system", "content": pi["system"]},
            {
                "role": "user",
                "content": PI_USER.format(
                    conversation=task["user"], prompt=pi["prompt"]
                ),
            },
        ]
    return [
        {"role": "system", "content": task["system"]},
        {"role": "user", "content": task["user"]},
    ]


def reader_messages(context: str, message: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": READER_SYSTEM},
        {
            "role": "user",
            "content": READER_USER.format(context=context, message=message),
        },
    ]


def fact_message(template: str, question: str) -> str:
    return template.replace("{questions}", f"Q1: {question}")


def commitment_message(probe: dict[str, Any]) -> str:
    return probe["instruction"].rstrip() + "\n\n" + MEMORY_NOTE


def judge_messages(
    brief: str, probe: dict[str, Any], reply: str
) -> list[dict[str, str]]:
    item = {
        "dependency": probe["dependency"],
        "dependency_key_strings": probe["keys"],
        "instruction": probe["instruction"],
        "criterion": probe["criterion"],
        "reply": reply,
    }
    return [
        {"role": "system", "content": brief},
        {
            "role": "user",
            "content": JUDGE_INSTRUCTION + json.dumps(item, ensure_ascii=False),
        },
    ]
