"""Link check: every evidence / docs / MCP URL is requested live. Dead links (404/410/DNS) are dropped from the
published data by analyze.py; bot-blocked pages (403/429/400/timeouts) are kept, since their quotes were
fetched and grounded earlier.

    python -m agent.linkcheck      -> data/linkcheck.json  {url: {"status": int|str, "class": OK|BLOCKED|DEAD}}
"""
import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def status(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # DNS, TLS, timeout
        return type(e).__name__


def classify(s) -> str:
    if isinstance(s, int):
        if s < 400 or s in (401, 405):  # MCP endpoints answer GET with 401/405
            return "OK"
        if s in (404, 410):
            return "DEAD"
        return "BLOCKED"
    return "DEAD" if s in ("URLError", "gaierror") else "BLOCKED"


def main():
    urls = set()
    src = ROOT / "data" / ("final_human" if (ROOT / "data" / "final_human").exists() else "final")
    for p in src.glob("*.json"):
        r = json.loads(p.read_text())
        urls |= {e["url"] for e in r.get("evidence", []) if str(e.get("url", "")).startswith("http")}
        urls |= {u for u in (r.get("docs_url"), r.get("mcp_url")) if u and str(u).startswith("http")}
    with ThreadPoolExecutor(24) as ex:
        res = dict(zip(sorted(urls), ex.map(status, sorted(urls))))
    # a dead result gets one retry, so a transient error doesn't delete evidence
    for u, s in list(res.items()):
        if classify(s) == "DEAD":
            res[u] = status(u)
    out = {u: {"status": s, "class": classify(s)} for u, s in res.items()}
    (ROOT / "data" / "linkcheck.json").write_text(json.dumps(out, indent=1))
    from collections import Counter
    print(len(out), "urls", dict(Counter(v["class"] for v in out.values())))


if __name__ == "__main__":
    main()
