import hashlib
from collections import defaultdict
from .forecast import _eid, _root_event, _source_family, _stage, _text, _timestamp, _is_primary, TARGET_TERMS, ACTION_TERMS, SEARCH_ENGINES


def _usable(event):
    text = _text(event)
    family = _source_family(event)
    return bool(family) and family not in SEARCH_ENGINES and any(term in text for term in TARGET_TERMS)


def _target_key(event):
    text = _text(event)
    hits = [term for term in TARGET_TERMS if term in text]
    return tuple(sorted(set(hits)))


def _claim_key(event):
    text = _text(event)
    actions = [term for term in ACTION_TERMS if term in text]
    return tuple(sorted(set(actions)))


def _same_claim(a, b):
    ta, tb = _target_key(a), _target_key(b)
    aa, ab = _claim_key(a), _claim_key(b)
    return bool(set(ta) & set(tb)) and bool(set(aa) & set(ab))


def _edge_type(a, b):
    ta, tb = _text(a), _text(b)
    negative_a = any(x in ta for x in ("опроверг", "не подтверд", "отменен", "отменён", "отказ", "не планируется", "ложн", "фейк", "исключен", "исключён"))
    negative_b = any(x in tb for x in ("опроверг", "не подтверд", "отменен", "отменён", "отказ", "не планируется", "ложн", "фейк", "исключен", "исключён"))
    if negative_a != negative_b and _same_claim(a, b):
        return "contradiction"
    return "corroboration"


def _compatible_order(a, b):
    sa, sb = _stage(a), _stage(b)
    ta, tb = _timestamp(a), _timestamp(b)
    if not ta or not tb:
        return sa != sb
    if sa == sb:
        return abs(tb - ta) <= 14 * 86400
    return sa < sb and ta <= tb


def build_evidence_graph(events, max_edges=40):
    events = list(events or [])
    usable = [e for e in events if _usable(e)]
    nodes = []
    for event in usable:
        family = _source_family(event)
        nodes.append({
            "id": _eid(event),
            "stage": _stage(event),
            "family": family,
            "primary": bool(_is_primary(event)),
            "region": str(event.get("region", "")).strip(),
            "ts": _timestamp(event),
            "root": bool(_root_event(event)),
        })

    edges = []
    contradiction_count = 0
    for i, a in enumerate(usable):
        for b in usable[i + 1:]:
            fa, fb = _source_family(a), _source_family(b)
            if fa == fb or not _same_claim(a, b):
                continue
            if not _compatible_order(a, b) and not _compatible_order(b, a):
                continue
            edge_type = _edge_type(a, b)
            if edge_type == "contradiction":
                contradiction_count += 1
            ta, tb = _timestamp(a), _timestamp(b)
            ordered = (ta <= tb) if ta and tb else (_stage(a) <= _stage(b))
            src, dst = (_eid(a), _eid(b)) if ordered else (_eid(b), _eid(a))
            edges.append({"from": src, "to": dst, "type": edge_type, "stage_from": _stage(a) if ordered else _stage(b), "stage_to": _stage(b) if ordered else _stage(a)})

    edges = sorted(edges, key=lambda e: (e["type"] == "contradiction", e["stage_to"], e["stage_from"]))[:max_edges]
    families = {n["family"] for n in nodes}
    primary_nodes = sum(n["primary"] for n in nodes)
    root_nodes = sum(n["root"] for n in nodes)
    ordered_edges = sum(e["type"] == "corroboration" and e["stage_from"] < e["stage_to"] for e in edges)
    regional_families = {n["family"] for n in nodes if n["region"]}
    chain_score = max(0, min(100,
        min(25, len(families) * 8)
        + min(20, primary_nodes * 10)
        + min(25, ordered_edges * 10)
        + min(15, root_nodes * 15)
        + min(10, len(regional_families) * 3)
        - min(30, contradiction_count * 10)
    ))
    fingerprint = hashlib.sha256(("|".join(sorted(n["id"] for n in nodes)) + "#" + "|".join(f"{e['from']}:{e['to']}:{e['type']}" for e in edges)).encode()).hexdigest()[:16]
    return {
        "version": 1,
        "nodes": nodes[:80],
        "edges": edges,
        "metrics": {
            "nodes": len(nodes),
            "edges": len(edges),
            "source_families": len(families),
            "primary_nodes": primary_nodes,
            "root_nodes": root_nodes,
            "ordered_support_edges": ordered_edges,
            "contradictions": contradiction_count,
            "regional_families": len(regional_families),
            "chain_score": chain_score,
        },
        "fingerprint": fingerprint,
    }


def compact_chain(graph):
    metrics = dict(graph.get("metrics", {}))
    edges = [e for e in graph.get("edges", []) if e.get("type") == "corroboration"][:12]
    contradictions = [e for e in graph.get("edges", []) if e.get("type") == "contradiction"][:8]
    return {"version": graph.get("version", 1), "metrics": metrics, "support_edges": edges, "contradiction_edges": contradictions, "fingerprint": graph.get("fingerprint", "")}
