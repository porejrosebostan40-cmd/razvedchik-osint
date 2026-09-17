import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup

from riskwatch.search import _clean, _domain, _extract_results, _matches_site, _site_targets
from riskwatch.config import SETTINGS

QUERY = "site:gov.ru ФСИН колония осужден"
HEADERS = {"User-Agent": "RiskWatch/1.0 (+public-source-monitoring)"}
ENDPOINTS = (
    ("DuckDuckGo", "https://html.duckduckgo.com/html/?q="),
    ("Bing", "https://www.bing.com/search?q="),
)
OUT_DIR = Path("/tmp/riskwatch_site_query")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    targets = _site_targets(QUERY)
    print(f"QUERY={QUERY}")
    print(f"TARGETS={targets!r}")

    for source, endpoint in ENDPOINTS:
        url = endpoint + quote_plus(QUERY)
        print(f"\n=== {source} ===")
        print(f"REQUEST_URL={url}")
        try:
            r = requests.get(
                url,
                headers=HEADERS,
                timeout=SETTINGS.request_timeout,
                allow_redirects=True,
            )
            print(f"STATUS={r.status_code}")
            print(f"FINAL_URL={r.url}")
            print(f"REDIRECT_COUNT={len(r.history)}")
            print(f"HTML_BYTES={len(r.content)}")
            print(f"GOV_RU_IN_HTML={'gov.ru' in r.text.lower()}")
            html_path = OUT_DIR / f"{stamp}_{source.lower()}.html"
            html_path.write_text(r.text, encoding="utf-8", errors="ignore")
            print(f"HTML_FILE={html_path}")
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")
            selectors = (".result a.result__a", "li.b_algo h2 a", "h2 a") if source == "Bing" else (".result a.result__a", ".result h2 a")
            raw = []
            seen_raw = set()
            for selector in selectors:
                for a in soup.select(selector):
                    href = str(a.get("href", ""))
                    key = (href, a.get_text(" ", strip=True))
                    if key not in seen_raw:
                        seen_raw.add(key)
                        raw.append(a)

            matches = []
            for a in raw:
                href = _clean(a.get("href", ""))
                if _matches_site(href, targets):
                    matches.append(a)

            extracted = _extract_results(soup, source, targets, 6)
            print(f"RAW_ANCHORS={len(raw)}")
            print(f"MATCHES_SITE={len(matches)}")
            print(f"EXTRACTED_RESULTS={len(extracted)}")
            for i, a in enumerate(matches[:5], 1):
                print(json.dumps({
                    "n": i,
                    "url": _clean(a.get("href", "")),
                    "title": a.get_text(" ", strip=True),
                }, ensure_ascii=False))
            for i, item in enumerate(extracted[:5], 1):
                print(json.dumps({
                    "extracted": i,
                    "url": item.get("url", ""),
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                }, ensure_ascii=False))
        except requests.RequestException as exc:
            print(f"REQUEST_ERROR={exc!r}")


if __name__ == "__main__":
    main()
