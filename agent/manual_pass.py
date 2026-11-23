"""Cross-check the agent against an independent manual research pass over the same 100 apps.

The manual pass is a separate document (site/manual-pass.pdf, compiled 23 Nov 2026). Its table was
extracted once into data/manual_pass_rows.json (one row per app, same order and ids as apps.csv).
This script normalises its free-text cells onto the agent's schema and records, per app and field,
whether the two passes agree. Nothing here changes the agent's own answers.

    python -m agent.manual_pass      # writes data/manual_pass.json and site/manual_pass.json
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, SITE = ROOT / "data", ROOT / "site"

# The PDF's own headline numbers, quoted from its text (used to check the extraction).
PDF_HEADLINE = {"free_no_approval": 69, "paid": 10, "gated": 13, "mcp_official": 41}


def norm_access(text, verdict=""):
    t, v = text.lower(), verdict.lower()
    if "local" in v or "no api" in v:
        return "no_api"
    if "gated by plan" in t or re.search(r"\bpaid\b|lite and above|from \$", t):
        return "paid"
    if t.startswith("gated") or "gated:" in t:
        return "gated"
    if re.search(r"review|approval|verification|access level|trial access", t):
        return "review"
    return "self_serve"


def norm_mcp(text):
    t = text.lower()
    if "community mcp" in t:
        return "community"
    if re.search(r"no (official )?mcp", t):
        return "none"
    if "mcp" in t:
        return "official"
    return "unstated"  # the cell describes the API but says nothing about MCP


def norm_verdict(text, access):
    v = text.lower()
    if "outreach" in v or access == "gated":
        return "outreach"
    if access == "no_api":
        return "not_buildable"
    if access in ("paid", "review") or re.search(r"paid|trial|review", v):
        return "friction"
    return "ready"


def norm_auth(text):
    t = text.lower()
    fam = set()
    if "oauth" in t:
        fam.add("OAUTH2")
    if re.search(r"api key|token|bearer|\bpat\b|key id|x-api-key|apikey|\bkey\b", t):
        fam.add("API_KEY")
    if "basic" in t:
        fam.add("BASIC")
    if re.search(r"sign|hmac|jwt", t):
        fam.add("OTHER")
    if t.startswith("none"):
        fam.add("NONE")
    return fam


AGENT_ACCESS = {"self_serve_free": "self_serve", "self_serve_trial": "self_serve", "paid_plan": "paid",
                "app_review": "review", "partner_gated": "gated", "no_public_api": "no_api"}
AGENT_VERDICT = {"ready": "ready", "ready_with_friction": "friction", "needs_outreach": "outreach",
                 "not_buildable": "not_buildable", "unverified": "outreach"}


def run():
    manual = json.loads((DATA / "manual_pass_rows.json").read_text(encoding="utf-8"))
    agent = {r["id"]: r for r in json.loads((SITE / "results.json").read_text(encoding="utf-8"))}
    # Compare against the agent's answers *before* the vendor-docs re-check was applied, so fields the
    # manual pass got right still count as its wins (gold/recheck_overrides.json records the old values).
    rc_file = ROOT / "gold" / "recheck_overrides.json"
    was = {int(k): v.get("was", {}) for k, v in json.loads(rc_file.read_text(encoding="utf-8")).items()} if rc_file.exists() else {}
    agent = {i: {**r, **was.get(i, {})} for i, r in agent.items()}
    out, agree, n = [], Counter(), Counter()
    for m in manual:
        a = agent[m["id"]]
        acc = norm_access(m["access"], m["verdict"])
        mn = {"access": acc, "mcp": norm_mcp(m["api_mcp"]), "verdict": norm_verdict(m["verdict"], acc),
              "auth": sorted(norm_auth(m["auth"]))}
        an = {"access": AGENT_ACCESS[a["access"]], "mcp": a["mcp"], "verdict": AGENT_VERDICT[a["verdict"]],
              "auth": a["auth_primary"]}
        same = {"verdict": mn["verdict"] == an["verdict"], "access": mn["access"] == an["access"],
                "mcp": None if mn["mcp"] == "unstated" else mn["mcp"] == an["mcp"],
                "auth": (a["auth_primary"] in mn["auth"]) if mn["auth"] else None}
        for k, v in same.items():
            if v is not None:
                agree[k] += v
                n[k] += 1
        url = m["evidence"].split()[0] if m["evidence"] else ""
        out.append({"id": m["id"], "name": a["name"], "manual": m, "manual_norm": mn, "agent_norm": an, "agree": same,
                    "manual_url": ("https://" + url) if url and not url.startswith("http") else url})
    counts = {"access": Counter(o["manual_norm"]["access"] for o in out),
              "mcp": Counter(o["manual_norm"]["mcp"] for o in out),
              "verdict": Counter(o["manual_norm"]["verdict"] for o in out)}
    extracted = {"free_no_approval": counts["access"]["self_serve"], "paid": counts["access"]["paid"],
                 "gated": counts["access"]["gated"], "mcp_official": counts["mcp"]["official"]}
    summary = {"agree": dict(agree), "n": dict(n), "counts": {k: dict(v) for k, v in counts.items()},
               "pdf_headline": PDF_HEADLINE, "extraction_matches_pdf": extracted == PDF_HEADLINE,
               "agent_mcp_official": sum(r["mcp"] == "official" for r in agent.values())}
    # Adjudication: every disputed field was re-checked against the vendor's live docs (data/adjudication.json).
    adj_file = DATA / "adjudication.json"
    if adj_file.exists():
        adj = {a["id"]: a["fields"] for a in json.loads(adj_file.read_text(encoding="utf-8"))}
        wins = {f: Counter() for f in ("verdict", "access", "mcp")}
        best = {f: Counter() for f in ("verdict", "access", "mcp")}
        for o in out:
            a = agent[o["id"]]
            o["adjudication"] = {}
            for f in ("verdict", "access", "mcp"):
                ruling = adj.get(o["id"], {}).get(f)
                if o["agree"][f] is False and ruling:
                    o["adjudication"][f] = ruling
                    wins[f][ruling["winner"]] += 1
                    label = ruling["correct"] if ruling["winner"] != "unclear" else a[f]
                else:
                    label = a[f]
                best[f][label] += 1
        summary["adjudication"] = {"wins": {f: dict(c) for f, c in wins.items()},
                                   "best_estimate": {f: dict(c) for f, c in best.items()},
                                   "agent": {f: dict(Counter(r[f] for r in agent.values())) for f in ("verdict", "access", "mcp")}}
    doc = {"summary": summary, "apps": out}
    for path in (DATA / "manual_pass.json", SITE / "manual_pass.json"):
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"agreement: " + ", ".join(f"{k} {agree[k]}/{n[k]}" for k in ("verdict", "access", "auth", "mcp")))
    print("extraction matches the PDF's own totals:", summary["extraction_matches_pdf"], extracted)


if __name__ == "__main__":
    run()
