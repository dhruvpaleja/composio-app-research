"""Consistency test: every number and app list quoted in the hand-written page text must match the data.

    python -m agent.check      # exits non-zero on any mismatch
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rows = json.loads((ROOT / "site" / "results.json").read_text())
acc = json.loads((ROOT / "data" / "accuracy.json").read_text())
P = json.loads((ROOT / "data" / "patterns.json").read_text())
text = " ".join([P["title"], P["lede"]] + [p["head"] + " " + p["body"] for p in P["patterns"]] + P["human"] + P["wrong"])

c = lambda key: Counter(r[key] for r in rows)
names = lambda pred: sorted(r["name"] for r in rows if pred(r))
v, a, b, m = c("verdict"), c("access"), c("blocker"), c("mcp")
auth_any = Counter(x for r in rows for x in r["auth_methods"] or [])
comp = c("composio_status")
ready_no_native = names(lambda r: r["verdict"] == "ready" and r["composio_status"] != "native" and not r.get("identity_risk"))

stats = json.loads((ROOT / "data" / "stats.json").read_text())
gold = {k: g for k, g in json.loads((ROOT / "gold" / "gold.json").read_text()).items() if not k.startswith("_")}
alts = sum(len(g[f]) > 1 for g in gold.values() for f in ("auth_primary", "access", "api_type", "mcp", "verdict", "auth_methods"))
ready = [r for r in rows if r["verdict"] == "ready"]
r1 = lambda x: round(x * 100, 1)
checks = {
    "title: 91 buildable": v["ready"] + v["ready_with_friction"] == 91,
    "61 ready / 30 friction / 6 outreach / 2 no API / 1 unverified": (v["ready"], v["ready_with_friction"], v["needs_outreach"], v["not_buildable"], v["unverified"]) == (61, 30, 6, 2, 1),
    "ready split 56 free + 5 trial": (sum(r["access"] == "self_serve_free" for r in ready), sum(r["access"] == "self_serve_trial" for r in ready)) == (56, 5),
    "outreach list": names(lambda r: r["verdict"] == "needs_outreach") ==
        sorted(["DealCloud", "Gladly", "Salesforce Commerce Cloud", "Waterfall.io", "PitchBook", "Otter AI"]),
    "no hosted API = Sherlock, Mermaid CLI": names(lambda r: r["verdict"] == "not_buildable") == ["Mermaid CLI", "Sherlock"],
    "unverified = Paygent": names(lambda r: r["verdict"] == "unverified") == ["Paygent Connect"],
    "primary OAuth 55 / key 33 / basic 9": (c("auth_primary")["OAUTH2"], c("auth_primary")["API_KEY"], c("auth_primary")["BASIC"]) == (55, 33, 9),
    "both OAuth+key = 58": sum(1 for r in rows if {"OAUTH2", "API_KEY"} <= set(r["auth_methods"])) == 58,
    "not ready = 39": 100 - v["ready"] == 39,
    "blocker paid 15 / review 9 / partnership 8": (b["paid_plan"], b["app_review"], b["partnership"]) == (15, 9, 8),
    "stacked-gate apps are friction": all(next(r for r in rows if r["name"] == n)["verdict"] == "ready_with_friction"
                                          for n in ["Zendesk", "Gorgias", "Copper", "Datadog", "Brex", "Ramp", "Aircall"]),
    "official MCP = 86": m["official"] == 86,
    "composio native 75 / mcp-only 4": (comp["native"], comp["mcp_only"]) == (75, 4),
    "mcp-only list": names(lambda r: r["composio_status"] == "mcp_only") == sorted(["Pylon", "Netlify", "Otter AI", "Devin"]),
    "build queue = 9 named": ready_no_native == sorted(["LiveAgent", "Lark (Larksuite)", "Vonage", "systeme.io", "WooCommerce",
                                                         "fanbasis", "Netlify", "Binance", "Reducto"]),
    "app_review names": set(names(lambda r: r["access"] == "app_review")) >=
        {"Google Ads", "Meta Ads", "LinkedIn Ads", "Pinterest", "Threads (Meta)", "WhatsApp Business"},
    "helpdesk paid names": set(names(lambda r: r["access"] == "paid_plan")) >= {"Help Scout", "Gorgias", "Plain", "Pylon"},
    "Freshdesk is trial": next(r for r in rows if r["name"] == "Freshdesk")["access"] == "self_serve_trial",
    "v1 orig 95.0 -> 92.2": (r1(acc["vs_gold_v1"]["v1_pass1"]["overall"]), r1(acc["vs_gold_v1"]["v1_final"]["overall"])) == (95.0, 92.2),
    "v2 orig 97.8 -> 97.2": (r1(acc["vs_gold_v1"]["pass1"]["overall"]), r1(acc["vs_gold_v1"]["final_human"]["overall"])) == (97.8, 97.2),
    "gold 98.9, quote-backed 95.0 -> 98.9": (r1(acc["pass1"]["overall"]), r1(acc["pass1"]["verified_overall"]), r1(acc["final_human"]["verified_overall"])) == (98.9, 95.0, 98.9),
    "strict 85.0 gold / 86.1 holdout": (r1(acc["strict"]["final_human"]["overall"]), r1(acc["holdout_strict"]["final_human"]["overall"])) == (85.0, 86.1),
    "holdout 98.1 (18 apps)": (r1(acc["holdout"]["final_human"]["overall"]), acc["holdout"]["final_human"]["n_apps"]) == (98.1, 18),
    "gold alternates 56/180": alts == 56,
    "link counts come from linkcheck.json": sum(stats["links"].values()) == len(json.loads((ROOT / "data" / "linkcheck.json").read_text())),
    "757 quotes, 99.6% grounded": (stats["quotes_final"], r1(stats["grounding_final"])) == (757, 99.6),
    "12 fields changed in 9 apps": (sum(stats["field_changes"].values()), stats["apps_changed"]) == (12, 9),
    "final 178/180": (acc["final_human"]["correct"], acc["final_human"]["total"]) == (178, 180),
    "no published evidence on a dead link": not any(e["url"] in {u for u, x in json.loads((ROOT / "data" / "linkcheck.json").read_text()).items() if x["class"] == "DEAD"} for r in rows for e in r["evidence"]),
    "all 100 apps have >=1 grounded quote": all(any((e.get("grounding") or 0) >= 0.6 for e in r["evidence"]) for r in rows),
    "100 unique ids": sorted(r["id"] for r in rows) == list(range(1, 101)),
}
# every "N apps" style number in the text should be explainable: list them for a human glance
nums = sorted(set(int(x) for x in re.findall(r"\b(\d{1,3})\b", text)))
bad = [k for k, ok in checks.items() if not ok]
for k, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + k)
print("numbers quoted in text:", nums)
sys.exit(1 if bad else 0)
