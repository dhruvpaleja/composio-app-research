"""Score agent output against the hand-checked gold sample.

    python -m agent.score            # pass1 vs final, per field, writes data/accuracy.json
"""
import json
from pathlib import Path

from .schema import SCORED_FIELDS
from . import tools

EV_FIELD = {"auth_primary": "auth", "auth_methods": "auth", "access": "access", "api_type": "api", "mcp": "mcp",
            "verdict": "access"}


def best_grounding(rec: dict, ev_field: str) -> float:
    from .pipeline import grounded
    best = 0.0
    for ev in rec.get("evidence", []):
        if ev.get("field", "").split(".")[0] != ev_field:
            continue
        g = ev.get("grounding")
        if g is None:
            page = tools.fetch_url(ev["url"]) if str(ev.get("url", "")).startswith("http") else {"content": ""}
            g = grounded(ev.get("quote", ""), page.get("content", ""))
        best = max(best, g)
    return best

ROOT = Path(__file__).resolve().parent.parent
GOLD = json.loads((ROOT / "gold" / "gold.json").read_text())


STRICT = False  # strict = only the first (preferred) gold answer counts, no alternates


def field_ok(field: str, rec: dict, g: dict) -> bool:
    if field == "auth_methods":
        got = set(rec.get("auth_methods") or [])
        for acc in (g["auth_methods"][:1] if STRICT else g["auth_methods"]):
            acc = set(acc)
            if got == acc or (got - {"OTHER"}) == acc:  # an extra OTHER is tolerated
                return True
        return False
    return rec.get(field) in (g[field][:1] if STRICT else g[field])


def score(stage_dir: str) -> dict:
    rows, per_field = [], {f: [0, 0] for f in SCORED_FIELDS}
    verified = {f: 0 for f in SCORED_FIELDS}
    for gid, g in GOLD.items():
        if gid.startswith("_"):
            continue
        p = ROOT / "data" / stage_dir / f"{gid}.json"
        if not p.exists():
            continue
        rec = json.loads(p.read_text())
        res = {}
        for f in SCORED_FIELDS:
            ok = field_ok(f, rec, g)
            gr = best_grounding(rec, EV_FIELD[f])
            verified[f] += ok and gr >= 0.6
            res[f] = {"ok": ok, "grounded": round(gr, 2), "got": rec.get(f), "gold": g[f] if f != "auth_methods" else g[f][0]}
            per_field[f][0] += ok
            per_field[f][1] += 1
        rows.append({"id": int(gid), "name": g["name"], "fields": res, "src": g["src"]})
    tot_ok = sum(v[0] for v in per_field.values())
    tot = sum(v[1] for v in per_field.values())
    apps_perfect = sum(all(x["ok"] for x in r["fields"].values()) for r in rows)
    return {"n_apps": len(rows), "field_accuracy": {f: round(a / n, 3) if n else None for f, (a, n) in per_field.items()},
            "overall": round(tot_ok / tot, 3) if tot else None, "correct": tot_ok, "total": tot,
            "apps_all_correct": apps_perfect,
            "verified_overall": round(sum(verified.values()) / tot, 3) if tot else None,
            "verified_field": {f: round(verified[f] / per_field[f][1], 3) if per_field[f][1] else None for f in SCORED_FIELDS}, "rows": sorted(rows, key=lambda r: r["id"])}


if __name__ == "__main__":
    out = {"pass1": score("pass1"), "final": score("final")}
    for k, d in (("v1_pass1", "history/pass1_v1"), ("v1_final", "history/final_v1")):
        if (ROOT / "data" / d).exists():
            out[k] = score(d)
    if (ROOT / "data" / "final_human").exists():
        out["final_human"] = score("final_human")
    # the same stages scored against my original, uncorrected hand labels (gold_v1.json)
    adjudicated, GOLD = GOLD, json.loads((ROOT / "gold" / "gold_v1.json").read_text())
    stages = {"v1_pass1": "history/pass1_v1", "v1_final": "history/final_v1", "pass1": "pass1", "final": "final",
              "final_human": "final_human"}
    out["vs_gold_v1"] = {k: {kk: v[kk] for kk in ("overall", "verified_overall", "correct", "total", "apps_all_correct")}
                         for k, v in ((k, score(d)) for k, d in stages.items() if (ROOT / "data" / d).exists())}
    GOLD = adjudicated
    # strict scoring (first-choice gold value only) and the independent held-out sample
    STRICT = True
    out["strict"] = {k: {kk: v[kk] for kk in ("overall", "correct", "total")}
                     for k, v in ((k, score(d)) for k, d in stages.items() if (ROOT / "data" / d).exists())}
    STRICT = False
    if (ROOT / "gold" / "holdout.json").exists():
        GOLD = json.loads((ROOT / "gold" / "holdout.json").read_text())
        out["holdout"] = {k: score(d) for k, d in (("pass1", "pass1"), ("final_human", "final_human"))}
        STRICT = True
        out["holdout_strict"] = {k: {kk: v[kk] for kk in ("overall", "correct", "total")}
                                 for k, v in ((k, score(d)) for k, d in (("pass1", "pass1"), ("final_human", "final_human")))}
        STRICT = False
        GOLD = adjudicated
    (ROOT / "data" / "accuracy.json").write_text(json.dumps(out, indent=1))
    for k, v in out.items():
        if k in ("vs_gold_v1", "strict", "holdout", "holdout_strict"):
            continue
        print(f"{k:12s} overall={v['overall']} ({v['correct']}/{v['total']})  verified={v['verified_overall']}  apps fully right={v['apps_all_correct']}/{v['n_apps']}")
        print("             ", v["field_accuracy"])
