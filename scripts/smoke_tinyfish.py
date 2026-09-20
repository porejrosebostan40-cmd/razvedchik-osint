import json
import os
import sys

import requests

REGION = sys.argv[1] if len(sys.argv) > 1 else "РСО–Алания"
QUERY = f"мобилизация заключенных ФСИН {REGION}"
URL = "https://api.search.tinyfish.ai"


def run_search(key: str, **params):
    return requests.get(
        URL,
        headers={"X-API-Key": key},
        params={"query": QUERY, "location": "RU", "language": "ru", **params},
        timeout=30,
    )


def print_results(label: str, response) -> int:
    print(f"\n=== {label} ===")
    print(f"HTTP {response.status_code}")
    if response.status_code != 200:
        print(f"BODY: {response.text[:2000]}")
        return 1

    try:
        data = response.json()
    except ValueError:
        print(f"BODY: {response.text[:5000]}")
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
        print(f"publisher: {item.get('publisher')}")
        print(f"snip:  {(item.get('snippet') or '')[:160]}")

    return 0


def main() -> int:
    key = os.environ.get("TINYFISH_API_KEY")
    if not key:
        print("TINYFISH_API_KEY missing")
        return 1

    rc = print_results("WITHOUT_DOMAIN_FILTER", run_search(key))
    if rc:
        return rc

    rc = print_results(
        "WITH_MIL_RU_FILTER",
        run_search(key, include_domains="mil.ru"),
    )
    if rc:
        return rc

    return 0


if __name__ == "__main__":
    sys.exit(main())
