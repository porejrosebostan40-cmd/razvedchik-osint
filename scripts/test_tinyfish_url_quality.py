import json
import os
import re
import sys
from urllib.parse import urlparse

import requests

URL = "https://api.search.tinyfish.ai"
REGION = "РСО–Алания"
QUERIES = [
    f"мобилизация заключенных ФСИН {REGION}",
    f"ФСИН {REGION} новости",
    f"site:fsin.gov.ru {REGION} заключенные",
]
RESULTS_PER_QUERY = 6
HTTP_TIMEOUT = 15

URL_RE = re.compile(r"https?://[^\\s<>\"]+")


def search(key: str, query: str):
    return requests.get(
        URL,
        headers={"X-API-Key": key},
        params={"query": query, "location": "RU", "language": "ru"},
        timeout=30,
    )


def normalize_url(value):
    if not isinstance(value, str):
        return None
    value = value.strip().rstrip(").,;")
    if not value.startswith(("http://", "https://")):
        return None
    return value


def url_kind(value):
    url = normalize_url(value)
    if not url:
        return "INVALID"
    parsed = urlparse(url)
    path = (parsed.path or "").rstrip("/")
    if not path or path == "":
        return "HOME"
    return "SPECIFIC"


def html_title(text):
    match = re.search(r"<title[^>]*>(.*?)</title>", text or "", re.I | re.S)
    if not match:
        return None
    return re.sub(r"\\s+", " ", re.sub(r"<[^>]+>", "", match.group(1))).strip()[:300]


def extract_urls(text):
    if not text:
        return []
    out = []
    for raw in URL_RE.findall(text):
        url = normalize_url(raw)
        if url and url not in out:
            out.append(url)
    return out


def inspect_url(url):
    url = normalize_url(url)
    if not url:
        return {"status": "INVALID"}

    try:
        response = requests.get(
            url,
            allow_redirects=True,
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 TinyFish-URL-quality-test"},
        )
        final_url = response.url
        return {
            "status": response.status_code,
            "final_url": final_url,
            "redirect": final_url != url,
            "final_kind": url_kind(final_url),
            "html_title": html_title(response.text[:500000]),
            "content_type": response.headers.get("content-type"),
        }
    except requests.RequestException as exc:
        return {"status": "ERROR", "error": str(exc)[:300]}


def main() -> int:
    key = os.environ.get("TINYFISH_API_KEY")
    if not key:
        print("TINYFISH_API_KEY missing")
        return 1

    all_rows = []
    failures = 0

    for query in QUERIES:
        print("\n" + "=" * 90)
        print(f"QUERY: {query}")
        response = search(key, query)
        print(f"SEARCH_HTTP: {response.status_code}")

        if response.status_code != 200:
            print(f"BODY: {response.text[:2000]}")
            failures += 1
            continue

        try:
            data = response.json()
        except ValueError:
            print("SEARCH_JSON: INVALID")
            print(response.text[:3000])
            failures += 1
            continue

        results = data.get("results", [])
        print(f"TOTAL_RESULTS: {data.get('total_results')}")
        print(f"RETURNED: {len(results) if isinstance(results, list) else 'NOT_LIST'}")

        if not isinstance(results, list):
            failures += 1
            continue

        for i, item in enumerate(results[:RESULTS_PER_QUERY], 1):
            title = item.get("title")
            result_url = normalize_url(item.get("url"))
            site = item.get("site_name")
            snippet = item.get("snippet") or ""
            embedded_urls = extract_urls(f"{title or ''} {snippet}")
            other_urls = [u for u in embedded_urls if u != result_url]

            print(f"\n[{i}]")
            print(f"title: {title}")
            print(f"url: {result_url}")
            print(f"site_name: {site}")
            print(f"date: {item.get('date')}")
            print(f"publisher: {item.get('publisher')}")
            print(f"url_kind: {url_kind(result_url)}")
            print(f"other_urls_in_title_or_snippet: {other_urls[:5]}")
            print(f"snippet: {snippet[:300]}")

            inspection = inspect_url(result_url)
            print(f"http_status: {inspection.get('status')}")
            print(f"final_url: {inspection.get('final_url')}")
            print(f"redirect: {inspection.get('redirect')}")
            print(f"final_url_kind: {inspection.get('final_kind')}")
            print(f"html_title: {inspection.get('html_title')}")
            print(f"content_type: {inspection.get('content_type')}")
            if inspection.get("error"):
                print(f"http_error: {inspection['error']}")

            row = {
                "query": query,
                "title": title,
                "url": result_url,
                "site_name": site,
                "date": item.get("date"),
                "publisher": item.get("publisher"),
                "url_kind": url_kind(result_url),
                "other_urls": other_urls[:5],
                "inspection": inspection,
            }
            all_rows.append(row)

    print("\n" + "=" * 90)
    print("SUMMARY")

    total = len(all_rows)
    home = sum(r["url_kind"] == "HOME" for r in all_rows)
    specific = sum(r["url_kind"] == "SPECIFIC" for r in all_rows)
    invalid = sum(r["url_kind"] == "INVALID" for r in all_rows)
    redirects = sum(bool(r["inspection"].get("redirect")) for r in all_rows)
    final_home = sum(r["inspection"].get("final_kind") == "HOME" for r in all_rows)
    final_specific = sum(r["inspection"].get("final_kind") == "SPECIFIC" for r in all_rows)
    embedded = sum(bool(r["other_urls"]) for r in all_rows)
    date_present = sum(r["date"] is not None for r in all_rows)
    publisher_present = sum(r["publisher"] is not None for r in all_rows)

    print(f"RESULTS_INSPECTED: {total}")
    print(f"RESULT_URL_HOME: {home}")
    print(f"RESULT_URL_SPECIFIC: {specific}")
    print(f"RESULT_URL_INVALID: {invalid}")
    print(f"REDIRECTS: {redirects}")
    print(f"FINAL_URL_HOME: {final_home}")
    print(f"FINAL_URL_SPECIFIC: {final_specific}")
    print(f"RESULTS_WITH_OTHER_URL_IN_TITLE_OR_SNIPPET: {embedded}")
    print(f"DATE_PRESENT: {date_present}")
    print(f"PUBLISHER_PRESENT: {publisher_present}")

    with open("tinyfish_url_quality.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "queries": QUERIES,
                "results_inspected": all_rows,
                "summary": {
                    "results_inspected": total,
                    "result_url_home": home,
                    "result_url_specific": specific,
                    "result_url_invalid": invalid,
                    "redirects": redirects,
                    "final_url_home": final_home,
                    "final_url_specific": final_specific,
                    "results_with_other_url": embedded,
                    "date_present": date_present,
                    "publisher_present": publisher_present,
                    "search_failures": failures,
                },
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    if total == 0 or failures == len(QUERIES):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
