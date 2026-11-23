"""Apply human review decisions on top of data/final -> data/final_human.

Two override files, applied in order:
  gold/human_overrides.json    decisions on apps the agent's own loop left flagged (the human queue)
  gold/recheck_overrides.json  fields where an independent manual pass disagreed with the agent and a
                               re-check against the vendor's live docs found the agent wrong
                               (rulings with source URL and quote: data/adjudication.json)
"""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
src, dst = ROOT / "data" / "final", ROOT / "data" / "final_human"
dst.mkdir(exist_ok=True)
read = lambda p: json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
ov = read(ROOT / "gold" / "human_overrides.json")
rc = read(ROOT / "gold" / "recheck_overrides.json")
for p in src.glob("*.json"):
    r = json.loads(p.read_text(encoding="utf-8"))
    o = ov.get(p.stem)
    if o:
        r.update(o["set"])
        r["_open_flags"] = []
        r["_human"] = {"note": o["note"], "src": o["src"], "trigger": o["trigger"]}
    c = rc.get(p.stem)
    if c:
        r.update(c["set"])
        r["_recheck"] = {"note": c["note"], "src": c["src"], "trigger": c["trigger"]}
    (dst / p.name).write_text(json.dumps(r, indent=1), encoding="utf-8")
print(f"applied {len(ov)} human decisions and {len(rc)} vendor-docs re-checks")
