from .entities import page_entities
from .extract import identifiers, domain
from .models import Investigation
from .normalize import expand_queries
from .planner import ai_queries, deterministic_queries
from .sources import source_specs_for_mode


VALID_MODES = {"fio", "username", "nickname", "phone", "email", "combined"}


class Agent:
    def __init__(self, mode: str, query: str, max_waves: int = 3, per_query: int = 6):
        if mode not in VALID_MODES:
            raise ValueError(f"unsupported mode: {mode}")
        if not query or not query.strip():
            raise ValueError("query must not be empty")
        if max_waves < 1 or max_waves > 12:
            raise ValueError("max_waves must be between 1 and 12")
        if per_query < 1 or per_query > 20:
            raise ValueError("per_query must be between 1 and 20")
        self.inv = Investigation(mode=mode, query=query.strip())
        self.max_waves = max_waves
        self.per_query = per_query

    def _collect(self, query: str):
        """Collect through the source registry; optional bridges never replace direct sources."""
        seen: set[str] = set()
        for spec in source_specs_for_mode(self.inv.mode):
            limit = min(self.per_query, spec.max_limit)
            try:
                results = list(spec.collector(query, limit=limit))
                self.inv.record_source_run(spec.name, query, len(results))
            except Exception as exc:
                self.inv.record_source_run(spec.name, query, 0, error=f"{type(exc).__name__}: {exc}")
                continue
            for ev in results:
                if ev.url not in seen:
                    seen.add(ev.url)
                    yield ev

    def _record(self, query: str, ev) -> None:
        eid = self.inv.add_evidence(ev)
        text = f"{ev.title} {ev.snippet}"
        ids = identifiers(text)
        dom = {domain(ev.url)} - {""}
        key = "|".join(sorted(ids)[:3]) if ids else f"evidence:{eid}"
        self.inv.add_candidate(key, ev.title, ids, {eid}, dom, {ev.source})

        graph, edges = page_entities(ev.title, ev.snippet, ev.url, ids, eid)
        self.inv.entity_graph.merge(graph)
        for left, relation, right in edges:
            self.inv.add_relation(left, relation, right, eid)

        ordered = sorted(ids)
        for left in ordered:
            for right in ordered:
                if left < right:
                    self.inv.add_relation(left, "co-occurs in source", right, eid)
        for ident in ordered:
            for pivot in (ident, f'"{ident}"'):
                if pivot not in self.inv.searched and pivot not in self.inv.queue:
                    self.inv.queue.append(pivot)

    def run(self) -> Investigation:
        self.inv.queue.extend(expand_queries(self.inv.mode, self.inv.query))
        for wave in range(1, self.max_waves + 1):
            self.inv.waves = wave
            current = []
            while self.inv.queue and len(current) < 16:
                q = self.inv.queue.pop(0)
                if q not in self.inv.searched:
                    current.append(q)
                    self.inv.searched.add(q)
            if not current:
                self.inv.stop_reason = "search queue exhausted"
                break
            for q in current:
                for ev in self._collect(q):
                    self._record(q, ev)
            known = sorted({i for c in self.inv.candidates.values() for i in c.identifiers})
            recent_evidence = [
                f"{ev.source} | {ev.title} | {ev.snippet} | {ev.url}"
                for ev in list(self.inv.evidence.values())[-8:]
            ]
            planned = ai_queries(self.inv.mode, self.inv.query, known, recent_evidence) or deterministic_queries(self.inv.mode, self.inv.query, known)
            for q in planned:
                if q not in self.inv.searched and q not in self.inv.queue:
                    self.inv.queue.append(q)
            if not self.inv.queue:
                self.inv.stop_reason = "no new queries"
                break
        else:
            self.inv.stop_reason = "maximum waves reached"
        if self.inv.stop_reason == "not finished":
            self.inv.stop_reason = "investigation completed"
        return self.inv
