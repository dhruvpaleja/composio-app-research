import sys, re, json
sys.path.insert(0,'.')
from agent import tools
for q in sys.argv[1:]:
    print(f"\n##### {q}")
    for r in tools.web_search(q, max_results=4):
        sn = re.sub(r"\s+"," ", r['snippet'])[:420]
        print(f"- {r['url']}\n    {sn}")
