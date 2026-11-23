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


def more(label, inner, cls=""):
    """Progressive disclosure: secondary detail stays one click away instead of on the page."""
    return f'<details class="more {cls}"><summary>{label}</summary><div class="morein">{inner}</div></details>'


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


def app_table(rows, mp=None):
    mp = {a["id"]: a for a in (mp or {}).get("apps", [])}
    out = []
    for r in rows:
        others = [a for a in (r["auth_methods"] or []) if a != r["auth_primary"]]
        auth = (f'<span class="tag pri">{E(AUTH.get(r["auth_primary"], r["auth_primary"] or "?"))}</span>'
                + (f'<span class="more-n" title="{E(", ".join(AUTH[a] for a in others))}">+{len(others)}</span>' if others else ""))
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
<dt>Evidence</dt><dd class="evl">{ev_links}</dd>
{manual_detail(mp.get(r["id"]))}
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
            f'<td>{pill("v", r["verdict"], VERDICT[r["verdict"]])}</td><td>{comp}</td></tr>'
            f'<tr class="drow" id="d-{r["id"]}" hidden><td></td><td colspan="7">{notes}</td></tr>')
    return "".join(out)


# ------------------------------------------------------------------ manual cross-check
MP_VERDICT = {"ready": ("v", "ready", "Ready"), "friction": ("v", "ready_with_friction", "Friction"),
              "outreach": ("v", "needs_outreach", "Outreach"), "not_buildable": ("v", "not_buildable", "No API")}
MP_ACCESS = {"self_serve": ("a", "self_serve_free", "Self-serve"), "paid": ("a", "paid_plan", "Paid plan"),
             "review": ("a", "app_review", "Review"), "gated": ("a", "partner_gated", "Gated"),
             "no_api": ("a", "no_public_api", "No API")}
MP_MCP = {"official": ("m", "official", "Official"), "community": ("m", "community", "Community"), "none": ("m", "none", "None")}
MP_FIELDS = {"verdict": ("Verdict", MP_VERDICT), "access": ("Access", MP_ACCESS), "mcp": ("MCP", MP_MCP)}
RANK = {"ready": 0, "friction": 1, "outreach": 2, "not_buildable": 3}


def load_manual():
    f = DATA / "manual_pass.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def mp_pill(field, val):
    kind, cls, lab = MP_FIELDS[field][1][val]
    return pill(kind, cls, lab)


def manual_detail(m):
    if not m:
        return ""
    diff = [MP_FIELDS[k][0].lower() for k in MP_FIELDS if m["agree"].get(k) is False]
    src = f' · <a href="{E(m["manual_url"])}" target="_blank" rel="noopener">source</a>' if m["manual_url"] else ""
    flag = f' <span class="diff">differs on {E(", ".join(diff))}</span>' if diff else ' <span class="same">agrees</span>'
    return (f'<dt>Manual pass</dt><dd>{mp_pill("verdict", m["manual_norm"]["verdict"])} '
            f'{E(m["manual"]["access"])} · {E(m["manual"]["api_mcp"])}{src}{flag}</dd>')


WIN = {"agent": ("Agent right", "w-agent"), "manual": ("Manual right", "w-manual"),
       "neither": ("Both wrong", "w-neither"), "unclear": ("Unclear", "w-unclear")}
RUBRIC_PILL = {**{k: ("v", k, VERDICT[k]) for k in VERDICT}, **{k: ("a", k, ACCESS[k]) for k in ACCESS},
               **{k: ("m", k, MCP[k]) for k in MCP}}


def checked_cell(a, field):
    r = (a.get("adjudication") or {}).get(field)
    if not r:
        return '<td></td>'
    lab, cls = WIN[r["winner"]]
    pl = pill(*RUBRIC_PILL[r["correct"]]) if r["correct"] in RUBRIC_PILL else ""
    q = f' title="{E(r.get("quote") or "")}"' if r.get("quote") else ""
    link = f' <a href="{E(r["url"])}" target="_blank" rel="noopener"{q}>source</a>' if r.get("url") else ""
    return f'<td>{pl}<span class="win {cls}">{lab}</span>{link}<small>{E(r.get("reason") or "")}</small></td>'


def adjudication_block(S):
    A = S.get("adjudication")
    if not A:
        return ""
    tot = {k: sum(A["wins"][f].get(k, 0) for f in A["wins"]) for k in WIN}
    n = sum(tot.values())
    tiles = "".join(f'<div class="ag {WIN[k][1]}"><b>{tot[k]}</b><span class="agl">{WIN[k][0].lower()}</span>'
                    f'<small>of {n} disputed fields</small></div>' for k in WIN)
    per = "".join(f'<tr><th scope="row">{lab}</th>' + "".join(f'<td>{A["wins"][f].get(k, 0)}</td>' for k in WIN) + "</tr>"
                  for f, lab in [("verdict", "Verdict"), ("access", "Access"), ("mcp", "MCP")])
    be, ag, mc = A["best_estimate"], A["agent"], S["counts"]
    man_v = {"ready": mc["verdict"].get("ready", 0), "ready_with_friction": mc["verdict"].get("friction", 0),
             "needs_outreach": mc["verdict"].get("outreach", 0), "not_buildable": mc["verdict"].get("not_buildable", 0)}
    rows_ = [(VERDICT_LONG[k], ag["verdict"].get(k, 0), man_v.get(k, "—"), be["verdict"].get(k, 0)) for k in VERDICT]
    rows_ += [("Free self-serve access", ag["access"].get("self_serve_free", 0), "—", be["access"].get("self_serve_free", 0)),
              ("Trial-only access", ag["access"].get("self_serve_trial", 0), "—", be["access"].get("self_serve_trial", 0)),
              ("Paid plan for API", ag["access"].get("paid_plan", 0), mc["access"].get("paid", 0), be["access"].get("paid_plan", 0)),
              ("Official MCP server", ag["mcp"].get("official", 0), mc["mcp"].get("official", 0), be["mcp"].get("official", 0))]
    best = "".join(f'<tr><th scope="row">{E(l)}</th><td>{a}</td><td>{m}</td><td class="bestc">{b}</td></tr>' for l, a, m, b in rows_)
    return f"""
  <h3 class="xh">Who was right?</h3>
  <p class="intro">Every disputed field was re-checked against the vendor's live docs and pricing pages, using the same rubric, with a source link and quote for each ruling.</p>
  <div class="agree">{tiles}</div>
  <div class="grid2">
    <div class="card"><h3>Rulings by field</h3><div class="tw"><table class="mini"><thead><tr><th></th>{"".join(f"<th>{WIN[k][0]}</th>" for k in WIN)}</tr></thead><tbody>{per}</tbody></table></div></div>
    <div class="card"><h3>Best-estimate numbers</h3><div class="tw"><table class="mini"><thead><tr><th></th><th>Agent</th><th>Manual</th><th>Checked</th></tr></thead><tbody>{best}</tbody></table></div>
      <p class="note">Checked = the agent's answer where both passes agree, the re-checked answer where they don't. Unclear rulings keep the agent's answer.</p></div>
  </div>"""


def cross_section(mp):
    if not mp:
        return ""
    S, apps = mp["summary"], mp["apps"]
    tiles = "".join(
        f'<div class="ag"><b>{round(100 * S["agree"][k] / S["n"][k])}%</b><span class="agl">{lab}</span>'
        f'<small>{S["agree"][k]} of {S["n"][k]}{note}</small><span class="kbar"><i style="width:{100 * S["agree"][k] / S["n"][k]:.0f}%"></i></span></div>'
        for k, lab, note in [("verdict", "same verdict", ""), ("access", "same access", ""),
                             ("auth", "same primary auth", ""), ("mcp", "same MCP status", " where stated")])
    vd = [a for a in apps if a["agree"]["verdict"] is False]
    softer = sum(RANK[a["manual_norm"]["verdict"]] < RANK[a["agent_norm"]["verdict"]] for a in vd)
    c = S["counts"]

    def table(field):
        rows_ = [a for a in apps if a["agree"].get(field) is False]
        body = "".join(
            f'<tr><th scope="row"><a href="#app-{a["id"]}">{E(a["name"])}</a></th>'
            f'<td>{mp_pill(field, a["manual_norm"][field])}<small>{E(a["manual"]["access"] if field != "mcp" else a["manual"]["api_mcp"])}</small></td>'
            f'<td>{mp_pill(field, a["agent_norm"][field])}</td>{checked_cell(a, field)}</tr>'
            for a in rows_)
        return (f'<details class="more big"><summary>{MP_FIELDS[field][0]} disagreements ({len(rows_)})</summary><div class="morein">'
                f'<div class="tw"><table class="xtab"><thead><tr><th>App</th><th>Manual pass</th><th>Agent</th><th>Checked against vendor docs</th></tr></thead>'
                f'<tbody>{body}</tbody></table></div></div></details>')

    return f"""
<section id="cross" class="sec">
  <h2>A second opinion</h2>
  <p class="intro">An independent manual research pass over the same 100 apps, read against the agent field by field. <a href="manual-pass.pdf">Read the manual pass (PDF)</a></p>
  <div class="agree">{tiles}</div>
  <div class="grid2">
    <div class="card"><h3>The manual pass in numbers</h3><div class="rstats">
      <div class="rs"><b>{c["access"].get("self_serve", 0)}</b><span class="rk">free account, no approval</span></div>
      <div class="rs"><b>{c["access"].get("paid", 0)}</b><span class="rk">need a paid plan</span></div>
      <div class="rs"><b>{c["access"].get("gated", 0)}</b><span class="rk">gated: partner, customer or sales</span></div>
      <div class="rs"><b>{c["mcp"].get("official", 0)}</b><span class="rk">official MCP named</span><small>agent: {S["agent_mcp_official"]}</small></div>
    </div></div>
    <div class="card"><h3>Where they part ways</h3><div class="loopkey">
      <div><span>verdicts that differ</span><b>{len(vd)}</b><small>manual more optimistic on {softer}, stricter on {len(vd) - softer}</small></div>
      <div><span>official MCP servers</span><b>{c["mcp"].get("official", 0)} vs {S["agent_mcp_official"]}</b><small>the agent also checks the MCP Registry; {c["mcp"].get("unstated", 0)} manual rows don't name an MCP status</small></div>
    </div></div>
  </div>
  {adjudication_block(S)}
  {table("verdict")}{table("access")}{table("mcp")}
</section>
"""


# ------------------------------------------------------------------ page
def build(artifact: bool = False):
    rows, s, acc, P, run = load()
    MPD = load_manual()
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

    def groups(lst):
        g = {}
        for r in lst:
            g.setdefault(BLOCKER.get(r["blocker"], r["blocker"]), []).append(r)
        return "".join(f'<div class="grp"><span class="grph">{E(k)} <b>{len(v)}</b></span><div class="chips">{chips(v)}</div></div>'
                       for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])))

    def chips(lst, extra=lambda r: ""):
        return "".join(f'<a class="chip" href="#app-{r["id"]}">{E(r["name"])}{extra(r)}</a>' for r in lst)

    L = {"links_total": sum(s["links"].values()), "links_ok": s["links"]["OK"], "links_blocked": s["links"]["BLOCKED"],
         "links_dead": s["links"]["DEAD"], "quotes_dropped": s["dead_evidence_dropped"]}
    P["wrong"] = [w.format_map(L) for w in P["wrong"]]
    run = {k: str(v).format_map(L) for k, v in run.items()}
    patterns_html = "".join(
        f'<li><details><summary><h3>{E(p["head"])}</h3></summary><p>{E(p["body"])}</p></details></li>' for p in P["patterns"])
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
    run_items = list(run.items())
    run_tiles = ('<div class="rstats">' + "".join(stat_tile(k, str(val)) for k, val in run_items[:6]) + "</div>"
                 + more(f"{len(run_items) - 6} more", '<div class="rstats">' + "".join(stat_tile(k, str(val)) for k, val in run_items[6:]) + "</div>"))

    fr_groups = groups(fr)

    css = (ROOT / "agent" / "site.css").read_text(encoding="utf-8")
    js = (ROOT / "agent" / "site.js").read_text(encoding="utf-8")

    body = f"""
<header class="top"><div class="wrap topin">
  <a class="brand" href="#top"><span class="mark" aria-hidden="true">{"<i></i>" * 9}</span>App Research Agent</a>
  <nav aria-label="Sections"><a href="#patterns">Patterns</a><a href="#act">Where to act</a><a href="#matrix">All apps</a><a href="#agent">Agent</a><a href="#verify">Verification</a>{'<a href="#cross">Cross-check</a>' if MPD else ""}<a href="#run-it">Run it</a></nav>
  <a class="dl" href="results.csv" download>results.csv ↓</a>
</div></header>

<section class="hero" id="top"><div class="wrap herogrid">
  <div class="herotext">
    <p class="eyebrow"><span>Composio</span><span>AI Product Ops Intern take-home</span><span>{E(AUTHOR)}</span><span>{E(P["date"])}</span></p>
    <h1>{E(P["title"])}</h1>
    <p class="lede">{E(P["lede"])}</p>
    <div class="kpis">{kpis}</div>
    <div class="accstats" aria-label="Accuracy">
      <div class="as"><b>{pct1(a2["overall"])}</b><span>accurate · {a2["n_apps"]}-app gold set</span></div>
      <div class="as"><b>{pct1(ho["overall"])}</b><span>accurate · {ho["n_apps"]} blind held-out</span></div>
      <div class="as"><b>{pct1(acc["strict"]["final_human"]["overall"])}<i>/</i>{pct1(acc["holdout_strict"]["final_human"]["overall"])}</b><span>exact first-choice match</span></div>
      <div class="as up"><b>{pct1(a1["verified_overall"])}<i>→</i>{pct1(a2["verified_overall"])}</b><span>quote-backed answers</span></div>
    </div>
  </div>
  <figure class="herofig">
    <div class="figlab"><span>{n} apps · 10 × 10</span><span>by verdict</span></div>
    {waffle(rows)}
    <div class="legend">{"".join(f'<span class="lg"><i class="v-{k}"></i>{E(VERDICT_LONG[k])}</span>' for k in VERDICT)}</div>
    <figcaption>One square per app. Click to open it.</figcaption>
  </figure>
</div></section>

<main class="wrap">

<section id="patterns" class="sec">
  <h2>What the 100 apps say</h2>
  <p class="intro">{len(P["patterns"])} patterns. Open one to read the evidence.</p>
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
      {more("Which apps", '<p class="note">Only a wrapped MCP: ' + E(", ".join(s["mcp_only_in_composio"])) + '.<br>Nothing yet: ' + E(", ".join(s["not_in_composio"])) + '.</p>')}</figure>
  </div>
</section>

<section id="act" class="sec">
  <h2>Where to act</h2>
  <div class="act">
    <div class="actcol"><h3><i class="v-ready"></i>Build this week <span>{len(ship)} without a native toolkit</span></h3>
      <p>Self-serve, no toolkit yet. Engineering time only.</p>
      <div class="chips">{chips(ship) or '<span class="note">None. Every ready app is already covered.</span>'}</div>
      {more("Already covered (" + str(len(ship_have)) + ")", '<div class="chips dim">' + chips(ship_have) + '</div>')}</div>
    <div class="actcol"><h3><i class="v-ready_with_friction"></i>Build with a workaround <span>{len(fr)}</span></h3>
      <p>One hurdle first: review, a paid plan or a trial.</p>
      {fr_groups}</div>
    <div class="actcol"><h3><i class="v-needs_outreach"></i>Start a conversation <span>{len(by_v("needs_outreach"))}</span></h3>
      <p>Credentials need a partnership. A job for BD.</p>
      <div class="chips">{chips(by_v("needs_outreach"))}</div>
      <p class="sub"><i class="sw v-not_buildable"></i>No hosted API ({len(by_v("not_buildable"))})</p>
      <div class="chips">{chips(by_v("not_buildable"))}</div>
      <p class="sub"><i class="sw v-unverified"></i>Unverified ({len(unsure)})</p>
      <div class="chips">{chips(unsure)}</div></div>
  </div>
</section>

<section id="matrix" class="sec">
  <h2>All 100 apps</h2>
  <p class="intro">Click an app to see its evidence. Raw data: <a href="results.json">JSON</a> · <a href="results.csv">CSV</a>.</p>
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
    <thead><tr><th>#</th><th>App</th><th>Auth</th><th>Access</th><th>API</th><th>MCP</th><th>Verdict</th><th>In Composio</th></tr></thead>
    <tbody>{app_table(rows, MPD)}</tbody></table></div>
</section>

<section id="agent" class="sec">
  <h2>The agent</h2>
  {more("How it works", '<p>' + E(P["agent_intro"]) + '</p>', "lead")}
  <ol class="pipe">
    <li><b>Research</b><span>3 Composio web searches per app. Every claim gets a quote and URL.</span></li>
    <li><b>Citation check</b><span>Re-fetch each page. The quote must be on it.</span></li>
    <li><b>Cross-source</b><span>Auth vs Composio's catalog. MCP vs the MCP Registry.</span></li>
    <li><b>Rules</b><span>Flag contradictions, like "ready" behind a partner gate.</span></li>
    <li><b>Re-research</b><span>A skeptical auditor re-checks flags on vendor docs, up to 2 rounds.</span></li>
    <li><b>Human queue</b><span>Whatever is still flagged, a person decides.</span></li>
  </ol>
  <div class="grid2">
    <div class="card"><h3>Run numbers</h3>{run_tiles}</div>
    <div class="card"><h3>Where a human was needed</h3><p class="note" style="margin:0 0 4px">{len(P["human"])} judgement calls the agent could not make alone.</p>{more("Read them", '<ul class="plain">' + human_html + '</ul>')}</div>
  </div>
</section>

<section id="verify" class="sec">
  <h2>How I know it's right</h2>
  {more("Method", '<p>' + E(P["verify_intro"]) + '</p>', "lead")}
  <div class="grid2">
    <figure class="card"><figcaption><b>Accuracy on the {a2["n_apps"]}-app gold sample, by iteration</b><span>{a2["total"]} field answers per stage. The axis starts at 80%.</span></figcaption>{accuracy_chart(acc)}
      <details class="more"><summary>Notes</summary><div class="morein"><p class="note">v1 = first rubric and loop; v2 = fixed rubric and loop. Scored against the gold after 5 evidence-backed corrections. Against my original, uncorrected labels: v1 {pct1(acc["vs_gold_v1"]["v1_pass1"]["overall"])} → {pct1(acc["vs_gold_v1"]["v1_final"]["overall"])}, final {pct1(acc["vs_gold_v1"]["final_human"]["overall"])}.</p></div></details></figure>
    <div class="card"><h3>Loop by loop</h3>
      <div class="loopkey"><div><span>v1 loop · labels right</span><b class="c-outreach">{pct1(acc["v1_pass1"]["overall"])} → {pct1(acc["v1_final"]["overall"])}</b><small>made it worse, rebuilt</small></div><div><span>v2 loop · quote-backed</span><b class="c-ready">{pct1(a1["verified_overall"])} → {pct1(a2["verified_overall"])}</b><small>evidence improved</small></div></div>
      <details class="more"><summary>All loop numbers</summary><div class="morein">
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
      </dl></div></details></div>
  </div>
  <details class="more big"><summary>Accuracy per field, by iteration</summary><div class="morein">
  <p class="intro">Big number: right and backed by a quote on the page. Small number: right at all.</p>
  {field_table(acc)}</div></details>
  <details class="more big"><summary>Every gold-sample answer, hit or miss</summary><div class="morein">
  <p class="intro">✓ right in both passes · <span class="g-fixed inl">✓ fixed</span> wrong in pass 1, fixed by the loops · <span class="g-broke inl">✗ broke</span> right in pass 1, made wrong by the loops · <span class="g-miss inl">✗</span> still wrong. Hover a cell for the agent's answer against gold.</p>
  {gold_table(acc)}</div></details>
  <details class="more big warnd"><summary>What is still wrong or weak ({len(P["wrong"])})</summary><div class="morein"><ul class="plain">{wrong_html}</ul></div></details>
</section>

{cross_section(MPD)}
<section id="run-it" class="sec">
  <h2>Run it</h2>
  <div class="grid2">
    <div class="card"><h3>Re-run the research</h3>
<pre><code>git clone {E(REPO_URL)}
cd composio-app-research
python3 -m agent.pipeline all --ids 41   # one app (Shopify), replayed from the cache
python3 -m agent.human && python3 -m agent.score
python3 -m agent.analyze && python3 -m agent.check && python3 -m agent.build_site</code></pre>
      <p class="note">Runs offline from the shipped cache: no keys, no cost.</p>
      {more("Research live instead", '<p class="note">Run <code>composio login</code>, delete <code>data/cache</code>, then <code>--ids 1-100</code>. Claude runs via <code>ANTHROPIC_API_KEY</code> or the local <code>claude</code> CLI.</p>')}
      {more("Recorded run: one app, live", '<pre><code>' + E(DEMO) + '</code></pre>')}</div>
    <div class="card"><h3>For agents reading this page</h3>
      <ul class="plain">
        <li><a href="results.json">results.json</a>: full records with evidence</li>
        <li><a href="results.csv">results.csv</a>: one row per app.</li>
        <li><a href="llms.txt">llms.txt</a>: field definitions</li>
        <li><a href="manual_pass.json">manual_pass.json</a>: an independent manual pass, compared field by field</li>
        <li>Source and README: <a href="{E(REPO_URL)}">{E(REPO_URL)}</a></li>
      </ul></div>
  </div>
</section>
</main>
<footer class="foot"><div class="wrap"><span>Made by {E(AUTHOR)} for Composio's AI Product Ops Intern take-home. Researched {E(P["date"])}.</span><span>Every claim links to its source.</span></div></footer>
<script>{js}</script>
"""
    head = f"""<title>App Research Agent</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="color-scheme" content="light"><meta name="theme-color" content="#ffffff">
<meta name="description" content="{E(P['lede'])}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400..700&family=Geist+Mono:wght@400;500&display=swap">
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
