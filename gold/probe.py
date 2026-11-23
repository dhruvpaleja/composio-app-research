"""Manual-check helper: fetch a page and print only lines around the words I'm checking."""
import re, sys
sys.path.insert(0, '.')
from agent import tools
url, pat = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else r"oauth|api key|token|basic|free|trial|plan|partner|approv|mcp"
t = tools.fetch_url(url)["content"]
print(f"## {url} ({len(t)} chars)")
seen = 0
for m in re.finditer(pat, t, re.I):
    if m.start() < seen: continue
    s, e = max(0, m.start()-160), min(len(t), m.end()+220)
    print("…", re.sub(r"\s+", " ", t[s:e]), "…"); seen = e
    if seen and t[:seen].count("…") > 40: break
