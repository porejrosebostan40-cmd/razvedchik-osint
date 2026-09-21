import json
import os
import re
import time
from urllib.parse import urlparse

import requests

from riskwatch.evidence import build_evidence_graph
from riskwatch.forecast import _has_direct_military_action, _has_target

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


def event_from_exa(item, query_id, query):
    return {
        "query_id": query_id,
        "query": query,
        "url": item.get("url") or "",
        "title": item.get("title") or "",
        "snippet": item.get("highlight") or item.get("snippet") or "",
        "published_date": item.get("publishedDate") or item.get("published_date"),
        "author": item.get("author"),
    }


def event_with_full_text(item, markdown, metadata):
    return {
        **item,
        "title": metadata.get("title") or item.get("title") or "",
        "snippet": markdown,
        "published_date": (
            metadata.get("publishedTime")
            or metadata.get("publishedDate")
            or item.get("published_date")
        ),
        "author": metadata.get("author") or item.get("author"),
    }


def semantic_metrics(events):
    events = list(events or [])
    target = [e for e in events if _has_target(e)]
    direct = [e for e in events if _has_direct_military_action(e)]
    graph = build_evidence_graph(events)
    return {
        "events": len(events),
        "target_events": len(target),
        "direct_action_events": len(direct),
        "root_events": len(direct),
        "graph_nodes": graph["metrics"]["nodes"],
        "graph_edges": graph["metrics"]["edges"],
        "graph_root_nodes": graph["metrics"]["root_nodes"],
        "graph_chain_score": graph["metrics"]["chain_score"],
        "graph": graph,
    }


def scrape(url):
    key = os.environ["FIRECRAWL_API_KEY"]
    started = time.monotonic()
    try:
        r = requests.post(
            FIRECRAWL_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
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
    t = str(markdown or "").lower()
    nav_markers = [
        "cookie",
        "privacy policy",
        "sign in",
        "log in",
        "subscribe",
        "menu",
        "advertisement",
        "all rights reserved",
    ]
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
            urls.append(event_from_exa(item, qid, query))
            if len(urls) >= MAX_URLS:
                break
        if len(urls) >= MAX_URLS:
            break

    rows = []
    snippet_events = []
    full_events = []

    for idx, item in enumerate(urls, 1):
        print(f"SCRAPE {idx}/{len(urls)} {item['url']}")
        result = scrape(item["url"])
        markdown = result.get("markdown") or ""
        meta = result.get("metadata") or {}
        clean = cleanliness(markdown)

        snippet_events.append(item)
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
            **clean,
        }

        if result["status"] == "ok":
            full_event = event_with_full_text(item, markdown, meta)
            full_events.append(full_event)
            row["full_target"] = _has_target(full_event)
            row["full_direct_action"] = _has_direct_military_action(full_event)
        else:
            row["full_target"] = None
            row["full_direct_action"] = None
        rows.append(row)

    snippet_sem = semantic_metrics(snippet_events)
    full_sem = semantic_metrics(full_events)

    ok = [r for r in rows if r["scrape_status"] == "ok"]
    failed = [r for r in rows if r["scrape_status"] != "ok"]

    uplift_target = []
    uplift_direct = []
    for r in ok:
        snippet_event = {
            "url": r["url"],
            "title": r["title"],
            "snippet": r["snippet"],
        }
        if (not _has_target(snippet_event)) and r["full_target"]:
            uplift_target.append(r)
        if (not _has_direct_military_action(snippet_event)) and r["full_direct_action"]:
            uplift_direct.append(r)

    summary = {
        "total_urls": len(rows),
        "scrape_ok": len(ok),
        "scrape_failed": len(failed),
        "scrape_success_rate": round(len(ok) / len(rows) * 100, 1) if rows else 0,
        "snippet": {
            "events": snippet_sem["events"],
            "target_events": snippet_sem["target_events"],
            "direct_action_events": snippet_sem["direct_action_events"],
            "root_events": snippet_sem["root_events"],
            "graph_nodes": snippet_sem["graph_nodes"],
            "graph_edges": snippet_sem["graph_edges"],
            "graph_root_nodes": snippet_sem["graph_root_nodes"],
            "graph_chain_score": snippet_sem["graph_chain_score"],
        },
        "full_text": {
            "events": full_sem["events"],
            "target_events": full_sem["target_events"],
            "direct_action_events": full_sem["direct_action_events"],
            "root_events": full_sem["root_events"],
            "graph_nodes": full_sem["graph_nodes"],
            "graph_edges": full_sem["graph_edges"],
            "graph_root_nodes": full_sem["graph_root_nodes"],
            "graph_chain_score": full_sem["graph_chain_score"],
        },
        "uplift": {
            "new_target_events": len(uplift_target),
            "new_direct_action_events": len(uplift_direct),
            "target_delta": full_sem["target_events"] - snippet_sem["target_events"],
            "direct_action_delta": full_sem["direct_action_events"] - snippet_sem["direct_action_events"],
            "root_delta": full_sem["root_events"] - snippet_sem["root_events"],
            "graph_node_delta": full_sem["graph_nodes"] - snippet_sem["graph_nodes"],
            "graph_root_node_delta": full_sem["graph_root_nodes"] - snippet_sem["graph_root_nodes"],
            "graph_chain_score_delta": full_sem["graph_chain_score"] - snippet_sem["graph_chain_score"],
        },
        "metadata": {
            "date_found_snippet": sum(bool(r.get("published_date")) for r in rows),
            "date_found_firecrawl": sum(bool(r.get("firecrawl_published_date")) for r in ok),
            "author_found_snippet": sum(bool(r.get("author")) for r in rows),
            "author_found_firecrawl": sum(bool(r.get("firecrawl_author")) for r in ok),
        },
        "cleanliness": {
            "avg_markdown_kb_ok": round(sum(r["markdown_kb"] for r in ok) / len(ok), 2) if ok else 0,
            "avg_nav_marker_hits_ok": round(sum(r["nav_marker_hits"] for r in ok) / len(ok), 2) if ok else 0,
            "avg_headings_ok": round(sum(r["headings"] for r in ok) / len(ok), 2) if ok else 0,
            "avg_paragraph_blocks_ok": round(sum(r["paragraph_blocks"] for r in ok) / len(ok), 2) if ok else 0,
        },
        "failed_domains": sorted({r["domain"] for r in failed}),
    }

    report = {
        "queries": QUERIES,
        "summary": summary,
        "rows": rows,
        "snippet_graph": snippet_sem["graph"],
        "full_text_graph": full_sem["graph"],
    }
    with open("firecrawl_benchmark_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\nSUMMARY")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
