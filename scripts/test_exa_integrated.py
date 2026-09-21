import json
from riskwatch.search import search

QUERIES = [
    'site:gov.ru ФСИН колония осужден',
    'ФСИН колония осужден gov.ru',
    'ФСИН колония осужден',
    'УФСИН РСО-Алания 2026',
    'site:fsin.gov.ru "УФСИН" "Северная Осетия — Алания"',
]

out = {}
for q in QUERIES:
    result = search(q, limit=10)
    out[q] = {
        "count": len(result),
        "items": list(result),
        "telemetry": getattr(result, "telemetry", {}),
    }
    print("\n===", q, "===")
    print("COUNT:", len(result))
    print("TELEMETRY:", getattr(result, "telemetry", {}))
    for i, item in enumerate(result[:5], 1):
        print(i, item.get("title"), item.get("url"))

with open("/tmp/exa_integrated_smoke.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
