import json
import os
import re
import time
from urllib.parse import urlparse

import requests

from riskwatch.forecast import ACTION_TERMS, NEGATIVE_TERMS, TARGET_TERMS, _is_negative

QUERIES = [
    ("Q1", "мобилизация заключенных ФСИН РСО-Алания"),
    ("Q2", "военный комиссариат РСО-Алания заключенные"),
    ("Q3", "ФСИН РСО-Алания Минобороны военный учет заключенных"),
]

EXA_URL = "https://api.exa.ai/search"
FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"
MAX_PER_QUERY = 10
MAX_URLS = 30


def exa_search(query):
    key = os.environ["EXA_API_KEY"]
    r = requests.post(
        EXA_URL,
        headers={"x-api-key": key, "Content-Type": "application/json"},
        json={
            "query": query,
            "type": "auto",
            "numResults": MAX_PER_QUERY,
            "contents": {"highlights": True},
        },
        timeout=60,
    )
    print("EXA_HTTP", r.status_code)
    r.raise_for_status()
    return r.json().get("results") or []


def norm(text):
    return str(text or "").lower()


def has_target_text(text):
    t = norm(text)
    return any(term in t for term in TARGET_TERMS)


def has_action_text(text):
    t = norm(text)
    return has_target_text(t) and any(term in t for term in ACTION_TERMS) and not any(term in t for term in NEGATIVE_TERMS)


def exa_event_match(item):
    text = f"{item.get('title','')} {item.get('highlight','')} {item.get('snippet','')}"
    return has_target_text(text), has_action_text(text)


def scrape(url):
    key = os.environ["FIRECRAWL_API_KEY"]
    started = time.monotonic()
    try:
        r = requests.post(
            FIRECRAWL_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": True,
            },
            timeout=90,
        )
        elapsed_ms = round((time.monotonic() - started) * 1000)
        payload = r.json()
        if not r.ok:
            return {
                "status": "failed",
                "http_status": r.status_code,
                "elapsed_ms": elapsed_ms,
                "error": payload.get("error") or payload.get("message") or str(payload)[:500],
            }
        data = payload.get("data") or {}
        markdown = data.get("markdown") or ""
        metadata = data.get("metadata") or {}
        return {
            "status": "ok" if payload.get("success", True) and markdown else "failed",
            "http_status": r.status_code,
            "elapsed_ms": elapsed_ms,
            "markdown": markdown,
            "metadata": metadata,
            "error": None if markdown else "empty_markdown",
        }
    except requests.RequestException as exc:
        return {
            "status": "failed",
            "http_status": None,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "error": f"{type(exc).__name__}: {exc}",
        }
    except ValueError as exc:
        return {
            "status": "failed",
            "http_status": r.status_code if "r" in locals() else None,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "error": f"invalid_json: {exc}",
        }


def cleanliness(markdown):
    t = norm(markdown)
    nav_markers = ["cookie", "privacy policy", "sign in", "log in", "subscribe", "menu", "advertisement", "all rights reserved"]
    nav_hits = sum(1 for x in nav_markers if x in t)
    headings = len(re.findall(r"(?m)^#{1,6}\s+", markdown or ""))
    paragraphs = len([x for x in re.split(r"\n\s*\n", markdown or "") if x.strip()])
    return {
        "nav_marker_hits": nav_hits,
        "headings": headings,
        "paragraph_blocks": paragraphs,
    }


def main():
    for name in ("EXA_API_KEY", "FIRECRAWL_API_KEY"):
        if not os.environ.get(name):
            raise SystemExit(f"{name} is missing in GitHub Actions secrets")

    urls = []
    seen = set()
    for qid, query in QUERIES:
        for item in exa_search(query)[:MAX_PER_QUERY]:
            url = item.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            target, action = exa_event_match(item)
            urls.append({
                "query_id": qid,
                "query": query,
                "url": url,
                "domain": urlparse(url).netloc.lower().removeprefix("www."),
                "title": item.get("title") or "",
                "snippet": item.get("highlight") or item.get("snippet") or "",
                "published_date": item.get("publishedDate") or item.get("published_date"),
                "author": item.get("author"),
                "exa_target": target,
                "exa_action": action,
            })
            if len(urls) >= MAX_URLS:
                break
        if len(urls) >= MAX_URLS:
            break

    rows = []
    for idx, item in enumerate(urls, 1):
        print(f"SCRAPE {idx}/{len(urls)} {item['url']}")
        result = scrape(item["url"])
        markdown = result.get("markdown") or ""
        meta = result.get("metadata") or {}
        clean = cleanliness(markdown)
        full_text = f"{meta.get('title','')}\n{markdown}"
        row = {
            **item,
            "scrape_status": result["status"],
            "http_status": result["http_status"],
            "elapsed_ms": result["elapsed_ms"],
            "error": result["error"],
            "markdown_chars": len(markdown),
            "markdown_kb": round(len(markdown.encode("utf-8")) / 1024, 2),
            "firecrawl_title": meta.get("title"),
            "firecrawl_published_date": meta.get("publishedTime") or meta.get("publishedDate"),
            "firecrawl_author": meta.get("author"),
            "firecrawl_target": has_target_text(full_text),
            "firecrawl_action": has_action_text(full_text),
            **clean,
        }
        rows.append(row)

    ok = [r for r in rows if r["scrape_status"] == "ok"]
    failed = [r for r in rows if r["scrape_status"] != "ok"]
    summary = {
        "total_urls": len(rows),
        "scrape_ok": len(ok),
        "scrape_failed": len(failed),
        "date_found_exa": sum(bool(r.get("published_date")) for r in rows),
        "date_found_firecrawl": sum(bool(r.get("firecrawl_published_date")) for r in ok),
        "author_found_exa": sum(bool(r.get("author")) for r in rows),
        "author_found_firecrawl": sum(bool(r.get("firecrawl_author")) for r in ok),
        "target_events_with_snippet": sum(bool(r["exa_target"]) for r in rows),
        "target_events_with_full_text": sum(bool(r["firecrawl_target"]) for r in ok),
        "action_events_with_snippet": sum(bool(r["exa_action"]) for r in rows),
        "action_events_with_full_text": sum(bool(r["firecrawl_action"]) for r in ok),
        "new_target_positives": sum((not r["exa_target"]) and r["firecrawl_target"] for r in ok),
        "new_action_positives": sum((not r["exa_action"]) and r["firecrawl_action"] for r in ok),
        "avg_markdown_kb_ok": round(sum(r["markdown_kb"] for r in ok) / len(ok), 2) if ok else 0,
        "domains_failed": sorted({r["domain"] for r in failed}),
    }
    report = {"queries": QUERIES, "summary": summary, "rows": rows}
    with open("firecrawl_benchmark_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\nSUMMARY")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
