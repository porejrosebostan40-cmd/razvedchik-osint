import json, os, re, subprocess, sys
from urllib.parse import urlparse

import requests

QUERIES = [
    ("Q1", "мобилизация заключенных ФСИН РСО-Алания"),
    ("Q2", "военный комиссариат РСО-Алания заключенные"),
    ("Q3", "ФСИН РСО-Алания Минобороны военный учет заключенных"),
]

def classify(url):
    try:
        p = urlparse(url)
        path = (p.path or "").strip("/")
        if not path:
            return "home"
        # PDF/doc/article paths and common CMS paths are specific pages.
        return "specific"
    except Exception:
        return "invalid"

def exa_search(query):
    key = os.environ.get("EXA_API_KEY")
    if not key:
        raise RuntimeError("EXA_API_KEY is missing")
    r = requests.post(
        "https://api.exa.ai/search",
        headers={"x-api-key": key, "Content-Type": "application/json"},
        json={
            "query": query,
            "type": "auto",
            "numResults": 10,
            "contents": {"highlights": True},
        },
        timeout=60,
    )
    print("EXA_HTTP", r.status_code)
    r.raise_for_status()
    return r.json()

def main():
    if not os.environ.get("EXA_API_KEY"):
        print("EXA_API_KEY is missing in GitHub Actions secrets", file=sys.stderr)
        raise SystemExit(2)

    from riskwatch.search import search

    report = {"queries": []}
    for qid, query in QUERIES:
        print("\n===", qid, query, "===")
        exa = exa_search(query)
        exa_results = exa.get("results") or []
        exa10 = exa_results[:10]

        cur = search(query, limit=10)
        cur10 = list(cur)[:10]

        def metrics(items):
            valid = [x for x in items if isinstance(x, dict) and x.get("url")]
            domains = []
            for x in valid:
                try:
                    domains.append(urlparse(x["url"]).netloc.lower().removeprefix("www."))
                except Exception:
                    pass
            return {
                "results": len(valid),
                "specific": sum(classify(x["url"]) == "specific" for x in valid),
                "home": sum(classify(x["url"]) == "home" for x in valid),
                "date": sum(bool(x.get("publishedDate") or x.get("published_date")) for x in valid),
                "author": sum(bool(x.get("author")) for x in valid),
                "domains": domains,
                "urls": [x["url"] for x in valid],
            }

        em = metrics(exa10)
        sm = metrics(cur10)
        telem = getattr(cur, "telemetry", {})

        print("EXA", json.dumps(em, ensure_ascii=False))
        print("SEARCH", json.dumps(sm, ensure_ascii=False))
        print("SEARCH_TELEMETRY", json.dumps(telem, ensure_ascii=False))

        report["queries"].append({
            "id": qid, "query": query,
            "exa": em,
            "search_py": {**sm, "telemetry": telem},
            "exa_raw_count": len(exa_results),
        })

    with open("exa_vs_search_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
