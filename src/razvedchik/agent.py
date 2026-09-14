from .collectors import search_github
from .entities import page_entities
from .extract import identifiers, domain
from .models import Investigation
from .normalize import expand_queries
from .planner import ai_queries, deterministic_queries
from .search import search_web


class Agent:
    def __init__(self, mode: str, query: str, max_waves: int = 3, per_query: int = 6):
        self.inv = Investigation(mode=mode, query=query)
        self.max_waves = max_waves
        self.per_query = per_query

    def _collect(self, query: str):
        """Combine generic web search with a public GitHub search branch."""
        seen: set[str] = set()
        for ev in search_web(query, limit=self.per_query):
            if ev.url not in seen:
                seen.add(ev.url)
                yield ev
        for ev in search_github(query, limit=min(self.per_query, 6)):
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
        self.inv.entity_graph.entities.update(graph.entities)
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
                break
            for q in current:
                for ev in self._collect(q):
                    self._record(q, ev)
            known = sorted({i for c in self.inv.candidates.values() for i in c.identifiers})
            planned = ai_queries(self.inv.mode, self.inv.query, known) or deterministic_queries(self.inv.mode, self.inv.query, known)
            for q in planned:
                if q not in self.inv.searched and q not in self.inv.queue:
                    self.inv.queue.append(q)
            if not self.inv.queue:
                break
        return self.inv
