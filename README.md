# App Research Agent: 100 apps → agent-toolkit readiness

Take-home for Composio's AI Product Ops Intern role. **Dhruv Paleja.**

**Live case study:** https://dhruv-paleja-composio-case-study.vercel.app (built from `site/index.html`)

For each of 100 apps the agent records:
- category and a one-liner
- auth methods
- self-serve vs gated access
- API surface
- MCP status
- a buildability verdict with the main blocker
- the evidence behind every claim: a URL and a verbatim quote

It then checks its own work. The outputs are a one-page case study (`site/index.html`) and the data (`site/results.json`, `site/results.csv`, `site/llms.txt`).

## Results in one paragraph

- **Verdicts:** 61 apps are ready to build today, 30 more after one hurdle, and 6 need a sales or partnership conversation. 2 are local tools with no hosted API, and 1 is unresolved.
- **Accuracy:** checked on 30 apps labelled by hand and 18 held-out apps labelled blind by separate research agents. 98.9% and 98.1% of answers are acceptable; 85.0% and 86.1% match the first-choice answer exactly.
- **The verification loop:** the first version made answers worse. The rebuilt loop raised the share of answers backed by a quote found on the cited page from 95.0% to 98.9%.

## How it works

```
data/apps.csv → PASS 1 → V1 citation check → V2 cross-source → V3 rules → V4 re-research → human review → link check → site/
```

| Stage | What it does |
|---|---|
| Pass 1 | 3 Composio web searches per app (`KEENABLE_SEARCH_WEB_PUBLIC` via `composio execute`). Claude fills a fixed schema with a verbatim quote and URL per claim. |
| V1 citation check | Re-fetches every quoted page (`KEENABLE_FETCH_URL_PUBLIC`). The quote must be on the page (word 3-gram overlap ≥ 60%). |
| V2 cross-source | Auth vs Composio's toolkit catalog (snapshot in `data/composio_toolkits.json`). MCP vs the official MCP Registry. |
| V3 rules | Contradictions, e.g. verdict "ready" with a partner gate, or primary auth missing from the auth list. |
| V4 re-research | Flagged fields, plus access and MCP on every app, get vendor-domain pages and a skeptical auditor that may only answer with verbatim quotes. Max 2 rounds. |
| Human review | `data/human_queue.json` holds the apps still flagged. Decisions are in `gold/human_overrides.json` and applied by `agent/human.py`. |
| Link check | Every evidence URL is requested live (`agent/linkcheck.py`). Dead links are dropped from the published data. |

The labelling rubric is in `agent/schema.py`. The agent, the auditor and the hand checks all use it, so "accuracy" means agreement on the same definitions.

## Cross-check against a manual pass

`site/manual-pass.pdf` is an independent manual research pass over the same 100 apps. Its table is extracted into `data/manual_pass_rows.json`; `python -m agent.manual_pass` maps it onto the agent's schema and writes per-app agreement to `data/manual_pass.json` (also published as `site/manual_pass.json`). The extraction reproduces the PDF's own totals (69 free, 10 paid, 13 gated, 41 official MCP). Agreement with the agent: verdict 82/100, access 82/100, primary auth 86/97, MCP 42/60 where the manual pass names one. The page shows every disagreement, and each app's detail row shows the manual answer next to the agent's.

## Run it

Python 3.10+, standard library only. The cache in `data/cache/` (≈38 MB) ships with the repo, so these commands reproduce the published page **offline, with no keys and no cost**:

```bash
python3 -m agent.pipeline all --ids 41   # one app (Shopify), replayed from the cache
python3 -m agent.human                   # apply human review decisions
python3 -m agent.score                   # accuracy: gold, strict, original labels, held-out
python3 -m agent.analyze                 # results.json / results.csv / stats.json
python3 -m agent.manual_pass             # cross-check vs the manual pass
python3 -m agent.check                   # every number in the page text vs the data (fails on mismatch)
python3 -m agent.build_site              # site/index.html
```

To research live:
1. Install the [Composio CLI](https://docs.composio.dev) and run `composio login`.
2. Make sure `ANTHROPIC_API_KEY` is set (then `pip install -r requirements.txt`) or the `claude` CLI is logged in.
3. Delete `data/cache/` and run `python3 -m agent.pipeline all --ids 1-100 --workers 12`.

That costs about $21 of Claude usage and takes under an hour. A single app takes about 2 minutes and $0.13 (recorded run on the page). Then run `python3 -m agent.linkcheck` before `analyze`.

`COMPOSIO_CATALOG=/path/to/toolkits.json` points the catalog check at a fresher catalog, e.g. the one the Composio CLI keeps at `~/.composio/toolkits.json`.

## Verification files

- `gold/gold.json`: 30-app stratified random sample (seed 42), labelled by hand from vendor docs, with sources. `_revisions` lists the 5 labels changed after reading the agent's evidence. The untouched original is `gold/gold_v1.json`.
- `gold/holdout.json`: 18 held-out apps (seed 7), labelled blind by three separate research agents and then adjudicated by hand.
- `gold/composio_matches.json`: hand corrections to the automatic Composio catalog match.
- `data/history/`: the first (v1) run, kept so its regression stays visible.
- `data/verify/<id>.json`: per-app log of flags, pages fetched and changes in each audit round.
- `data/accuracy.json`, `data/linkcheck.json`, `data/stats.json`: the numbers on the page.

## Layout

```
agent/   pipeline.py  pass 1 + verification loop        tools.py   Composio / MCP Registry / Claude calls, cached
         schema.py    rubric + output schema             human.py   apply human review decisions
         score.py     accuracy vs gold / holdout         linkcheck.py  live link check
         analyze.py   dataset + pattern stats             check.py   page text vs data consistency test
         build_site.py, site.css, site.js                 the page
data/    apps.csv (input), pass1/, final/, final_human/, verify/, evidence/, history/ (v1 run), cache/,
         composio_toolkits.json, accuracy.json, stats.json, linkcheck.json, human_queue.json,
         patterns.json + run_stats.json + demo_run.txt (written by hand: page text and recorded numbers)
gold/    gold.json, gold_v1.json, holdout.json, human_overrides.json, composio_matches.json, sample_ids.json,
         holdout_ids.json, probe.py + batch.py (helpers used for the hand check)
site/    index.html, results.json, results.csv, llms.txt (the deployed page)
```
