# scripts/test_retrieval_sources.py
# Изолированный диагностический тест retrieval-источников.
# НЕ влияет на production. НЕ изменяет search.py.

import json
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from riskwatch.config import SETTINGS
from riskwatch.search import HEADERS, _clean

QUERY = "ФСИН колония осужден"
RESULTS_PATH = Path("/tmp/test_retrieval_sources_result.json")

SOURCES = [
    ("DuckDuckGo HTML", f"https://html.duckduckgo.com/html/?q={quote_plus(QUERY)}"),
    ("DuckDuckGo Lite", f"https://lite.duckduckgo.com/lite/?q={quote_plus(QUERY)}"),
    ("Bing HTML", f"https://www.bing.com/search?q={quote_plus(QUERY)}"),
    ("Google HTML", f"https://www.google.com/search?q={quote_plus(QUERY)}&hl=ru&gl=RU"),
    ("Yandex HTML", f"https://yandex.ru/search/?text={quote_plus(QUERY)}&lr=213"),
]

def parse_links(source, html):
    soup = BeautifulSoup(html, "html.parser")
    anchors = []
    if source == "Bing HTML":
        anchors = soup.select("li.b_algo h2 a")
    elif source == "DuckDuckGo HTML":
        anchors = soup.select(".result a.result__a")
    elif source == "DuckDuckGo Lite":
        anchors = soup.select("a.result-link")
        if not anchors:
            anchors = soup.select("table a[href]")
    elif source == "Google HTML":
        anchors = soup.select("div.MjjYud a[href]")
        if not anchors:
            anchors = soup.select("a[href]")
    elif source == "Yandex HTML":
        anchors = soup.select("a.Link")
        if not anchors:
            anchors = soup.select("a[href]")

    seen = set()
    rows = []
    for a in anchors:
        raw = str(a.get("href", ""))
        clean = _clean(raw)
        if not clean or clean.startswith("#") or clean in seen:
            continue
        seen.add(clean)

        title = a.get_text(" ", strip=True)
        if not title:
            continue

        node = (
            a.find_parent("li", class_="b_algo")
            if source == "Bing HTML"
            else a.parent
        )
        snippet = ""
        if node:
            for selector in (".b_caption p", ".result__snippet", ".snippet", "[data-snippet]"):
                sn = node.select_one(selector) if hasattr(node, "select_one") else None
                if sn:
                    snippet = sn.get_text(" ", strip=True)
                    break

        rows.append({
            "url": clean,
            "title": title,
            "snippet": snippet,
            "gov_ru": "gov.ru" in clean.lower(),
            "fsin": any(x in (clean + " " + title + " " + snippet).lower()
                         for x in ("фсин", "уфсин", "фку", "исправительн", "колони")),
        })
        if len(rows) >= 20:
            break
    return rows

results = {}

for source, url in SOURCES:
    print(f"=== {source} ===")
    print(f"[QUERY] {QUERY}")
    print(f"[URL] {url}")

    entry = {"source": source, "query": QUERY, "url": url}

    try:
        r = requests.get(
            url,
            headers={**HEADERS, "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7"},
            timeout=SETTINGS.request_timeout,
            allow_redirects=True,
        )
        html = r.text
        rows = parse_links(source, html)
        relevant = [x for x in rows if x["fsin"]]
        gov = [x for x in rows if x["gov_ru"]]

        print(f"[STATUS] {r.status_code}")
        print(f"[FINAL_URL] {r.url}")
        print(f"[CONTENT_TYPE] {r.headers.get('Content-Type', '')}")
        print(f"[SIZE] {len(html)} bytes")
        print(f"[RESULTS] {len(rows)}")
        print(f"[GOV_RU] {len(gov)}")
        print(f"[FSIN_RELEVANT] {len(relevant)}")

        for i, row in enumerate(rows[:5]):
            print(f"[{i}] URL: {row['url']}")
            print(f"    TITLE: {row['title'][:200]}")
            print(f"    SNIPPET: {row['snippet'][:300]}")
            print(f"    GOV_RU: {row['gov_ru']} FSIN_RELEVANT: {row['fsin']}")

        entry.update({
            "status": r.status_code,
            "final_url": r.url,
            "content_type": r.headers.get("Content-Type", ""),
            "size": len(html),
            "result_count": len(rows),
            "gov_ru_count": len(gov),
            "fsin_relevant_count": len(relevant),
            "samples": rows[:5],
        })
        Path(f"/tmp/test_retrieval_{source.split()[0].lower()}_{source.split()[1].lower() if len(source.split()) > 1 else 'html'}.html").write_text(
            html, encoding="utf-8"
        )

    except requests.RequestException as exc:
        print(f"[ERROR] {exc}")
        entry["error"] = str(exc)

    results[source] = entry
    print()

RESULTS_PATH.write_text(
    json.dumps(
        {"query": QUERY, "timeout": SETTINGS.request_timeout, "sources": results},
        ensure_ascii=False, indent=2,
    ),
    encoding="utf-8",
)
print(f"[DONE] {RESULTS_PATH}")
