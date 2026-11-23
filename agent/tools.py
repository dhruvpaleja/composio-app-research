"""Tool layer for the research agent.

Every external call the agent makes goes through here:
  * web_search / fetch_url  -> Composio tools (KEENABLE_SEARCH_WEB_PUBLIC, KEENABLE_FETCH_URL_PUBLIC)
                               executed with the Composio CLI (`composio execute`).
  * composio_catalog        -> Composio's own toolkit catalog (auth schemes per toolkit),
                               used as an independent cross-check and as a coverage signal.
  * mcp_registry            -> the official MCP Registry (registry.modelcontextprotocol.io).
  * llm                     -> Claude. Uses ANTHROPIC_API_KEY via the SDK if present,
                               otherwise the local `claude -p` CLI in headless mode.

All tool calls are cached on disk (data/cache) so re-runs are cheap and reproducible.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
APP_TITLE = "composio-app-research-agent"
# Composio's toolkit catalog. A snapshot ships in data/ so runs are reproducible; override with COMPOSIO_CATALOG
# (e.g. ~/.composio/toolkits.json, which the Composio CLI keeps up to date).
COMPOSIO_CATALOG = Path(os.environ.get("COMPOSIO_CATALOG", ROOT / "data" / "composio_toolkits.json"))

# Scraped pages sometimes contain credentials (often docs examples, sometimes real leaks). They are
# replaced before anything is cached, prompted or published.
SECRET = re.compile(r"[MNO][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,38}|gh[pousr]_[A-Za-z0-9]{36}"
                    r"|sk-ant-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|[sr]k_live_[0-9a-zA-Z]{20,}")


def redact(text: str) -> str:
    return SECRET.sub("[REDACTED-TOKEN]", text or "")


STATS = {"search": 0, "fetch": 0, "llm": 0, "llm_cost_usd": 0.0, "cache_hits": 0}


def _cache_get(kind: str, key: str):
    p = CACHE / kind / (hashlib.sha1(key.encode()).hexdigest() + ".json")
    if p.exists():
        STATS["cache_hits"] += 1
        return json.loads(p.read_text())
    return None


def _cache_put(kind: str, key: str, value):
    d = CACHE / kind
    d.mkdir(parents=True, exist_ok=True)
    (d / (hashlib.sha1(key.encode()).hexdigest() + ".json")).write_text(json.dumps(value))


def composio_execute(slug: str, args: dict, retries: int = 2) -> dict:
    """Run a Composio tool through the CLI and return its JSON result."""
    last = None
    for attempt in range(retries + 1):
        try:
            out = subprocess.run(
                ["composio", "execute", slug, "-d", json.dumps(args)],
                capture_output=True, text=True, timeout=90,
            )
            res = json.loads(out.stdout or "{}")
            if res.get("successful"):
                return res
            last = res
        except Exception as e:  # network / timeout / bad json
            last = {"successful": False, "error": str(e)}
        time.sleep(1.5 * (attempt + 1))
    return last or {"successful": False}


# ---------------------------------------------------------------- web search
def web_search(query: str, max_results: int = 6, site: str | None = None) -> list[dict]:
    key = f"{query}|{max_results}|{site}"
    hit = _cache_get("search", key)
    if hit is not None:
        return hit
    STATS["search"] += 1
    args = {"query": query, "keenable_title": APP_TITLE, "max_results": max_results, "mode": "realtime"}
    if site:
        args["site"] = site
    res = composio_execute("KEENABLE_SEARCH_WEB_PUBLIC", args)
    results = []
    for r in (res.get("data") or {}).get("results", []) or []:
        results.append({
            "url": r.get("url"),
            "title": r.get("title"),
            "snippet": redact((r.get("snippet") or r.get("description") or "")[:2500]),
        })
    if res.get("successful"):
        _cache_put("search", key, results)
    return results


# ---------------------------------------------------------------- fetch page
def _plain_fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research-agent)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        html = r.read(2_000_000).decode("utf-8", "ignore")
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text)


def fetch_url(url: str, max_chars: int = 40000) -> dict:
    """Fetch page text. Composio fetch first, raw HTTP as fallback."""
    if not url.startswith("http"):
        url = "https://" + url
    hit = _cache_get("fetch", url)
    if hit is not None:
        return hit
    STATS["fetch"] += 1
    res = composio_execute("KEENABLE_FETCH_URL_PUBLIC", {"url": url, "keenable_title": APP_TITLE}, retries=1)
    content, via = "", "composio:keenable"
    if res.get("successful"):
        content = (res.get("data") or {}).get("content") or ""
    if len(content) < 200:
        try:
            content, via = _plain_fetch(url), "http"
        except Exception as e:
            content, via = "", f"failed:{type(e).__name__}"
    out = {"url": url, "via": via, "content": redact(content[:max_chars])}
    _cache_put("fetch", url, out)  # failures are cached too, so scoring and re-runs stay offline
    return out


# ---------------------------------------------------------------- Composio catalog
_CATALOG = None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def composio_catalog(name: str, aliases: list[str] | None = None) -> list[dict]:
    """Toolkits in Composio's own catalog that match this app (exact-ish name match)."""
    global _CATALOG
    if _CATALOG is None:
        if not COMPOSIO_CATALOG.exists():
            raise SystemExit(f"Composio catalog not found at {COMPOSIO_CATALOG}. Set COMPOSIO_CATALOG.")
        _CATALOG = json.loads(COMPOSIO_CATALOG.read_text())
    wants = {_norm(n) for n in [name, *(aliases or [])] if n}
    hits = []
    for t in _CATALOG:
        n, s = _norm(t["name"]), _norm(t["slug"])
        base = s.replace("mcp", "")
        if n in wants or s in wants or base in wants:
            hits.append({
                "slug": t["slug"], "name": t["name"], "auth_schemes": t.get("auth_schemes", []),
                "managed": t.get("composio_managed_auth_schemes", []),
                "tools": (t.get("meta") or {}).get("tools_count"),
            })
    return hits


# ---------------------------------------------------------------- MCP registry
def mcp_registry(term: str, limit: int = 30) -> list[dict]:
    key = f"{term}|{limit}"
    hit = _cache_get("mcp", key)
    if hit is not None:
        return hit
    url = "https://registry.modelcontextprotocol.io/v0/servers?" + urllib.parse.urlencode({"search": term, "limit": limit})
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.load(r)
    except Exception:
        return []
    seen, out = set(), []
    for s in data.get("servers", []):
        s = s.get("server", s)
        if s.get("name") in seen:
            continue
        seen.add(s.get("name"))
        out.append({"name": s.get("name"), "description": (s.get("description") or "")[:160],
                    "repo": (s.get("repository") or {}).get("url")})
    _cache_put("mcp", key, out)
    return out


# ---------------------------------------------------------------- LLM
def llm_json(system: str, prompt: str, schema: dict | None = None, model: str = "sonnet") -> dict:
    """Ask Claude for a JSON object. Cached by (system, prompt, model)."""
    key = f"{model}|{system}|{prompt}"
    hit = _cache_get("llm", key)
    if hit is not None:
        return hit
    STATS["llm"] += 1
    text = ""
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic  # optional dependency
        mid = {"sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5", "opus": "claude-opus-5-5"}[model]
        msg = anthropic.Anthropic().messages.create(
            model=mid, max_tokens=4000, system=system,
            messages=[{"role": "user", "content": prompt + "\n\nReturn ONLY a JSON object."}])
        text = msg.content[0].text
    else:
        cmd = ["claude", "-p", "--model", model, "--tools", "", "--system-prompt", system,
               "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
               "--output-format", "json"]
        if schema:
            cmd += ["--json-schema", json.dumps(schema)]
        with tempfile.TemporaryDirectory() as td:
            out = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=300, cwd=td)
        env = json.loads(out.stdout)
        STATS["llm_cost_usd"] += env.get("total_cost_usd") or 0
        if env.get("structured_output"):
            result = env["structured_output"]
            _cache_put("llm", key, result)
            return result
        text = env.get("result", "")
    m = re.search(r"\{.*\}", text, re.S)
    result = json.loads(m.group(0)) if m else {}
    if result:  # never cache an empty answer
        _cache_put("llm", key, result)
    return result
