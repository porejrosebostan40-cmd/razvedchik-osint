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
                for ev in search_web(q, limit=self.per_query):
                    eid = self.inv.add_evidence(ev)
                    ids = identifiers(f"{ev.title} {ev.snippet}")
                    dom = {domain(ev.url)} - {""}
                    key = "|".join(sorted(ids)[:3]) if ids else f"seed:{self.inv.query}"
                    self.inv.add_candidate(key, ev.title, ids, {eid}, dom)
                    # Autonomous second-generation pivots: identifiers discovered in evidence
                    # become future search seeds without requiring user approval.
                    for ident in sorted(ids):
                        for pivot in (ident, f'"{ident}"'):
                            if pivot not in self.inv.searched and pivot not in self.inv.queue:
                                self.inv.queue.append(pivot)
            known = sorted({i for c in self.inv.candidates.values() for i in c.identifiers})
            planned = ai_queries(self.inv.mode, self.inv.query, known) or deterministic_queries(self.inv.mode, self.inv.query, known)
            for q in planned:
                if q not in self.inv.searched and q not in self.inv.queue:
                    self.inv.queue.append(q)
            if not self.inv.queue:
                break
        return self.inv
