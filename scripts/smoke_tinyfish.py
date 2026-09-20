import json
import os
import sys

import requests


def main() -> int:
    key = os.environ.get("TINYFISH_API_KEY")
    if not key:
        print("TINYFISH_API_KEY missing")
        return 1

    r = requests.get(
        "https://api.search.tinyfish.ai",
        headers={"X-API-Key": key},
        params={
            "query": "мобилизация заключенных ФСИН",
            "location": "RU",
            "language": "ru",
            "include_domains": "mil.ru",
            "purpose": "Проверка официальных российских источников по теме мобилизации заключенных.",
        },
        timeout=30,
    )

    print(f"HTTP {r.status_code}")
    print(f"CONTENT_TYPE {r.headers.get('content-type', '')}")

    try:
        data = r.json()
    except ValueError:
        print(r.text[:5000])
        return 1 if r.status_code != 200 else 2

    print(json.dumps(data, ensure_ascii=False, indent=2)[:10000])

    if r.status_code != 200:
        return 1

    results = data.get("results")
    if not isinstance(results, list):
        print("DEBUG invalid results type")
        return 2

    print(f"RESULT_COUNT {len(results)}")
    for i, item in enumerate(results, 1):
        print(
            f"RESULT {i}: "
            f"site={item.get('site_name')} "
            f"url={item.get('url')} "
            f"title={item.get('title')!r}"
        )

    bad_domains = [
        item.get("url", "")
        for item in results
        if "mil.ru" not in item.get("url", "")
    ]
    print(f"NON_MIL_URL_COUNT {len(bad_domains)}")
    if bad_domains:
        print("NON_MIL_URLS", json.dumps(bad_domains, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
