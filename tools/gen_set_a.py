import json
import sys
from pathlib import Path

PACKAGE = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(PACKAGE / "harness" / "src"))

from ceval import pisession  # noqa: E402
from ceval.stories import build_story_plan  # noqa: E402

PROVIDER = "llama.cpp"
MODEL = "unsloth/Qwen3.8-27B-GGUF:UD-Q6_K_XL"
THINKING = "xhigh"
SESSION_VERSION = 3
PHASES = ("plant", "round1")

scenario = json.loads((PACKAGE / "materials/scenarios/s1.json").read_text(encoding="utf-8"))
OUT.mkdir(parents=True, exist_ok=True)
manifest = []
for index in range(scenario["n_sessions"]):
    plan = build_story_plan(scenario, index, keep_recent_tokens=20000, chars_per_token=3.6)
    target = OUT / f"{plan.session_id}.jsonl"
    if target.exists():
        target.unlink()
    fact_entries = {}
    for name in PHASES:
        at = next(i for i, phase in enumerate(plan.phases) if phase["name"] == name)
        writer = pisession.SessionWriter(
            target,
            cwd=f"/work/{plan.session_id}",
            version=SESSION_VERSION,
            provider=PROVIDER,
            model=MODEL,
            seed=plan.seed * 100 + at,
            thinking_level=THINKING,
        )
        for step in plan.phases[at]["steps"]:
            ids = writer.step(step)
            if step.get("fact_uid"):
                fact_entries.setdefault(step["fact_uid"], []).extend(ids)
    facts = []
    for uid in plan.probe_order:
        fact = next(f for f in plan.facts if f.uid == uid)
        row = fact.to_dict()
        row["entry_ids"] = fact_entries.get(uid, [])
        row["is_lure"] = fact.is_lure
        facts.append(row)
    plan_file = OUT / f"{plan.session_id}.plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "session_id": plan.session_id,
                "seed": plan.seed,
                "story": plan.meta["story"],
                "skeleton": plan.meta["skeleton"],
                "build_attempt": plan.meta["build_attempt"],
                "phases_written": list(PHASES),
                "facts": facts,
                "positions": plan.meta["positions"],
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    entries = pisession.read_entries(target)
    planted = [f for f in facts if not f["is_lure"]]
    manifest.append(
        {
            "session_id": plan.session_id,
            "story": plan.meta["story"],
            "entries": len(entries),
            "bytes": target.stat().st_size,
            "facts": len(planted),
            "lures": len(facts) - len(planted),
            "sources": sorted({f["source"] for f in planted}),
            "round0": sum(1 for f in planted if f["round_planted"] == 0),
            "attempt": plan.meta["build_attempt"],
        }
    )
    print(json.dumps(manifest[-1]))
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
