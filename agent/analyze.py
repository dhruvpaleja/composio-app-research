"""Aggregate the final records into the dataset + pattern stats used by the case-study page.

    python -m agent.analyze     -> site/results.json, site/results.csv, data/stats.json
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from . import tools
from .pipeline import grounded, load_apps, vendor_token

ROOT = Path(__file__).resolve().parent.parent
DATA, SITE = ROOT / "data", ROOT / "site"
SITE.mkdir(exist_ok=True)


def final_dir() -> Path:
    return DATA / "final_human" if (DATA / "final_human").exists() else DATA / "final"


def evidence_grounding(rec: dict) -> list[float]:
    out = []
    for ev in rec.get("evidence", []):
        if "grounding" in ev:
            out.append(ev["grounding"])
            continue
        page = tools.fetch_url(ev["url"]) if str(ev.get("url", "")).startswith("http") else {"content": ""}
        out.append(grounded(ev.get("quote", ""), page.get("content", "")))
    return out


MATCHES = {k: v for k, v in json.loads((ROOT / "gold" / "composio_matches.json").read_text()).items()
           if not k.startswith("_")} if (ROOT / "gold" / "composio_matches.json").exists() else {}
LINKS = json.loads((ROOT / "data" / "linkcheck.json").read_text()) if (ROOT / "data" / "linkcheck.json").exists() else {}
LOW_CONF = {"96": "Devin: which plan includes API access is unconfirmed",
            "80": "Harvest: free-plan API access rests on draft evidence",
            "17": "Plain: access label is a best judgement from a third-party page",
            "88": "Brex: needs a Brex business account; sandbox unconfirmed"}


def main():
    n_dead_ev = [0]
    apps = {a["id"]: a for a in load_apps()}
    tools.composio_catalog("_warm_")  # load the catalog
    fd = final_dir()
    overrides = json.loads((ROOT / "gold" / "human_overrides.json").read_text()) \
        if (ROOT / "gold" / "human_overrides.json").exists() else {}
    rows, g1, g2 = [], [], []
    changed_apps = Counter()
    for aid, app in apps.items():
        p1 = json.loads((DATA / "pass1" / f"{aid}.json").read_text())
        fin = json.loads((fd / f"{aid}.json").read_text())
        vlog = json.loads((DATA / "verify" / f"{aid}.json").read_text())
        gp1, gfin = evidence_grounding(p1), evidence_grounding(fin)
        g1 += gp1
        g2 += gfin
        loop = json.loads((DATA / "final" / f"{aid}.json").read_text())  # the loop's own output, before human review
        diffs = {k: [p1.get(k), loop.get(k)] for k in
                 ("auth_methods", "auth_primary", "access", "api_type", "mcp", "verdict", "blocker")
                 if (sorted(p1.get(k)) if k == "auth_methods" else p1.get(k)) !=
                 (sorted(loop.get(k)) if k == "auth_methods" else loop.get(k))}
        for k in diffs:
            changed_apps[k] += 1
        sig = fin.get("_signals") or vlog.get("signals") or {}
        allc = list(sig.get("composio_catalog", []))
        tok = vendor_token(app)
        for t in tools._CATALOG or []:  # prefix match, e.g. GoHighLevel -> highlevel_location
            if len(tok) >= 5 and t["slug"].split("_")[0] == tok and t["slug"] not in {c["slug"] for c in allc}:
                allc.append({"slug": t["slug"], "auth_schemes": t.get("auth_schemes", []),
                             "tools": (t.get("meta") or {}).get("tools_count")})
        if aid in MATCHES:  # hand-reviewed correction of the automatic match
            allc = [{"slug": t["slug"], "auth_schemes": t.get("auth_schemes", []),
                     "tools": (t.get("meta") or {}).get("tools_count")}
                    for t in tools._CATALOG or [] if t["slug"] in MATCHES[aid]]
        allc = [c for c in allc if (c.get("tools") or 0) > 0]  # drop 0-tool stubs (e.g. 'amazon')
        cat = [c for c in allc if not c["slug"].endswith("_mcp")]
        mcp_only = [c for c in allc if c["slug"].endswith("_mcp")]
        comp_status = "native" if cat else ("mcp_only" if mcp_only else "none")
        dead = [e for e in fin.get("evidence", []) if LINKS.get(e.get("url"), {}).get("class") == "DEAD"]
        n_dead_ev[0] += len(dead)
        if LINKS.get(fin.get("mcp_url"), {}).get("class") == "DEAD":
            fin["mcp_url"] = None
        ev = sorted([e for e in fin.get("evidence", []) if e.get("grounding", 0) >= 0.6 and e not in dead],
                    key=lambda e: -e.get("grounding", 0))
        rows.append({
            "id": int(aid), "name": app["name"], "category": app["category"], "hint": app["hint"],
            "one_liner": fin.get("one_liner"),
            "auth_methods": fin.get("auth_methods"), "auth_primary": fin.get("auth_primary"),
            "auth_notes": fin.get("auth_notes"),
            "access": fin.get("access"), "access_notes": fin.get("access_notes"),
            "api_type": fin.get("api_type"), "api_breadth": fin.get("api_breadth"),
            "openapi_spec": fin.get("openapi_spec"), "webhooks": fin.get("webhooks"), "sandbox": fin.get("sandbox"),
            "mcp": fin.get("mcp"), "mcp_url": fin.get("mcp_url"),
            "verdict": fin.get("verdict"), "blocker": fin.get("blocker"), "blocker_notes": fin.get("blocker_notes"),
            "docs_url": fin.get("docs_url"),
            "in_composio": bool(cat), "composio_status": comp_status,
            "composio_slugs": [c["slug"] for c in cat + mcp_only],
            "composio_auth": sorted({a for c in cat for a in c["auth_schemes"]}),
            "evidence": [{"field": e["field"], "url": e["url"], "quote": e["quote"], "grounding": e.get("grounding")}
                         for e in ev[:8]],
            "evidence_ungrounded": sum(1 for e in fin.get("evidence", []) if e.get("grounding", 0) < 0.6),
            "changed_by_verification": diffs,
            "verify_rounds": len(vlog.get("rounds", [])),
            "initial_flags": [f"{f['check']}:{f['field']}" for f in vlog.get("initial_flags", [])],
            "open_flags": [f"{f['check']}:{f['field']}" for f in fin.get("_open_flags", [])],
            "human_override": overrides.get(aid),
            "identity_risk": aid == "84",
            "low_confidence": LOW_CONF.get(aid),
            "confidence": fin.get("confidence"),
        })
    rows.sort(key=lambda r: r["id"])

    # ---------------- patterns
    cats = list(dict.fromkeys(r["category"] for r in rows))
    by = lambda key: Counter(r[key] for r in rows)
    cross = lambda key: {c: Counter(r[key] for r in rows if r["category"] == c) for c in cats}
    auth_any = Counter(a for r in rows for a in (r["auth_methods"] or []))
    stats = {
        "n": len(rows),
        "verdict": by("verdict"), "access": by("access"), "auth_primary": by("auth_primary"),
        "auth_any": auth_any, "mcp": by("mcp"), "blocker": by("blocker"), "api_type": by("api_type"),
        "verdict_by_cat": cross("verdict"), "access_by_cat": cross("access"), "mcp_by_cat": cross("mcp"),
        "auth_by_cat": cross("auth_primary"),
        "oauth_and_key": sum(1 for r in rows if {"OAUTH2", "API_KEY"} <= set(r["auth_methods"] or [])),
        "in_composio": sum(r["in_composio"] for r in rows),
        "not_in_composio": [r["name"] for r in rows if r["composio_status"] == "none"],
        "mcp_only_in_composio": [r["name"] for r in rows if r["composio_status"] == "mcp_only"],
        "composio_status": Counter(r["composio_status"] for r in rows),
        "easy_wins_missing": [r["name"] for r in rows if r["composio_status"] != "native" and r["verdict"] == "ready"],
        "links": {k: sum(1 for v in LINKS.values() if v["class"] == k) for k in ("OK", "BLOCKED", "DEAD")},
        "dead_evidence_dropped": n_dead_ev[0],
        "outreach": [r["name"] for r in rows if r["verdict"] in ("needs_outreach",)],
        "grounding_pass1": round(sum(x >= 0.6 for x in g1) / max(1, len(g1)), 3), "quotes_pass1": len(g1),
        "grounding_final": round(sum(x >= 0.6 for x in g2) / max(1, len(g2)), 3), "quotes_final": len(g2),
        "apps_with_initial_flags": sum(1 for r in rows if [f for f in r["initial_flags"] if not f.startswith("V4")]),
        "apps_changed": sum(1 for r in rows if r["changed_by_verification"]),
        "field_changes": changed_apps,
        "open_flag_apps": [r["name"] for r in rows if r["open_flags"]],
        "flag_checks": Counter(f.split(":")[0] for r in rows for f in r["initial_flags"]),
    }
    (SITE / "results.json").write_text(json.dumps(rows, indent=1))
    (DATA / "stats.json").write_text(json.dumps(stats, indent=1))
    cols = ["id", "name", "category", "one_liner", "auth_primary", "auth_methods", "access", "api_type", "api_breadth",
            "mcp", "verdict", "blocker", "blocker_notes", "in_composio", "docs_url", "evidence_urls"]
    with open(SITE / "results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r["id"], r["name"], r["category"], r["one_liner"], r["auth_primary"],
                        "|".join(r["auth_methods"] or []), r["access"], r["api_type"], r["api_breadth"], r["mcp"],
                        r["verdict"], r["blocker"], r["blocker_notes"], r["in_composio"], r["docs_url"],
                        " ".join(dict.fromkeys(e["url"] for e in r["evidence"]))])
    print(json.dumps({k: v for k, v in stats.items() if not k.endswith("_by_cat")}, indent=1)[:3500])


if __name__ == "__main__":
    main()
