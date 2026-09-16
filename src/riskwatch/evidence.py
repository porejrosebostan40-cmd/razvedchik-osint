import hashlib
from .forecast import _eid, _source_family, _stage, _text, _timestamp, _is_primary, TARGET_TERMS, ACTION_TERMS, SEARCH_ENGINES
from .semantics import safe_root_event, has_target, is_negative

DIRECT_ROOT_TERMS=("привлечен", "привлечён", "зачислен", "зачислён", "направлен", "отправлен", "отправл", "призван", "заключил контракт", "заключен контракт", "заключён контракт", "начал службу")
PREPARATION_TERMS=("подготов", "список", "списки", "отбор", "учет", "учёт", "медицин", "провер", "поручен", "поручён")

def _graph_stage(event):
    text=_text(event)
    if safe_root_event(event): return 5
    if any(term in text for term in PREPARATION_TERMS) and has_target(event) and not is_negative(event):
        if any(term in text for term in ("транспорт", "размещ", "снабж", "формирован", "комплектован")): return 3
        return 2
    stage=_stage(event)
    return 4 if stage == 5 else stage

def _graph_root(event): return safe_root_event(event)
def _usable(event):
    family=_source_family(event)
    return bool(family) and family not in SEARCH_ENGINES and has_target(event)
def _target_key(event):
    text=_text(event)
    return tuple(sorted(set(term for term in TARGET_TERMS if term in text)))
def _claim_key(event):
    text=_text(event)
    return tuple(sorted(set(term for term in ACTION_TERMS if term in text)))
def _same_claim(a,b):
    return bool(set(_target_key(a)) & set(_target_key(b))) and bool(set(_claim_key(a)) & set(_claim_key(b)))
def _edge_type(a,b):
    if is_negative(a) != is_negative(b) and _same_claim(a,b): return "contradiction"
    return "corroboration"
def _compatible_order(a,b):
    sa,sb=_graph_stage(a),_graph_stage(b); ta,tb=_timestamp(a),_timestamp(b)
    if ta and tb: return sa < sb and ta <= tb
    if sa==sb: return True
    return sa < sb

def build_evidence_graph(events,max_edges=40):
    events=list(events or []); usable=[e for e in events if _usable(e)]; nodes=[]
    for event in usable:
        family=_source_family(event)
        nodes.append({"id":_eid(event),"stage":_graph_stage(event),"family":family,"primary":bool(_is_primary(event)),"region":str(event.get("region","" )).strip(),"ts":_timestamp(event),"root":bool(_graph_root(event))})
    edges=[]; contradiction_count=0
    for i,a in enumerate(usable):
        for b in usable[i+1:]:
            fa,fb=_source_family(a),_source_family(b)
            if fa==fb or not _same_claim(a,b): continue
            edge_type=_edge_type(a,b)
            if edge_type=="contradiction":
                ta,tb=_timestamp(a),_timestamp(b)
                if ta and tb and ta>tb: continue
                contradiction_count+=1
            elif not _compatible_order(a,b) and not _compatible_order(b,a):
                continue
            ta,tb=_timestamp(a),_timestamp(b)
            ordered=(ta<=tb) if ta and tb else (_graph_stage(a)<=_graph_stage(b))
            src,dst=(_eid(a),_eid(b)) if ordered else (_eid(b),_eid(a))
            edges.append({"from":src,"to":dst,"type":edge_type,"stage_from":_graph_stage(a) if ordered else _graph_stage(b),"stage_to":_graph_stage(b) if ordered else _graph_stage(a)})
    edges=sorted(edges,key=lambda e:(e["type"]=="contradiction",e["stage_to"],e["stage_from"]))[:max_edges]
    families={n["family"] for n in nodes}; primary_nodes=sum(n["primary"] for n in nodes); root_nodes=sum(n["root"] for n in nodes)
    ordered_edges=sum(e["type"]=="corroboration" and e["stage_from"]<e["stage_to"] for e in edges)
    regions={n["region"] for n in nodes if n["region"]}
    chain_score=max(0,min(100,min(25,len(families)*8)+min(20,primary_nodes*10)+min(25,ordered_edges*10)+min(15,root_nodes*15)+min(10,len(regions)*3)-min(30,contradiction_count*10)))
    fingerprint=hashlib.sha256(("|".join(sorted(n["id"] for n in nodes))+"#"+"|".join(f"{e['from']}:{e['to']}:{e['type']}" for e in edges)).encode()).hexdigest()[:16]
    return {"version":2,"nodes":nodes[:80],"edges":edges,"metrics":{"nodes":len(nodes),"edges":len(edges),"source_families":len(families),"primary_nodes":primary_nodes,"root_nodes":root_nodes,"ordered_support_edges":ordered_edges,"contradictions":contradiction_count,"regions_with_signals":len(regions),"chain_score":chain_score},"fingerprint":fingerprint}

def compact_chain(graph):
    metrics=dict(graph.get("metrics",{})); edges=[e for e in graph.get("edges",[]) if e.get("type")=="corroboration"][:12]; contradictions=[e for e in graph.get("edges",[]) if e.get("type")=="contradiction"][:8]
    return {"version":graph.get("version",1),"metrics":metrics,"support_edges":edges,"contradiction_edges":contradictions,"fingerprint":graph.get("fingerprint","")}
