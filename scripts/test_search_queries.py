# scripts/test_search_queries.py
# Изолированный диагностический тест трёх Bing-запросов.
# НЕ влияет на production. НЕ изменяет search.py.

import json
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from riskwatch.config import SETTINGS
from riskwatch.search import HEADERS, _clean, _matches_site

QUERIES = [
    ("A", "site:gov.ru ФСИН колония осужден"),
    ("B", "ФСИН колония осужден gov.ru"),
    ("C", "ФСИН колония осужден"),
]

TARGETS = ("gov.ru",)
RESULTS_PATH = Path("/tmp/test_search_queries_result.json")

results = {}

for label, query in QUERIES:
    url = "https://www.bing.com/search?q=" + quote_plus(query)
    print(f"=== QUERY {label} ===")
    print(f"[QUERY] {query}")
    print(f"[URL] {url}")

    entry = {
        "label": label,
        "query": query,
        "url": url,
    }

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=SETTINGS.request_timeout,
            allow_redirects=True,
        )
        html = r.text
        soup = BeautifulSoup(html, "html.parser")
        anchors = soup.select("li.b_algo h2 a")

        print(f"[STATUS] {r.status_code}")
        print(f"[FINAL_URL] {r.url}")
        print(f"[CONTENT_TYPE] {r.headers.get('Content-Type', '')}")
        print(f"[SIZE] {len(html)} bytes")
        print(f"[ANCHORS] {len(anchors)}")

        samples = []
        gov_urls = []

        for i, a in enumerate(anchors):
            raw_href = str(a.get("href", ""))
            clean_href = _clean(raw_href)
            site_match = _matches_site(clean_href, TARGETS)
            if "gov.ru" in clean_href.lower():
                gov_urls.append(clean_href)

            node = a.find_parent("li", class_="b_algo")
            title = a.get_text(" ", strip=True)
            snippet = ""
            if node:
                sn = node.select_one(".b_caption p")
                if sn:
                    snippet = sn.get_text(" ", strip=True)

            print(f"[{i}] RAW: {raw_href}")
            print(f"    CLEAN: {clean_href}")
            print(f"    SITE_MATCH: {site_match}")

            if i < 5:
                print(f"    TITLE: {title[:200]}")
                print(f"    SNIPPET: {snippet[:300]}")
                samples.append({
                    "raw_href": raw_href,
                    "url": clean_href,
                    "site_match": site_match,
                    "title": title,
                    "snippet": snippet,
                })

        print(f"[GOV_RU_URLS] {len(gov_urls)}")
        for u in gov_urls[:20]:
            print(f"  {u}")
        print()

        entry.update({
            "status": r.status_code,
            "final_url": r.url,
            "content_type": r.headers.get("Content-Type", ""),
            "size": len(html),
            "anchor_count": len(anchors),
            "gov_ru_url_count": len(gov_urls),
            "gov_ru_urls": gov_urls[:20],
            "samples": samples,
        })

        Path(f"/tmp/test_search_queries_{label}.html").write_text(
            html, encoding="utf-8"
        )

    except requests.RequestException as exc:
        print(f"[ERROR] {exc}")
        entry["error"] = str(exc)

    results[label] = entry

RESULTS_PATH.write_text(
    json.dumps(
        {
            "targets": TARGETS,
            "timeout": SETTINGS.request_timeout,
            "queries": results,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print(f"[DONE] {RESULTS_PATH}")
