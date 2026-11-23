"""App-research agent: pass 1 (research) -> verification loop -> human queue.

    python -m agent.pipeline pass1  --ids 1-100 --workers 8
    python -m agent.pipeline verify --ids 1-100 --workers 6
    python -m agent.pipeline all    --ids 1-100

Pass 1  : 3 Composio web searches per app, Claude extracts a structured record with a quote per claim.
Verify  : V1 citation grounding  - every quote is re-fetched from its URL and must actually be on the page.
          V2 cross-source check  - auth vs Composio's own toolkit catalog; MCP vs the official MCP Registry.
          V3 consistency rules   - e.g. verdict 'ready' with a partner gate, missing evidence, low confidence.
          V4 targeted re-research- flagged fields get vendor-docs fetches + a skeptical auditor model that may
                                   only answer with verbatim quotes. Re-checked by V1-V3, max 2 rounds.
Human   : whatever is still flagged after 2 rounds goes to data/human_queue.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

from . import tools
from .schema import RECORD_SCHEMA, RUBRIC

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
for d in ("pass1", "final", "verify", "evidence"):
    (DATA / d).mkdir(parents=True, exist_ok=True)


def load_apps() -> list[dict]:
    return list(csv.DictReader(open(DATA / "apps.csv")))


def vendor_token(app: dict) -> str:
    """'hubspot.com' -> 'hubspot'; 'developers.facebook.com/docs/threads' -> 'facebook'."""
    host = app["hint"].split()[0].split("/")[0]
    parts = [p for p in host.split(".") if p not in ("www", "developer", "developers", "docs", "api", "api-docs",
                                                         "help", "open", "learn", "core", "com", "io", "ai", "dev",
                                                         "app", "co", "org", "net", "github", "video", "readme")]
    return (parts[0] if parts else re.sub(r"[^a-z0-9]", "", app["name"].lower())).lower()


# ====================================================================== PASS 1
SYS_RESEARCHER = ("You are an API research analyst at Composio. You decide whether an app can become an "
                  "agent toolkit. Be precise, use only the evidence given, and copy quotes verbatim.")


def _snips(results: list[dict], n: int = 6) -> str:
    return "\n\n".join(f"[{r['url']}]\n{r['snippet'][:1500]}" for r in results[:n])


def pass1(app: dict) -> dict:
    name = app["name"]
    searches = {
        "auth": tools.web_search(f"{name} API authentication developer documentation"),
        "access": tools.web_search(f"{name} API access requirements free developer account pricing partner"),
        "mcp": tools.web_search(f"{name} MCP server model context protocol"),
    }
    (DATA / "evidence" / f"{app['id']}_pass1.json").write_text(json.dumps(searches, indent=1))
    prompt = f"""App #{app['id']}: {name}  (category: {app['category']}; hint: {app['hint']})
{RUBRIC}
EVIDENCE (web search results, each prefixed by its URL):
--- auth searches ---
{_snips(searches['auth'])}
--- access / pricing searches ---
{_snips(searches['access'])}
--- MCP searches ---
{_snips(searches['mcp'])}

Produce the research record. For every claim put an evidence item {{field, url, quote}} where quote is copied
verbatim (8-40 words) from the snippet of that url. Fields for evidence: auth, access, api, mcp.
If evidence is missing, use your best judgement and set that confidence to low."""
    rec = tools.llm_json(SYS_RESEARCHER, prompt, RECORD_SCHEMA)
    rec["_pass"] = 1
    (DATA / "pass1" / f"{app['id']}.json").write_text(json.dumps(rec, indent=1))
    return rec


# ====================================================================== VERIFY
def _norm_txt(s: str) -> list[str]:
    s = re.sub(r"[`*_#>\[\]()|\\]", " ", s.lower())
    return re.findall(r"[a-z0-9]+", s)


def grounded(quote: str, page: str) -> float:
    """Share of the quote's word 3-grams that appear on the page (1.0 = verbatim)."""
    q, p = _norm_txt(quote), _norm_txt(page)
    if len(q) < 3:
        return 0.0
    qg = {tuple(q[i:i + 3]) for i in range(len(q) - 2)}
    pg = {tuple(p[i:i + 3]) for i in range(len(p) - 2)}
    return len(qg & pg) / len(qg)


CAT_MAP = {"OAUTH2": "OAUTH2", "DCR_OAUTH": "OAUTH2", "OAUTH1": "OAUTH2", "S2S_OAUTH2": "OAUTH2",
           "API_KEY": "API_KEY", "BEARER_TOKEN": "API_KEY", "BASIC": "BASIC", "BASIC_WITH_JWT": "BASIC",
           "NO_AUTH": "NONE"}


def check(app: dict, rec: dict, initial: bool = True) -> tuple[list[dict], dict]:
    """Run V1-V3. Returns (flags, signals)."""
    flags, signals = [], {}
    # ---- V1 citation grounding (re-fetch each cited page)
    by_field: dict[str, list] = {}
    for ev in rec.get("evidence", []):
        f = ev.get("field", "?").split(".")[0]
        page = tools.fetch_url(ev["url"]) if ev.get("url", "").startswith("http") else {"content": ""}
        score = grounded(ev.get("quote", ""), page.get("content", ""))
        ev["grounding"] = round(score, 2)
        ev["fetched_via"] = page.get("via")
        by_field.setdefault(f, []).append(score)
    for f in ("auth", "access", "api", "mcp"):
        best = max(by_field.get(f, [0.0]))
        if best < 0.6:
            flags.append({"check": "V1_grounding", "field": f,
                          "why": "no evidence" if f not in by_field else f"best quote only {best:.0%} found on cited page"})
    # ---- V2 cross-source: Composio catalog (auth) + MCP registry (mcp)
    cat = tools.composio_catalog(app["name"], [vendor_token(app), app["name"].split(" (")[0]])
    signals["composio_catalog"] = cat
    core = [c for c in cat if not c["slug"].endswith("_mcp")]
    cat_auth = {CAT_MAP.get(a, "OTHER") for c in core for a in c["auth_schemes"]}
    signals["catalog_auth"] = sorted(cat_auth)
    if cat_auth:
        missing = cat_auth - set(rec.get("auth_methods", [])) - {"OTHER"}
        if missing:
            flags.append({"check": "V2_catalog", "field": "auth",
                          "why": f"Composio catalog lists {sorted(cat_auth)}; agent missed {sorted(missing)}"})
    tok = vendor_token(app)
    reg = tools.mcp_registry(app["name"].split(" (")[0])
    official = [s for s in reg if tok and tok in re.split(r"[./_-]", s["name"].split("/")[0].lower())]
    signals["mcp_registry_official"] = [s["name"] for s in official][:5]
    signals["mcp_registry_any"] = len(reg)
    cat_mcp = [c["slug"] for c in cat if c["slug"].endswith("_mcp")]
    signals["composio_mcp_toolkits"] = cat_mcp
    if (official or cat_mcp) and rec.get("mcp") != "official":
        flags.append({"check": "V2_mcp_registry", "field": "mcp",
                      "why": f"registry/catalog suggests vendor MCP ({(signals['mcp_registry_official'] + cat_mcp)[:3]}) but agent said {rec.get('mcp')}"})
    if rec.get("mcp") == "none" and reg:
        flags.append({"check": "V2_mcp_registry", "field": "mcp",
                      "why": f"agent said none, registry returns {len(reg)} servers matching name"})
    # ---- V3 consistency rules
    v, a = rec.get("verdict"), rec.get("access")
    if v == "ready" and a in ("partner_gated", "paid_plan", "app_review", "no_public_api"):
        flags.append({"check": "V3_rules", "field": "verdict", "why": f"verdict ready but access={a}"})
    if v == "needs_outreach" and a in ("self_serve_free",):
        flags.append({"check": "V3_rules", "field": "verdict", "why": "needs_outreach but self-serve free"})
    if a == "no_public_api" and rec.get("api_type") not in ("none", "SDK_or_CLI_only"):
        flags.append({"check": "V3_rules", "field": "access", "why": "no_public_api but api_type set"})
    if rec.get("auth_primary") not in rec.get("auth_methods", []):
        flags.append({"check": "V3_rules", "field": "auth", "why": "auth_primary not in auth_methods"})
    for k, c in (rec.get("confidence") or {}).items():
        if c == "low" and initial:
            flags.append({"check": "V3_rules", "field": k, "why": "agent self-reported low confidence"})
    # de-dupe by field
    seen, out = set(), []
    for fl in flags:
        key = (fl["field"], fl["check"])
        if key not in seen:
            seen.add(key)
            out.append(fl)
    return out, signals


KEYWORDS = r"(oauth|api key|api token|access token|personal access|authenticat|authoriz|bearer|basic auth|" \
           r"pricing|plan|enterprise|partner|approval|review|trial|free|sandbox|contact sales|" \
           r"mcp|model context|graphql|rest api|endpoint|webhook|openapi)"


def passages(text: str, budget: int = 5000) -> str:
    """Keep the parts of a page that matter for the rubric (keyword windows)."""
    if len(text) <= budget:
        return text
    spans = []
    for m in re.finditer(KEYWORDS, text, re.I):
        s, e = max(0, m.start() - 350), min(len(text), m.end() + 450)
        if spans and s <= spans[-1][1]:
            spans[-1][1] = e
        else:
            spans.append([s, e])
    out, total = [], 0
    for s, e in spans:
        if total > budget:
            break
        out.append(text[s:e])
        total += e - s
    return " … ".join(out) or text[:budget]


def deep_evidence(app: dict, rec: dict, flags: list[dict], round_: int) -> list[dict]:
    """V4: targeted re-research for flagged fields. Prefers the vendor's own domains."""
    name, tok = app["name"], vendor_token(app)
    fields = {f["field"] for f in flags}
    queries = []
    if "auth" in fields:
        queries.append(f"{name} API authentication OAuth API key token")
    if fields & {"access", "verdict"}:
        queries += [f"{name} API access plan required partner program", f"{name} developer API pricing free tier"]
    if "api" in fields:
        queries.append(f"{name} REST API reference endpoints")
    if "mcp" in fields:
        queries.append(f"{name} official MCP server")
    if round_ > 1:
        queries = [q + " site docs" for q in queries]
    urls = []
    if "mcp" in fields:
        sig = tools.mcp_registry(name.split(" (")[0])
        urls += [s["repo"] for s in sig if s.get("repo") and tok in re.split(r"[./_-]", s["name"].split("/")[0].lower())][:2]
        for r in tools.web_search(f"{name} MCP server", max_results=8):
            if tok in (urlparse(r["url"] or "").netloc.lower()):
                urls.append(r["url"])
    hint = app["hint"].split()[0]
    if "." in hint:
        urls.append("https://" + hint)
    if rec.get("docs_url"):
        urls.append(rec["docs_url"])
    for q in queries:
        for r in tools.web_search(q, max_results=6):
            host = urlparse(r["url"] or "").netloc.lower()
            if tok in host or tok in (r["url"] or "").lower():  # vendor-owned pages first
                urls.append(r["url"])
        for r in tools.web_search(q, max_results=3):
            urls.append(r["url"])
    pages, seen = [], set()
    for u in urls:
        if not u or u in seen or len(pages) >= 9:
            continue
        seen.add(u)
        p = tools.fetch_url(u)
        if len(p.get("content", "")) > 300:
            pages.append({"url": u, "text": passages(p["content"])})
    return pages


SYS_AUDITOR = ("You are a skeptical verification auditor. A junior agent produced a research record and automated "
               "checks flagged problems. You may ONLY rely on the page text given to you. Every corrected claim must "
               "be backed by a quote copied character-for-character from one of the pages. Absence is not evidence: "
               "if the pages say nothing about a field, KEEP the draft value (and its draft evidence) and lower its "
               "confidence. Change a value only when a page shows the draft is wrong. Never set mcp to 'none' unless "
               "you saw the vendor's own docs and they offer no MCP server.")


def audit(app: dict, rec: dict, flags: list[dict], signals: dict, pages: list[dict]) -> dict:
    page_txt = "\n\n".join(f"=== PAGE {p['url']} ===\n{p['text']}" for p in pages)
    draft = {k: v for k, v in rec.items() if not k.startswith("_")}
    prompt = f"""App #{app['id']}: {app['name']} (category: {app['category']}; hint: {app['hint']})
{RUBRIC}
DRAFT RECORD:
{json.dumps(draft, indent=1)[:6000]}

AUTOMATED FLAGS:
{json.dumps(flags, indent=1)}

INDEPENDENT SIGNALS (not proof, but hints):
- Composio's toolkit catalog for this app: {json.dumps(signals.get('composio_catalog'))}
- MCP Registry servers published under the vendor's namespace: {signals.get('mcp_registry_official')}

FETCHED PAGES:
{page_txt[:32000]}

Return the full corrected record. Re-check every flagged field against the pages. Any changed or newly
supported claim needs an evidence quote copied verbatim from the PAGES above, naming the page url it came from.
For fields you leave unchanged you may keep the draft's evidence items."""
    new = tools.llm_json(SYS_AUDITOR, prompt, RECORD_SCHEMA)
    return new or rec


def verify(app: dict, max_rounds: int = 2) -> dict:
    p1 = json.loads((DATA / "pass1" / f"{app['id']}.json").read_text())
    rec = json.loads(json.dumps(p1))
    log = {"id": app["id"], "name": app["name"], "rounds": []}
    flags, signals = check(app, rec)
    log["initial_flags"] = flags
    log["signals"] = signals
    for rnd in range(1, max_rounds + 1):
        if rnd == 1:
            # access + mcp are almost never settled by search snippets, so they are always
            # deep-checked once, flagged or not (learned from the smoke test: Pipedrive).
            have = {f["field"] for f in flags}
            flags = flags + [{"check": "V4_mandatory", "field": f, "why": "always deep-checked"}
                             for f in ("access", "mcp") if f not in have]
        if not flags:
            break
        pages = deep_evidence(app, rec, flags, rnd)
        new = audit(app, rec, flags, signals, pages)
        changed = {k: [rec.get(k), new.get(k)] for k in
                   ("auth_methods", "auth_primary", "access", "api_type", "api_breadth", "mcp", "verdict", "blocker")
                   if rec.get(k) != new.get(k)}
        rec = new
        flags, signals = check(app, rec, initial=False)
        log["rounds"].append({"round": rnd, "pages": [p["url"] for p in pages], "changed": changed,
                              "flags_after": flags})
    rec["_pass"] = "final"
    rec["_open_flags"] = flags
    rec["_signals"] = signals
    (DATA / "final" / f"{app['id']}.json").write_text(json.dumps(rec, indent=1))
    (DATA / "verify" / f"{app['id']}.json").write_text(json.dumps(log, indent=1))
    return log


# ====================================================================== CLI
def parse_ids(s: str) -> set[int]:
    out = set()
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out |= set(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return out


def run(stage: str, ids: set[int], workers: int):
    apps = [a for a in load_apps() if int(a["id"]) in ids]
    fn = {"pass1": pass1, "verify": verify}[stage]
    for k in tools.STATS:  # per-stage counters
        tools.STATS[k] = 0
    done = 0
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(fn, a): a for a in apps}
        for f in as_completed(futs):
            a = futs[f]
            done += 1
            try:
                r = f.result()
                extra = f"flags={len(r['initial_flags'])} rounds={len(r['rounds'])}" if stage == "verify" else \
                    f"auth={r.get('auth_primary')} access={r.get('access')} verdict={r.get('verdict')}"
                print(f"[{stage} {done}/{len(apps)}] #{a['id']} {a['name']}: {extra}", flush=True)
            except Exception as e:
                print(f"[{stage} {done}/{len(apps)}] #{a['id']} {a['name']}: ERROR {e!r}", flush=True)
    print("STATS", json.dumps(tools.STATS), flush=True)


def human_queue():
    q = []
    for p in sorted((DATA / "final").glob("*.json"), key=lambda p: int(p.stem)):
        r = json.loads(p.read_text())
        if r.get("_open_flags"):
            q.append({"id": int(p.stem), "flags": r["_open_flags"]})
    (DATA / "human_queue.json").write_text(json.dumps(q, indent=1))
    print(f"human queue: {len(q)} apps with unresolved flags")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["pass1", "verify", "all", "queue"])
    ap.add_argument("--ids", default="1-100")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    ids = parse_ids(a.ids)
    if a.stage in ("pass1", "all"):
        run("pass1", ids, a.workers)
    if a.stage in ("verify", "all"):
        run("verify", ids, a.workers)
    if a.stage in ("verify", "all", "queue"):
        human_queue()
