import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PACKAGE = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
CHUNK = 1 << 16

selection = json.loads((PACKAGE / "materials/s4/selection.json").read_text(encoding="utf-8"))
base = f"https://huggingface.co/datasets/{selection['dataset']['repo']}/resolve/main/"
OUT.mkdir(parents=True, exist_ok=True)


def pull(url: str, target: Path) -> None:
    part = target.with_suffix(".part")
    for attempt in range(12):
        have = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": "exp1-fetch"}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=60
            ) as response:
                if have and response.status != 206:
                    part.unlink()
                    have = 0
                with part.open("ab" if have else "wb") as handle:
                    while True:
                        block = response.read(CHUNK)
                        if not block:
                            break
                        handle.write(block)
            part.replace(target)
            return
        except urllib.error.HTTPError as exc:
            if exc.code == 416:
                part.replace(target)
                return
            time.sleep(3 + attempt)
        except (OSError, TimeoutError):
            time.sleep(3 + attempt)
    raise SystemExit(f"could not fetch {url}")


bad = 0
for row in selection["selected"]:
    target = OUT / f"{row['sid']}.jsonl"
    if not target.exists():
        pull(base + urllib.parse.quote(row["file"]), target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    ok = digest == row["sha256"]
    if not ok:
        bad += 1
        target.unlink()
    print(row["sid"], row["licence"], "ok" if ok else f"MISMATCH {digest}", flush=True)
print(f"{len(selection['selected']) - bad} of {len(selection['selected'])} verified")
sys.exit(1 if bad else 0)
