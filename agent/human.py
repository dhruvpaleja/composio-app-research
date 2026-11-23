"""Apply human review decisions (gold/human_overrides.json) on top of data/final -> data/final_human."""
import json, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
src, dst = ROOT / "data" / "final", ROOT / "data" / "final_human"
dst.mkdir(exist_ok=True)
ov = json.loads((ROOT / "gold" / "human_overrides.json").read_text())
for p in src.glob("*.json"):
    r = json.loads(p.read_text())
    o = ov.get(p.stem)
    if o:
        r.update(o["set"])
        r["_open_flags"] = []
        r["_human"] = {"note": o["note"], "src": o["src"], "trigger": o["trigger"]}
    (dst / p.name).write_text(json.dumps(r, indent=1))
print(f"applied {len(ov)} human decisions")
