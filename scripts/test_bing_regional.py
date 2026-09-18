# scripts/test_bing_regional.py
# Изолированный диагностический тест Bing по двум региональным запросам.
# НЕ влияет на production. НЕ изменяет search.py.

import json
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from riskwatch.config import SETTINGS
from riskwatch.search import HEADERS, _clean

QUERIES = [
    'site:gov.ru "Северная Осетия" ФСИН колония осужден',
    '"Северная Осетия" ФСИН колония осужден',
]

RESULTS_PATH = Path("/tmp/test_bing_regional_result.json")


def has_region(text):
    value = str(text or "").lower()
    return "северная осетия" in value or "северной осетии" in value


def has_fsin_term(text):
    value = str(text or "").lower()
    return any(
        term in value
        for term in ("фсин", "уфсин", "фку", "исправительн", "колони")
    )


def parse_bing(html):
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.select("li.b_algo h2 a")

    rows = []
    seen = set()

    for a in anchors:
        raw = str(a.get("href", ""))
        clean = _clean(raw)
        if not clean or clean in seen:
            continue
        seen.add(clean)

        node = a.find_parent("li", class_="b_algo")
        title = a.get_text(" ", strip=True)
        snippet = ""

        if node:
            sn = node.select_one(".b_caption p")
            if sn:
                snippet = sn.get_text(" ", strip=True)

        combined = f"{title} {snippet}"

        rows.append({
            "raw_href": raw,
            "clean_url": clean,
            "gov_ru": "gov.ru" in clean.lower(),
            "region_in_title_or_snippet": has_region(combined),
            "fsin_in_title_or_snippet": has_fsin_term(combined),
            "title": title,
            "snippet": snippet,
        })

    return anchors, rows


results = {}

for query in QUERIES:
    print("=" * 80)
    print(f"[QUERY] {query}")

    url = "https://www.bing.com/search?q=" + quote_plus(query)
    print(f"[URL] {url}")
    print(f"[TIMEOUT] {SETTINGS.request_timeout}")

    entry = {
        "query": query,
        "url": url,
    }

    try:
        r = requests.get(
            url,
            headers={
                **HEADERS,
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
            },
            timeout=SETTINGS.request_timeout,
            allow_redirects=True,
        )

        html = r.text
        anchors, rows = parse_bing(html)

        gov_rows = [x for x in rows if x["gov_ru"]]
        region_rows = [x for x in rows if x["region_in_title_or_snippet"]]
        fsin_rows = [x for x in rows if x["fsin_in_title_or_snippet"]]
        region_fsin_rows = [
            x for x in rows
            if x["region_in_title_or_snippet"] and x["fsin_in_title_or_snippet"]
        ]

        print(f"[STATUS] {r.status_code}")
        print(f"[FINAL_URL] {r.url}")
        print(f"[CONTENT_TYPE] {r.headers.get('Content-Type', '')}")
        print(f"[SIZE] {len(html)} bytes")
        print(f"[ANCHORS] {len(anchors)}")
        print(f"[PARSED_ROWS] {len(rows)}")
        print(f"[GOV_RU_FINAL_URLS] {len(gov_rows)}")
        print(f"[REGION_IN_TITLE_SNIPPET] {len(region_rows)}")
        print(f"[FSIN_IN_TITLE_SNIPPET] {len(fsin_rows)}")
        print(f"[REGION_AND_FSIN] {len(region_fsin_rows)}")

        print("[SAMPLES] first 5 parsed results:")
        for i, row in enumerate(rows[:5]):
            print(f"[{i}] raw_href={row['raw_href']}")
            print(f"    clean_url={row['clean_url']}")
            print(f"    gov_ru={row['gov_ru']}")
            print(
                f"    region={row['region_in_title_or_snippet']} "
                f"fsin={row['fsin_in_title_or_snippet']}"
            )
            print(f"    title={row['title'][:250]}")
            print(f"    snippet={row['snippet'][:400]}")

        entry.update({
            "status": r.status_code,
            "final_url": r.url,
            "content_type": r.headers.get("Content-Type", ""),
            "size": len(html),
            "anchor_count": len(anchors),
            "parsed_count": len(rows),
            "gov_ru_count": len(gov_rows),
            "region_in_title_snippet_count": len(region_rows),
            "fsin_in_title_snippet_count": len(fsin_rows),
            "region_and_fsin_count": len(region_fsin_rows),
            "samples": rows[:5],
        })

        slug = "site" if query.startswith("site:") else "control"
        Path(f"/tmp/test_bing_regional_{slug}.html").write_text(
            html, encoding="utf-8"
        )

    except requests.RequestException as exc:
        print(f"[ERROR] {exc}")
        entry["error"] = str(exc)

    results[query] = entry
    print()

RESULTS_PATH.write_text(
    json.dumps(
        {
            "timeout": SETTINGS.request_timeout,
            "queries": results,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print(f"[DONE] {RESULTS_PATH}")
