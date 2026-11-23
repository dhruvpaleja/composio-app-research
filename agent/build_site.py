"""Render the one-page case study (site/index.html) from results.json, stats.json, accuracy.json.

    python -m agent.build_site            # full HTML document for static hosting (Vercel)
    python -m agent.build_site --artifact # body-only variant for a claude.ai artifact preview
"""
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, SITE = ROOT / "data", ROOT / "site"
E = html.escape

AUTHOR = "Dhruv Paleja"
DEMO = (ROOT / "data" / "demo_run.txt").read_text(encoding="utf-8").strip() if (ROOT / "data" / "demo_run.txt").exists() else ""
REPO_URL = (ROOT / "data" / "repo_url.txt").read_text(encoding="utf-8").strip() if (ROOT / "data" / "repo_url.txt").exists() else "#run-it"

VERDICT = {"ready": "Ready", "ready_with_friction": "Friction", "needs_outreach": "Outreach", "not_buildable": "Not buildable",
           "unverified": "Unverified"}
VERDICT_LONG = {"ready": "Ready to build", "ready_with_friction": "Buildable with friction", "unverified": "Unverified (identity unresolved)",
                "needs_outreach": "Needs outreach", "not_buildable": "Not buildable"}
ACCESS = {"self_serve_free": "Free self-serve", "self_serve_trial": "Trial only", "paid_plan": "Paid plan",
          "app_review": "App review", "partner_gated": "Partner / sales", "no_public_api": "No public API"}
AUTH = {"OAUTH2": "OAuth 2", "API_KEY": "API key / token", "BASIC": "Basic", "OTHER": "Signed / JWT / other",
        "NONE": "None"}
MCP = {"official": "Official", "community": "Community", "none": "None"}
BLOCKER = {"none": "None", "paid_plan": "Paid plan", "app_review": "App review", "partnership": "Partnership / sales",
           "no_public_api": "No public API", "self_hosted_or_local": "Self-hosted / local only",
           "unclear_docs": "Unclear docs", "tos_restrictions": "ToS restrictions", "other": "Other"}
FIELDS = {"auth_primary": "Primary auth", "auth_methods": "All auth methods", "access": "Self-serve vs gated",
          "api_type": "API type", "mcp": "MCP status", "verdict": "Buildability verdict"}


def load():
    rows = json.loads((SITE / "results.json").read_text(encoding="utf-8"))
    stats = json.loads((DATA / "stats.json").read_text(encoding="utf-8"))
    acc = json.loads((DATA / "accuracy.json").read_text(encoding="utf-8"))
    patterns = json.loads((DATA / "patterns.json").read_text(encoding="utf-8"))
    run = json.loads((DATA / "run_stats.json").read_text(encoding="utf-8")) if (DATA / "run_stats.json").exists() else {}
    return rows, stats, acc, patterns, run


def pill(kind, val, label=None):
    return f'<span class="pill {kind}-{E(str(val))}">{E(label or str(val))}</span>'


def pct(x):
    return f"{round(100 * x)}%"


def pct1(x):
    return f"{100 * x:.1f}%"


# ------------------------------------------------------------------ pieces
def waffle(rows):
    cells = "".join(
        f'<a class="w v-{r["verdict"]}" href="#app-{r["id"]}" title="{E(r["name"])}: {VERDICT_LONG[r["verdict"]]}">'
        f'<span class="sr">{E(r["name"])}</span></a>' for r in rows)
    return f'<div class="waffle" aria-label="One square per app, coloured by verdict">{cells}</div>'


def stacked_rows(by_cat: dict, order: list, labels: dict, kind: str):
    out = []
    for cat, counts in by_cat.items():
        tot = sum(counts.values()) or 1
        segs = "".join(
            f'<span class="seg {kind}-{k}" style="flex:{counts.get(k, 0)}" title="{E(labels[k])}: {counts.get(k, 0)}">'
            f'{counts.get(k, 0) if counts.get(k, 0) else ""}</span>' for k in order if counts.get(k, 0))
        out.append(f'<div class="srow"><span class="slabel">{E(cat)}</span><span class="sbar">{segs}</span></div>')
    legend = "".join(f'<span class="lg"><i class="{kind}-{k}"></i>{E(labels[k])}</span>' for k in order)
    return f'<div class="stack">{"".join(out)}</div><div class="legend">{legend}</div>'


def hbars(counter: dict, labels: dict, kind: str, total: int, order=None):
    items = [(k, counter.get(k, 0)) for k in (order or sorted(counter, key=lambda k: -counter[k]))]
    mx = max([v for _, v in items] + [1])
    return '<div class="hbars">' + "".join(
        f'<div class="hb"><span class="hbl">{E(labels.get(k, k))}</span>'
        f'<span class="hbt"><span class="hbf {kind}-{k}" style="width:{100 * v / mx:.1f}%"></span></span>'
        f'<span class="hbv">{v}</span></div>' for k, v in items if v) + "</div>"


STAGES = [("v1_pass1", "v1", "pass 1"), ("v1_final", "v1", "after loops"), ("pass1", "v2", "pass 1"),
          ("final", "v2", "after loops"), ("final_human", "v2", "+ human queue")]


def accuracy_chart(acc):
    lo = 0.80
    h = lambda v: max(0.0, (v - lo) / (1 - lo)) * 100
    cols = []
    for key, ver, lab in STAGES:
        if key not in acc:
            continue
        c, vf = acc[key]["overall"], acc[key]["verified_overall"]
        cols.append(
            f'<div class="tcol{" v1" if ver == "v1" else ""}"><div class="tbars">'
            f'<span class="tbar right" style="height:{h(c):.1f}%"><em>{c * 100:.1f}</em></span>'
            f'<span class="tbar ver" style="height:{h(vf):.1f}%"><em>{vf * 100:.1f}</em></span></div>'
            f'<span class="tlab"><b>{ver}</b> {E(lab)}</span></div>')
    grid = "".join(f'<span class="gl" style="bottom:{h(t / 100):.0f}%"><i>{t}%</i></span>' for t in (80, 85, 90, 95, 100))
    legend = ('<div class="legend"><span class="lg"><i class="tbar right"></i>Label right</span>'
              '<span class="lg"><i class="tbar ver"></i>Right and backed by a quote found on the cited page</span><span class="lg">v1 bars in grey and red</span></div>')
    return f'<div class="tchart"><div class="tgrid">{grid}</div><div class="tcols">{"".join(cols)}</div></div>{legend}'


def field_table(acc):
    keys = [k for k, _, _ in STAGES if k in acc]
    head = "".join(f"<th>{E(v)} {E(l)}</th>" for k, v, l in STAGES if k in acc)
    body = ""
    for f, lab in FIELDS.items():
        cells = ""
        for k in keys:
            vf, c = acc[k]["verified_field"][f], acc[k]["field_accuracy"][f]
            tone = "hi" if vf >= 0.97 else ("mid" if vf >= 0.9 else "lo")
            cells += f'<td class="ft-{tone}">{vf * 100:.0f}%<small>{c * 100:.0f}% right</small></td>'
        body += f"<tr><th scope=\"row\">{E(lab)}</th>{cells}</tr>"
    return (f'<div class="tw"><table class="ftab"><thead><tr><th>Field (quote-backed %)</th>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def gold_table(acc):
    stage = "final_human" if "final_human" in acc else "final"
    p1 = {r["id"]: r for r in acc["pass1"]["rows"]}
    head = "".join(f"<th>{E(v)}</th>" for v in FIELDS.values())
    body = []
    for r in acc[stage]["rows"]:
        cells = []
        for f in FIELDS:
            ok, ok1 = r["fields"][f]["ok"], p1[r["id"]]["fields"][f]["ok"]
            got = r["fields"][f]["got"]
            got = "+".join(got) if isinstance(got, list) else got
            if ok and ok1:
                c, sym = "g-ok", "✓"
            elif ok and not ok1:
                c, sym = "g-fixed", "✓ fixed"
            elif not ok and ok1:
                c, sym = "g-broke", "✗ broke"
            else:
                c, sym = "g-miss", "✗"
            tip = f"agent: {got} · gold: {r['fields'][f]['gold']}"
            cells.append(f'<td class="{c}" title="{E(str(tip))}">{sym}<small>{E(str(got))}</small></td>')
        src = " ".join(f'<a href="{E(u)}" rel="noopener" target="_blank">doc</a>' for u in r["src"][:2])
        body.append(f'<tr><th scope="row">{E(r["name"])}</th>{"".join(cells)}<td class="src">{src}</td></tr>')
    return (f'<div class="tw"><table class="gold"><thead><tr><th>App (gold sample)</th>{head}<th>Checked against</th>'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def app_table(rows):
    out = []
    for r in rows:
        auth = " ".join(f'<span class="tag{" pri" if a == r["auth_primary"] else ""}">{E(AUTH[a])}</span>'
                        for a in (r["auth_methods"] or []))
        comp = {"native": '<span class="yes">native</span>', "mcp_only": '<span class="mid">MCP only</span>',
                "none": '<span class="no">none</span>'}[r["composio_status"]]
        ev_links = " ".join(
            f'<a href="{E(e["url"])}" target="_blank" rel="noopener" title="{E(e["field"])}: {E(e["quote"][:180])}">{E(e["field"])}</a>'
            for e in list({e["field"]: e for e in reversed(r["evidence"])}.values())[::-1][:4])
        quotes = "".join(
            f'<li><b>{E(e["field"])}</b> “{E(e["quote"])}” <a href="{E(e["url"])}" target="_blank" rel="noopener">{E(e["url"][:90])}</a>'
            f' <span class="gscore">quote found on page: {pct(e["grounding"] or 0)}</span></li>' for e in r["evidence"])
        changed = "; ".join(f'{k}: {E(str(a))} → {E(str(b))}' for k, (a, b) in r["changed_by_verification"].items())
        human = f'<p><b>Human review:</b> {E(r["human_override"]["note"])}</p>' if r.get("human_override") else ""
        if r.get("low_confidence"):
            human += f'<p><b>Low confidence:</b> {E(r["low_confidence"])}. Check by hand before relying on it.</p>'
        notes = f"""<div class="detail">
<p class="one">{E(r["one_liner"] or "")}</p>
<dl>
<dt>Auth</dt><dd>{E(r.get("auth_notes") or "")}</dd>
<dt>Access</dt><dd>{E(r.get("access_notes") or "")}</dd>
<dt>Blocker</dt><dd>{E(BLOCKER.get(r["blocker"], r["blocker"]))}{" · " + E(r["blocker_notes"]) if r.get("blocker_notes") else ""}</dd>
<dt>API</dt><dd>{E(r["api_type"])} · {E(r["api_breadth"] or "")} breadth · OpenAPI spec: {r.get("openapi_spec")} · webhooks: {r.get("webhooks")} · sandbox: {r.get("sandbox")}</dd>
<dt>MCP</dt><dd>{E(MCP[r["mcp"]])}{(' · <a href="' + E(r["mcp_url"]) + '" target="_blank" rel="noopener">' + E(r["mcp_url"][:80]) + '</a>') if r.get("mcp_url") else ""}</dd>
<dt>Composio today</dt><dd>{E(", ".join(r["composio_slugs"]) or "no toolkit in catalog")}{(" · auth " + E(", ".join(r["composio_auth"]))) if r["composio_auth"] else ""}</dd>
<dt>Verification</dt><dd>{r["verify_rounds"]} audit round(s). {("Changed: " + changed) if changed else "Pass-1 answer confirmed."}{(" Still open: " + E(", ".join(r["open_flags"]))) if r["open_flags"] else ""}</dd>
</dl>{human}
<ol class="quotes">{quotes}</ol></div>"""
        out.append(
            f'<tr id="app-{r["id"]}" class="arow-main" data-cat="{E(r["category"])}" data-verdict="{r["verdict"]}" '
            f'data-access="{r["access"]}" data-comp="{"y" if r["composio_status"] == "native" else "n"}" data-q="{E((r["name"] + " " + (r["one_liner"] or "")).lower())}">'
            f'<td class="num">{r["id"]}</td>'
            f'<th scope="row"><button class="exp" aria-expanded="false" aria-controls="d-{r["id"]}">{E(r["name"])}</button>'
            f'<small>{E(r["category"])}</small></th>'
            f'<td>{auth}</td><td>{pill("a", r["access"], ACCESS[r["access"]])}</td>'
            f'<td class="mono">{E(r["api_type"])}</td><td>{pill("m", r["mcp"], MCP[r["mcp"]])}</td>'
            f'<td>{pill("v", r["verdict"], VERDICT[r["verdict"]])}</td><td>{comp}</td>'
            f'<td class="evl">{ev_links}</td></tr>'
            f'<tr class="drow" id="d-{r["id"]}" hidden><td></td><td colspan="8">{notes}</td></tr>')
    return "".join(out)


# ------------------------------------------------------------------ page
def build(artifact: bool = False):
    rows, s, acc, P, run = load()
    n = s["n"]
    v = s["verdict"]
    stage = "final_human" if "final_human" in acc else "final"
    a1, a2 = acc["pass1"], acc[stage]
    a_loop = acc["final"]
    ho = acc["holdout"]["final_human"]
    cats = list(s["verdict_by_cat"].keys())
    by_v = lambda k: [r for r in rows if r["verdict"] == k]
    ship = [r for r in by_v("ready") if r["composio_status"] != "native" and not r.get("identity_risk")]
    ship_have = [r for r in by_v("ready") if r["composio_status"] == "native"]
    unsure = [r for r in rows if r.get("identity_risk")]
    qids = [q["id"] for q in json.loads((DATA / "human_queue.json").read_text(encoding="utf-8"))]
    queue = [r["name"] for r in rows if r["id"] in qids]
    fr = by_v("ready_with_friction")
    out = by_v("needs_outreach") + by_v("not_buildable")

    def chips(lst, extra=lambda r: ""):
        return "".join(f'<a class="chip" href="#app-{r["id"]}">{E(r["name"])}{extra(r)}</a>' for r in lst)

    L = {"links_total": sum(s["links"].values()), "links_ok": s["links"]["OK"], "links_blocked": s["links"]["BLOCKED"],
         "links_dead": s["links"]["DEAD"], "quotes_dropped": s["dead_evidence_dropped"]}
    P["wrong"] = [w.format_map(L) for w in P["wrong"]]
    run = {k: str(v).format_map(L) for k, v in run.items()}
    patterns_html = "".join(
        f'<li><h3>{E(p["head"])}</h3><p>{E(p["body"])}</p></li>' for p in P["patterns"])
    human_html = "".join(f"<li>{E(h)}</li>" for h in P["human"])
    wrong_html = "".join(f"<li>{E(h)}</li>" for h in P["wrong"])
    cat_opts = "".join(f'<option value="{E(c)}">{E(c)}</option>' for c in cats)
    access_order = list(ACCESS)
    verdict_order = list(VERDICT)

    kpi_def = [("ready", "ready to build now"), ("ready_with_friction", "buildable with friction"),
               ("needs_outreach", "need outreach"), ("not_buildable", "no hosted API"), ("unverified", "unverified")]
    kpis = "".join(
        f'<div class="kpi v-{k}"><div class="kv"><b>{v.get(k, 0)}</b><small>/{n}</small></div>'
        f'<span class="kl">{E(lab)}</span><span class="kbar" aria-hidden="true"><i style="width:{100 * v.get(k, 0) / n:.0f}%"></i></span></div>'
        for k, lab in kpi_def)

    def stat_tile(k, val):
        import re
        m = re.search(r"[~$]?\d[\d,.]*%?", val)
        big = m.group(0) if m else val
        rest = (val[:m.start()] + val[m.end():]).strip(" :") if m else ""
        return (f'<div class="rs"><b>{E(big)}</b><span class="rk">{E(k)}</span>'
                f'{f"<small>{E(rest)}</small>" if rest else ""}</div>')
    run_tiles = "".join(stat_tile(k, str(val)) for k, val in run.items())

    css = (ROOT / "agent" / "site.css").read_text(encoding="utf-8")
    js = (ROOT / "agent" / "site.js").read_text(encoding="utf-8")

    body = f"""
<header class="top"><div class="wrap topin">
  <a class="brand" href="#top"><span class="mark" aria-hidden="true">{"<i></i>" * 9}</span>App Research Agent</a>
  <nav aria-label="Sections"><a href="#patterns">Patterns</a><a href="#act">Where to act</a><a href="#matrix">All apps</a><a href="#agent">Agent</a><a href="#verify">Verification</a><a href="#run-it">Run it</a></nav>
  <a class="dl" href="results.csv" download>results.csv ↓</a>
</div></header>

<section class="hero" id="top"><div class="wrap herogrid">
  <div class="herotext">
    <p class="eyebrow"><span>Composio</span><span>AI Product Ops Intern take-home</span><span>{E(AUTHOR)}</span><span>{E(P["date"])}</span></p>
    <h1>{E(P["title"])}</h1>
    <p class="lede">{E(P["lede"])}</p>
    <div class="kpis">{kpis}</div>
    <div class="accstats" aria-label="Accuracy">
      <div class="as"><b>{pct1(a2["overall"])}</b><span>answers acceptable on the {a2["n_apps"]}-app hand-labelled gold sample</span></div>
      <div class="as"><b>{pct1(ho["overall"])}</b><span>acceptable on {ho["n_apps"]} held-out apps, labelled blind by separate agents</span></div>
      <div class="as"><b>{pct1(acc["strict"]["final_human"]["overall"])}<i>/</i>{pct1(acc["holdout_strict"]["final_human"]["overall"])}</b><span>exact match with my first-choice answer (gold / held-out)</span></div>
      <div class="as up"><b>{pct1(a1["verified_overall"])}<i>→</i>{pct1(a2["verified_overall"])}</b><span>answers backed by a quote found on the cited page</span></div>
    </div>
    <p class="accnote">My first verification loop made answers worse, so I rebuilt it. The rebuilt loop improves evidence, not labels.</p>
  </div>
  <figure class="herofig">
    <div class="figlab"><span>{n} apps · 10 × 10</span><span>by verdict</span></div>
    {waffle(rows)}
    <div class="legend">{"".join(f'<span class="lg"><i class="v-{k}"></i>{E(VERDICT_LONG[k])}</span>' for k in VERDICT)}</div>
    <figcaption>All {n} apps, one square each, in the order given (10 categories × 10). Colour is the verdict. Click a square to jump to its row.</figcaption>
  </figure>
</div></section>

<main class="wrap">

<section id="patterns" class="sec">
  <h2>What the 100 apps say</h2>
  <ol class="patterns">{patterns_html}</ol>
  <div class="grid2">
    <figure class="card"><figcaption><b>Verdict by category</b><span>count of apps, out of 10 per row</span></figcaption>
      {stacked_rows(s["verdict_by_cat"], verdict_order, VERDICT_LONG, "v")}</figure>
    <figure class="card"><figcaption><b>Self-serve vs gated, by category</b><span>how a developer gets credentials</span></figcaption>
      {stacked_rows(s["access_by_cat"], access_order, ACCESS, "a")}</figure>
    <figure class="card"><figcaption><b>Auth methods offered</b><span>apps offering each (an app can offer several)</span></figcaption>
      {hbars(s["auth_any"], AUTH, "au", n)}</figure>
    <figure class="card"><figcaption><b>Main blocker</b><span>apps not ready today, by the one thing in the way</span></figcaption>
      {hbars({k: c for k, c in s["blocker"].items() if k != "none"}, BLOCKER, "b", n)}</figure>
    <figure class="card"><figcaption><b>MCP server status, by category</b><span>vendor-run, third-party only, or none</span></figcaption>
      {stacked_rows(s["mcp_by_cat"], list(MCP), MCP, "m")}</figure>
    <figure class="card"><figcaption><b>Already in Composio's catalog?</b><span>matched against Composio's {P.get("catalog_size", "")} toolkits</span></figcaption>
      {hbars(s["composio_status"], {"native": "Native toolkit", "mcp_only": "Only a wrapped vendor MCP", "none": "Nothing yet"}, "cs", n, ["native", "mcp_only", "none"])}
      <p class="note">Only a wrapped MCP: {E(", ".join(s["mcp_only_in_composio"]))}. Nothing yet: {E(", ".join(s["not_in_composio"]))}.</p></figure>
  </div>
</section>

<section id="act" class="sec">
  <h2>Where to act</h2>
  <div class="act">
    <div class="actcol"><h3><i class="v-ready"></i>Build this week <span>{len(ship)} without a native toolkit</span></h3>
      <p>Self-serve and documented, with no native Composio toolkit today. Engineering time only.</p>
      <div class="chips">{chips(ship) or '<span class="note">None. Every ready app is already covered.</span>'}</div>
      <p class="sub">Ready and already covered ({len(ship_have)}): maintenance and depth, not new builds.</p>
      <div class="chips dim">{chips(ship_have)}</div></div>
    <div class="actcol"><h3><i class="v-ready_with_friction"></i>Build with a workaround <span>{len(fr)}</span></h3>
      <p>Buildable, but someone has to clear app review, buy a plan, work within a short trial, or get partner approval first.</p>
      <div class="chips">{chips(fr, lambda r: f'<small>{E(BLOCKER.get(r["blocker"], r["blocker"]))}</small>')}</div></div>
    <div class="actcol"><h3><i class="v-needs_outreach"></i>Start a conversation <span>{len(by_v("needs_outreach"))}</span></h3>
      <p>Credentials only come through a partnership or a sales contract. This is work for the partnerships team, not engineering.</p>
      <div class="chips">{chips(by_v("needs_outreach"))}</div>
      <p class="sub"><i class="sw v-not_buildable"></i>No hosted API ({len(by_v("not_buildable"))}): local tools that could run in a sandbox instead.</p>
      <div class="chips">{chips(by_v("not_buildable"))}</div>
      <p class="sub"><i class="sw v-unverified"></i>Unverified ({len(unsure)}): which product the brief means is unclear, so it is held back.</p>
      <div class="chips">{chips(unsure)}</div></div>
  </div>
</section>

<section id="matrix" class="sec">
  <h2>All 100 apps</h2>
  <p class="intro">Click an app name for its notes, every quote the agent relied on, and what verification changed. Hover an evidence link to see the quote. The same data is in <a href="results.json">results.json</a> and <a href="results.csv">results.csv</a>.</p>
  <div class="filters" role="search">
    <label for="q">Search</label><input id="q" type="search" placeholder="Search 100 apps…" autocomplete="off">
    <label for="fcat">Category</label><select id="fcat"><option value="">All categories</option>{cat_opts}</select>
    <label for="fver">Verdict</label><select id="fver"><option value="">All verdicts</option>{"".join(f'<option value="{k}">{E(VERDICT_LONG[k])}</option>' for k in VERDICT)}</select>
    <label for="facc">Access</label><select id="facc"><option value="">Any access</option>{"".join(f'<option value="{k}">{E(l)}</option>' for k, l in ACCESS.items())}</select>
    <label class="cb"><input id="fcomp" type="checkbox"> No native Composio toolkit</label>
    <button type="button" id="freset" class="reset" hidden>Clear filters</button>
    <span id="count" class="count" aria-live="polite">{n} apps</span>
  </div>
  <div class="tw"><table class="apps">
    <thead><tr><th>#</th><th>App</th><th>Auth (primary in bold)</th><th>Access</th><th>API</th><th>MCP</th><th>Verdict</th><th>In Composio</th><th>Evidence</th></tr></thead>
    <tbody>{app_table(rows)}</tbody></table></div>
</section>

<section id="agent" class="sec">
  <h2>The agent</h2>
  <p class="intro">{E(P["agent_intro"])}</p>
  <ol class="pipe">
    <li><b>Pass 1 · research</b><span>3 web searches per app through Composio (<code>KEENABLE_SEARCH_WEB_PUBLIC</code>). Claude fills a fixed schema with a verbatim quote and URL behind each claim.</span></li>
    <li><b>V1 · citation check</b><span>Every quote's URL is fetched again through Composio (<code>KEENABLE_FETCH_URL_PUBLIC</code>). A quote has to be on the page (word 3-gram match ≥ 60%) or that field is flagged.</span></li>
    <li><b>V2 · cross-source</b><span>Auth is checked against Composio's own toolkit catalog ({P.get("catalog_size", "")} toolkits). MCP is checked against the official MCP Registry. A disagreement raises a flag.</span></li>
    <li><b>V3 · rules</b><span>Contradictions raise flags: "ready" with a partner gate, a primary auth not in the auth list, low self-reported confidence.</span></li>
    <li><b>V4 · re-research</b><span>Flagged fields, plus access and MCP on every app, get vendor-domain docs pages. A skeptical auditor model may only answer with verbatim quotes from those pages. Then V1 to V3 run again, for up to 2 rounds.</span></li>
    <li><b>Human queue</b><span>Anything still flagged after 2 rounds goes to <code>data/human_queue.json</code> for a person to decide against the docs.</span></li>
  </ol>
  <div class="grid2">
    <div class="card"><h3>Run numbers</h3><div class="rstats">{run_tiles}</div></div>
    <div class="card"><h3>Where a human was needed</h3><ul class="plain">{human_html}</ul></div>
  </div>
</section>

<section id="verify" class="sec">
  <h2>How I know it's right</h2>
  <p class="intro">{E(P["verify_intro"])}</p>
  <div class="grid2">
    <figure class="card"><figcaption><b>Accuracy on the {a2["n_apps"]}-app gold sample, by iteration</b><span>{a2["total"]} field answers per stage. The axis starts at 80%.</span></figcaption>{accuracy_chart(acc)}
      <p class="note">v1 = first rubric and loop; v2 = fixed rubric and loop. Scored against the gold after 5 evidence-backed corrections. Against my original, uncorrected labels: v1 {pct1(acc["vs_gold_v1"]["v1_pass1"]["overall"])} → {pct1(acc["vs_gold_v1"]["v1_final"]["overall"])}, final {pct1(acc["vs_gold_v1"]["final_human"]["overall"])}.</p></figure>
    <div class="card"><h3>Loop by loop</h3>
      <dl class="nums">
        <dt>v1 loop (first version)</dt><dd>Made things worse: {pct1(acc["v1_pass1"]["overall"])} → {pct1(acc["v1_final"]["overall"])} right, {pct1(acc["v1_pass1"]["verified_overall"])} → {pct1(acc["v1_final"]["verified_overall"])} quote-backed. The auditor read missing evidence as a "no".</dd>
        <dt>v2 pass 1 (fixed rubric)</dt><dd>{pct1(a1["overall"])} right · {pct1(a1["verified_overall"])} quote-backed · {a1["apps_all_correct"]}/{a1["n_apps"]} apps fully right</dd>
        <dt>v2 after loops</dt><dd>{pct1(a_loop["overall"])} right · {pct1(a_loop["verified_overall"])} quote-backed · {a_loop["apps_all_correct"]}/{a_loop["n_apps"]} apps fully right</dd>
        {f'<dt>After human queue</dt><dd>{pct1(a2["overall"])} right · {pct1(a2["verified_overall"])} quote-backed (the queue apps were outside the gold sample)</dd>' if stage == "final_human" else ""}
        <dt>Strict scoring</dt><dd>Only my first-choice answer counts: {pct1(acc["strict"]["pass1"]["overall"])} after pass 1 → {pct1(acc["strict"]["final_human"]["overall"])} final. 56 of 180 gold fields accept more than one answer.</dd>
        <dt>Held-out sample ({ho["n_apps"]} apps)</dt><dd>Labelled blind by 3 separate research agents, then adjudicated by me: {pct1(acc["holdout"]["pass1"]["overall"])} → {pct1(ho["overall"])} right, {pct1(acc["holdout"]["pass1"]["verified_overall"])} → {pct1(ho["verified_overall"])} quote-backed, {pct1(acc["holdout_strict"]["final_human"]["overall"])} strict. Both misses are extra OAuth (Telegram, Clay).</dd>
        <dt>Change audit, all 100 apps</dt><dd>The loop changed {sum(s["field_changes"].values())} fields in {s["apps_changed"]} apps. Checked by hand: 6 apps fixed, 1 debatable, 1 still wrong, 1 made wrong (Mermaid CLI, reverted in review).</dd>
        <dt>Quotes found on the cited page</dt><dd>{pct1(s["grounding_pass1"])} of {s["quotes_pass1"]} in pass 1 → {pct1(s["grounding_final"])} of {s["quotes_final"]} after</dd>
        <dt>Apps flagged by V1 to V3</dt><dd>{s["apps_with_initial_flags"]} of {n}</dd>
        <dt>Fields changed by the loop</dt><dd>{sum(s["field_changes"].values())} in {s["apps_changed"]} apps ({", ".join(f"{k} {c}" for k, c in s["field_changes"].items())})</dd>
        <dt>Still flagged after 2 rounds</dt><dd>{len(queue)} apps went to the human queue ({E(", ".join(queue))}). Both were decided by hand, see the agent section.</dd>
      </dl></div>
  </div>
  <h3 class="h3">Verified accuracy per field, by iteration</h3>
  <p class="intro">Big number: right and backed by a quote on the page. Small number: right at all.</p>
  {field_table(acc)}
  <h3 class="h3">Every gold-sample answer, hit or miss</h3>
  <p class="intro">✓ right in both passes · <span class="g-fixed inl">✓ fixed</span> wrong in pass 1, fixed by the loops · <span class="g-broke inl">✗ broke</span> right in pass 1, made wrong by the loops · <span class="g-miss inl">✗</span> still wrong. Hover a cell for the agent's answer against gold.</p>
  {gold_table(acc)}
  <div class="card warn"><h3>What is still wrong or weak</h3><ul class="plain">{wrong_html}</ul></div>
</section>

<section id="run-it" class="sec">
  <h2>Run it</h2>
  <div class="grid2">
    <div class="card"><h3>Re-run the research</h3>
<pre><code>git clone {E(REPO_URL)}
cd composio-app-research
python3 -m agent.pipeline all --ids 41   # one app (Shopify), replayed from the cache
python3 -m agent.human && python3 -m agent.score
python3 -m agent.analyze && python3 -m agent.check && python3 -m agent.build_site</code></pre>
      <p class="note">The cache in <code>data/cache</code> ships with the repo, so the commands above reproduce this page offline, with no keys and no cost. To research live, run <code>composio login</code>, delete <code>data/cache</code>, and run <code>--ids 1-100</code>. Claude runs through <code>ANTHROPIC_API_KEY</code> if set, otherwise the local <code>claude</code> CLI.</p>
      <h3>Recorded run: one app, live, cache cleared</h3>
<pre><code>{E(DEMO)}</code></pre></div>
    <div class="card"><h3>For agents reading this page</h3>
      <ul class="plain">
        <li><a href="results.json">results.json</a>: 100 records, full schema, with evidence quotes and grounding scores.</li>
        <li><a href="results.csv">results.csv</a>: one row per app.</li>
        <li><a href="llms.txt">llms.txt</a>: field definitions and how to read the data.</li>
        <li>Source and README: <a href="{E(REPO_URL)}">{E(REPO_URL)}</a></li>
      </ul></div>
  </div>
</section>
</main>
<footer class="foot"><div class="wrap"><span>Made by {E(AUTHOR)} for Composio's AI Product Ops Intern take-home. Researched {E(P["date"])}.</span><span>Facts about vendors change; each claim links to the page it came from.</span></div></footer>
<script>{js}</script>
"""
    head = f"""<title>App Research Agent</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="color-scheme" content="light"><meta name="theme-color" content="#f7f5f0">
<meta name="description" content="{E(P['lede'])}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&display=swap">
<style>{css}</style>"""
    if artifact:
        page = head + body
        (SITE / "artifact.html").write_text(page, encoding="utf-8")
    else:
        page = f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">{head}</head><body>{body}</body></html>'
        (SITE / "index.html").write_text(page, encoding="utf-8")
    print(f"wrote {len(page) // 1024} KB")


if __name__ == "__main__":
    build("--artifact" in sys.argv)
