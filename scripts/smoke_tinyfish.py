import json
import os
import sys

import requests

REGION = sys.argv[1] if len(sys.argv) > 1 else "РСО–Алания"
QUERY = f"мобилизация заключенных ФСИН {REGION}"


def main() -> int:
    key = os.environ.get("TINYFISH_API_KEY")
    if not key:
        print("TINYFISH_API_KEY missing")
        return 1

    r = requests.get(
        "https://api.search.tinyfish.ai",
        headers={"X-API-Key": key},
        params={
            "query": QUERY,
            "location": "RU",
            "language": "ru",
        },
        timeout=30,
    )

    print(f"HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"BODY: {r.text[:2000]}")
        return 1

    try:
        data = r.json()
    except ValueError:
        print(f"BODY: {r.text[:5000]}")
        return 1

    results = data.get("results", [])
    if not isinstance(results, list):
        print("DEBUG: results is not an array")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:5000])
        return 1

    print(f"QUERY: {data.get('query')}")
    print(f"TOTAL_RESULTS: {data.get('total_results')}")
    print(f"PAGE: {data.get('page')}")
    print(f"RESULT_COUNT: {len(results)}")

    for i, item in enumerate(results[:10], 1):
        print("---")
        print(f"title: {item.get('title')}")
        print(f"url:   {item.get('url')}")
        print(f"site:  {item.get('site_name')}")
        print(f"date:  {item.get('date')}")
        print(f"snip:  {(item.get('snippet') or '')[:120]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
