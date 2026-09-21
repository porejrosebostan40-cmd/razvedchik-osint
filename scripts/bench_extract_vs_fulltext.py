import json
import os
import re
import time
from urllib.parse import urlparse

import requests

from riskwatch.evidence import build_evidence_graph
from riskwatch.forecast import (
    _has_direct_military_action,
    _has_target,
    _is_negative,
    _text,
)

QUERIES = [
    ("Q1", "мобилизация заключенных ФСИН РСО-Алания"),
    ("Q2", "военный комиссариат РСО-Алания заключенные"),
    ("Q3", "ФСИН РСО-Алания Минобороны военный учет заключенных"),
]

EXA_URL = "https://api.exa.ai/search"
FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"
MAX_PER_QUERY = 5
MAX_URLS = 15
MAX_EXTRACT_CHARS = 1800

TARGET_TERMS = (
    "осужден", "осуждён", "заключен", "заключён", "заключенн",
    "исправительн", "колони", "мест лишения свободы", "фсин",
    "уфсин", "фку", "содержащихся",
)
ACTION_TERMS = (
    "мобилиз", "привлеч", "военн", "контракт", "зачислен",
    "направлен", "отправлен", "призван", "служб", "отбор",
    "медицин", "список", "учет", "учёт", "квот", "транспорт",
)
MILITARY_ANCHORS = (
    "мобилиз", "военн", "военком", "военнослуж", "арм", "сво",
    "вооружен", "вооружён", "министерств оборон", "минобороны",
    "вооруженные силы", "вооружённые силы",
)

SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+|(?<=; )(?=[А-ЯЁ])")


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


def split_sentences(markdown):
    text = re.sub(r"(?m)^#{1,6}\s*", "", markdown or "")
    text = re.sub(r"\[([^\]]+)\]\((?:https?://|/)[^)]*\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return [s.strip(" \\t-•*") for s in SENTENCE_RE.split(text) if s.strip()]


def term_hit(sentence, terms):
    t = sentence.lower()
    return any(term in t for term in terms)


def extract_relevant(markdown):
    sentences = split_sentences(markdown)
    selected = []
    seen = set()

    for sentence in sentences:
        low = sentence.lower()
        has_target = term_hit(sentence, TARGET_TERMS)
        has_action = term_hit(sentence, ACTION_TERMS)
        has_anchor = term_hit(sentence, MILITARY_ANCHORS)
        negative = _is_negative({"title": "", "snippet": sentence})

        # Option D: negation is evidence metadata, not an extraction filter.
        if not has_target or not has_action:
            continue

        key = low
        if key in seen:
            continue
        seen.add(key)
        selected.append(
            {
                "text": sentence,
                "target": has_target,
                "action": has_action,
                "military_anchor": has_anchor,
                "has_negative": negative,
            }
        )

    parts = [x["text"] for x in selected]
    extracted = " ".join(parts)
    if len(extracted) > MAX_EXTRACT_CHARS:
        extracted = extracted[:MAX_EXTRACT_CHARS].rsplit(" ", 1)[0]

    return {
        "snippet": extracted,
        "sentences_total": len(sentences),
        "sentences_selected": len(selected),
        "selected": selected,
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
    extracted_events = []

    for idx, item in enumerate(urls, 1):
        time.sleep(8.0)
        print(f"EXTRACT {idx}/{len(urls)} {item['url']}")
        result = scrape(item["url"])
        retries = 0
        while result.get("http_status") == 429 and retries < 3:
            wait_s = 15 * (2 ** retries)
            print(f"RATE_LIMIT retry={retries + 1} wait={wait_s}s")
            time.sleep(wait_s)
            result = scrape(item["url"])
            retries += 1
        markdown = result.get("markdown") or ""
        meta = result.get("metadata") or {}

        snippet_events.append(item)
        row = {
            **item,
            "scrape_status": result["status"],
            "http_status": result["http_status"],
            "error": result["error"],
            "full_chars": len(markdown),
        }

        if result["status"] == "ok":
            full_event = {
                **item,
                "title": meta.get("title") or item.get("title") or "",
                "snippet": markdown,
                "published_date": (
                    meta.get("publishedTime")
                    or meta.get("publishedDate")
                    or item.get("published_date")
                ),
                "author": meta.get("author") or item.get("author"),
            }
            full_events.append(full_event)

            extracted = extract_relevant(markdown)
            extracted_event = {
                **item,
                "title": meta.get("title") or item.get("title") or "",
                "snippet": extracted["snippet"],
                "published_date": full_event["published_date"],
                "author": full_event["author"],
            }
            extracted_events.append(extracted_event)

            row.update(
                {
                    "full_target": _has_target(full_event),
                    "full_direct_action": _has_direct_military_action(full_event),
                    "extracted_snippet": extracted["snippet"],
                    "sentences_total": extracted["sentences_total"],
                    "sentences_selected": extracted["sentences_selected"],
                    "extracted_target": _has_target(extracted_event),
                    "extracted_direct_action": _has_direct_military_action(extracted_event),
                    "extracted_negative": _is_negative(extracted_event),
                }
            )
        else:
            row.update(
                {
                    "full_target": None,
                    "full_direct_action": None,
                    "extracted_snippet": "",
                    "sentences_total": 0,
                    "sentences_selected": 0,
                    "extracted_target": None,
                    "extracted_direct_action": None,
                    "extracted_negative": None,
                }
            )

        rows.append(row)

    snippet_sem = semantic_metrics(snippet_events)
    full_sem = semantic_metrics(full_events)
    extracted_sem = semantic_metrics(extracted_events)

    ok = [r for r in rows if r["scrape_status"] == "ok"]
    target_recovered = []
    root_recovered = []
    root_lost = []

    for r in ok:
        snippet_event = {"url": r["url"], "title": r["title"], "snippet": r["snippet"]}
        if (not _has_target(snippet_event)) and r["extracted_target"]:
            target_recovered.append(r)
        if (not _has_direct_military_action(snippet_event)) and r["extracted_direct_action"]:
            root_recovered.append(r)
        if _has_direct_military_action(snippet_event) and not r["extracted_direct_action"]:
            root_lost.append(r)

    summary = {
        "total_urls": len(rows),
        "scrape_ok": len(ok),
        "scrape_failed": len(rows) - len(ok),
        "snippet": {k: snippet_sem[k] for k in (
            "events", "target_events", "direct_action_events", "root_events",
            "graph_nodes", "graph_edges", "graph_root_nodes", "graph_chain_score"
        )},
        "full_text": {k: full_sem[k] for k in (
            "events", "target_events", "direct_action_events", "root_events",
            "graph_nodes", "graph_edges", "graph_root_nodes", "graph_chain_score"
        )},
        "extracted": {k: extracted_sem[k] for k in (
            "events", "target_events", "direct_action_events", "root_events",
            "graph_nodes", "graph_edges", "graph_root_nodes", "graph_chain_score"
        )},
        "delta_full_vs_snippet": {
            "target": full_sem["target_events"] - snippet_sem["target_events"],
            "direct_action": full_sem["direct_action_events"] - snippet_sem["direct_action_events"],
            "root_nodes": full_sem["graph_root_nodes"] - snippet_sem["graph_root_nodes"],
        },
        "delta_extracted_vs_snippet": {
            "target": extracted_sem["target_events"] - snippet_sem["target_events"],
            "direct_action": extracted_sem["direct_action_events"] - snippet_sem["direct_action_events"],
            "root_nodes": extracted_sem["graph_root_nodes"] - snippet_sem["graph_root_nodes"],
        },
        "extraction": {
            "target_recovered": len(target_recovered),
            "root_recovered": len(root_recovered),
            "root_lost": len(root_lost),
            "avg_selected_sentences": round(
                sum(r["sentences_selected"] for r in ok) / len(ok), 2
            ) if ok else 0,
        },
        "recovered_target_urls": [r["url"] for r in target_recovered],
        "recovered_root_urls": [r["url"] for r in root_recovered],
        "lost_root_urls": [r["url"] for r in root_lost],
    }

    report = {
        "queries": QUERIES,
        "method": {
            "type": "rule_based_sentence_extraction_option_D",
            "rule": "select target + action sentences regardless of negation; retain has_negative as evidence metadata; run production predicates on extracted compact event",
            "max_chars": MAX_EXTRACT_CHARS,
        },
        "summary": summary,
        "rows": rows,
        "snippet_graph": snippet_sem["graph"],
        "full_text_graph": full_sem["graph"],
        "extracted_graph": extracted_sem["graph"],
    }

    with open("firecrawl_extraction_benchmark_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\nEXTRACTION_SUMMARY")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
