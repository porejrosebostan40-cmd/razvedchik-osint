import json, os, re, sys
from urllib.parse import urlparse
import requests

from riskwatch.search import search
from riskwatch.forecast import _has_target, _has_military_anchor, _has_direct_military_action, _has_target_action, _stage, _is_negative, ACTION_TERMS
from riskwatch.evidence import build_evidence_graph

QUERIES = [
    ("Q1", "мобилизация заключенных ФСИН РСО-Алания"),
    ("Q2", "военный комиссариат РСО-Алания заключенные"),
    ("Q3", "ФСИН РСО-Алания Минобороны военный учет заключенных"),
]
SEARCH_ENGINE_DOMAINS = ("duckduckgo.com","bing.com","google.com","yandex.ru","yandex.com")

def domain(url):
    try:
        return urlparse(str(url)).netloc.lower().split(":")[0].removeprefix("www.")
    except ValueError:
        return ""

def usable_url(url):
    d = domain(url)
    return bool(d) and d not in SEARCH_ENGINE_DOMAINS and not any(d.endswith("." + x) for x in SEARCH_ENGINE_DOMAINS)

def normalize_exa(x, query):
    return {
        "url": x.get("url", ""),
        "title": x.get("title", ""),
        "snippet": " ".join((x.get("highlights") or [])[:3]) if isinstance(x.get("highlights"), list) else str(x.get("text","") or "")[:1200],
        "published": x.get("publishedDate", "") or "",
        "author": x.get("author", "") or "",
        "query": query,
        "region": "РСО-Алания",
        "kind": "Exa",
    }

def dedup(items):
    out, seen = [], set()
    for e in items:
        u = e.get("url","")
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(e)
    return out

def metrics(items):
    items = list(items)
    target = [e for e in items if _has_target(e)]
    action = [e for e in target if any(t in (str(e.get("title","")) + " " + str(e.get("snippet",""))).lower() for t in ACTION_TERMS)]
    direct = [e for e in items if _has_direct_military_action(e)]
    return {
        "results": len(items),
        "target_events": len(target),
        "action_events": len(action),
        "direct_root_events": len(direct),
        "negative_events": sum(_is_negative(e) for e in items),
        "stages": sorted(set(_stage(e, items) for e in items if _stage(e, items) > 0)),
    }

def exa_search(query, include_domains=None):
    key = os.environ["EXA_API_KEY"]
    body = {
        "query": query,
        "type": "auto",
        "numResults": 10,
        "contents": {"highlights": {"maxCharacters": 1200}},
    }
    if include_domains:
        body["includeDomains"] = include_domains
    r = requests.post(
        "https://api.exa.ai/search",
        headers={"x-api-key": key, "Content-Type": "application/json"},
        json=body, timeout=60,
    )
    print("EXA_HTTP", r.status_code, "domains=", include_domains or [])
    r.raise_for_status()
    return r.json().get("results") or []

def run():
    if not os.environ.get("EXA_API_KEY"):
        raise SystemExit("EXA_API_KEY missing")
    report = {"queries": [], "domain_control": None}
    for qid, query in QUERIES:
        raw_exa = [normalize_exa(x, query) for x in exa_search(query)]
        exa_valid = [e for e in raw_exa if usable_url(e["url"])]
        exa_unique = dedup(exa_valid)
        exa_m = metrics(exa_unique)

        cur = list(search(query, limit=10))
        search_valid = [e for e in cur if usable_url(e.get("url",""))]
        search_unique = dedup(search_valid)
        search_m = metrics(search_unique)
        graph_exa = build_evidence_graph(exa_unique)
        graph_search = build_evidence_graph(search_unique)

        row = {
            "id": qid,
            "query": query,
            "exa": {**exa_m, "graph_nodes": len(graph_exa.get("nodes", [])), "graph_edges": len(graph_exa.get("edges", [])),
                    "graph_root_nodes": graph_exa.get("metrics",{}).get("root_nodes",0)},
            "search_py": {**search_m, "graph_nodes": len(graph_search.get("nodes", [])), "graph_edges": len(graph_search.get("edges", [])),
                          "graph_root_nodes": graph_search.get("metrics",{}).get("root_nodes",0),
                          "telemetry": getattr(cur, "telemetry", {})},
            "exa_urls": [e["url"] for e in exa_unique],
            "search_urls": [e.get("url","") for e in search_unique],
        }
        report["queries"].append(row)
        print("RESULT", json.dumps(row, ensure_ascii=False))

    # Separate control: verify whether the raw Exa API honors includeDomains.
    control_domains = ["fsin.gov.ru", "mil.ru"]
    control_raw = [normalize_exa(x, "ФСИН Минобороны воинский учет заключенных") for x in exa_search("ФСИН Минобороны воинский учет заключенных", include_domains=control_domains)]
    control_domains_seen = sorted({domain(e["url"]) for e in control_raw if domain(e["url"])})
    report["domain_control"] = {
        "requested": control_domains,
        "results": len(control_raw),
        "domains_seen": control_domains_seen,
        "all_allowed": bool(control_raw) and all(d in control_domains or any(d.endswith("." + x) for x in control_domains) for d in control_domains_seen),
        "urls": [e["url"] for e in control_raw],
    }
    print("DOMAIN_CONTROL", json.dumps(report["domain_control"], ensure_ascii=False))

    with open("exa_event_gate_report.json","w",encoding="utf-8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)

if __name__ == "__main__":
    run()
