from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/lt")


def main() -> int:
    contestant, source, count = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
    sessions = {}
    with (ROOT / "sessions.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            sessions[row["item_id"]] = row
    items = ROOT / "items.jsonl"
    known = set()
    if items.is_file():
        known = {json.loads(line)["item_id"] for line in items.open(encoding="utf-8")}
    picked = []
    seen = set()
    for line in source.open(encoding="utf-8"):
        row = json.loads(line)
        if row.get("error") or row.get("status") != 200 or row["item_id"] in seen or not row.get("text"):
            continue
        seen.add(row["item_id"])
        picked.append(row)
        if len(picked) >= count:
            break
    with items.open("a", encoding="utf-8") as handle:
        for row in picked:
            if row["item_id"] in known:
                continue
            session = sessions[row["item_id"]]
            handle.write(
                json.dumps(
                    {
                        "item_id": row["item_id"],
                        "task": {"system": session["system"], "user": session["user"]},
                        "label": {
                            "input_tokens": session["input_tokens"],
                            "budget_tokens": session["budget_tokens"],
                            "facts": session["facts"],
                            "probes": session["probes"],
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    out = ROOT / "work" / "outputs" / f"{contestant}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in picked:
            handle.write(json.dumps({"item_id": row["item_id"], "text": row["text"]}, ensure_ascii=False) + "\n")
    print(f"{contestant}: {len(picked)} outputs staged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
