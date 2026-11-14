"""[claude-code/claude-fable-5-2 · op Ali (git: Ali) · Alis-MacBook-Air.local · ali/judges-presentation · 2026-11-14]
Put one real decisions.jsonl row (and optionally today's evaluation numbers) into the deck. No robot imports.

    python3 presentation/set_row.py runs/<run>/decisions.jsonl --item 3
    python3 presentation/set_row.py --eval good_passed=30 good_total=31 defects_flagged=11 defects_total=12 note="held-out picks, all six views"
    python3 presentation/set_row.py --device CPU

Then rebuild: cd presentation && npm run package
"""
import argparse
import json
from pathlib import Path

P = Path(__file__).resolve().parent / "src" / "today.json"
a = argparse.ArgumentParser()
a.add_argument("log", nargs="?")
a.add_argument("--item", type=int)
a.add_argument("--eval", nargs="+", metavar="key=value")
a.add_argument("--device")
a = a.parse_args()
d = json.loads(P.read_text())
if a.log:
    rows = [json.loads(l) for l in Path(a.log).read_text().splitlines() if l.strip()]
    row = next(r for r in rows if a.item is None or r["item"] == a.item) if a.item is not None else rows[-1]
    row["_source"] = f"{a.log} · item {row['item']}"
    d["row"] = row
if a.eval:
    kv = dict(x.split("=", 1) for x in a.eval)
    d["eval"] = {k: (int(v) if v.isdigit() else v) for k, v in kv.items()}
if a.device:
    d["device"] = a.device
P.write_text(json.dumps(d, indent=2) + "\n")
print(json.dumps({k: (v if k != "row" else (v or {}).get("_source")) for k, v in d.items() if k != "_comment"}))
