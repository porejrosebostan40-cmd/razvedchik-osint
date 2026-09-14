from dataclasses import dataclass, field, asdict
from typing import Any
import hashlib
import json
from .entities import EntityGraph


@dataclass(frozen=True)
class Evidence:
    source: str
    url: str
    title: str
    snippet: str
    query: str
    kind: str = "web"
    confidence: str = "found mention"

    @property
    def evidence_id(self) -> str:
        raw = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class Relation:
    left: str
    relation: str
    right: str
    evidence_ids: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "relation": self.relation,
            "right": self.right,
            "evidence_ids": sorted(self.evidence_ids),
        }


@dataclass
class Candidate:
    key: str
    labels: set[str] = field(default_factory=set)
    identifiers: set[str] = field(default_factory=set)
    evidence_ids: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    domains: set[str] = field(default_factory=set)
    identifier_evidence: dict[str, set[str]] = field(default_factory=dict)
    identifier_sources: dict[str, set[str]] = field(default_factory=dict)
    identifier_domains: dict[str, set[str]] = field(default_factory=dict)
    score: float = 0.0
    status: str = "possible match"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "labels": sorted(self.labels),
            "identifiers": sorted(self.identifiers),
            "evidence_ids": sorted(self.evidence_ids),
            "sources": sorted(self.sources),
            "domains": sorted(self.domains),
            "score": round(self.score, 3),
            "status": self.status,
        }


@dataclass
class Investigation:
    mode: str
    query: str
    waves: int = 0
    stop_reason: str = "not finished"
    evidence: dict[str, Evidence] = field(default_factory=dict)
    candidates: dict[str, Candidate] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)
    entity_graph: EntityGraph = field(default_factory=EntityGraph)
    searched: set[str] = field(default_factory=set)
    queue: list[str] = field(default_factory=list)
    source_runs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_evidence(self, item: Evidence) -> str:
        self.evidence[item.evidence_id] = item
        return item.evidence_id

    def record_source_run(self, source: str, query: str, result_count: int, error: str | None = None) -> None:
        key = f"{source}|{query}"
        row = self.source_runs.setdefault(key, {"source": source, "query": query, "attempts": 0, "results": 0, "errors": []})
        row["attempts"] += 1
        row["results"] += result_count
        if error:
            row["errors"].append(error[:240])

    def add_relation(self, left: str, relation: str, right: str, evidence_id: str) -> None:
        if not left or not right or left == right:
            return
        for existing in self.relations:
            if existing.left == left and existing.relation == relation and existing.right == right:
                existing.evidence_ids.add(evidence_id)
                return
        self.relations.append(Relation(left, relation, right, {evidence_id}))

    def add_candidate(self, key: str, label: str, identifiers: set[str], evidence_ids: set[str], domains: set[str] | None = None, sources: set[str] | None = None) -> Candidate:
        candidate = self.candidates.setdefault(key, Candidate(key=key))
        domains = domains or set()
        sources = sources or set()
        candidate.labels.add(label)
        candidate.identifiers.update(identifiers)
        candidate.evidence_ids.update(evidence_ids)
        candidate.domains.update(domains)
        candidate.sources.update(sources)
        for identifier in identifiers:
            candidate.identifier_evidence.setdefault(identifier, set()).update(evidence_ids)
            candidate.identifier_sources.setdefault(identifier, set()).update(sources)
            candidate.identifier_domains.setdefault(identifier, set()).update(domains)

        candidate.score = min(100.0, candidate.score + 5 + 3 * len(identifiers) + min(10, len(candidate.domains) * 2))
        independently_supported = any(
            len(candidate.identifier_evidence.get(identifier, set())) >= 2
            and len(candidate.identifier_sources.get(identifier, set())) >= 2
            and len(candidate.identifier_domains.get(identifier, set())) >= 2
            for identifier in candidate.identifiers
            if _is_stable_identifier(identifier)
        )
        candidate.status = "confirmed by source" if independently_supported else "possible match"
        return candidate


def _is_stable_identifier(value: str) -> bool:
    return value.startswith("@") or ("@" in value and "." in value.rsplit("@", 1)[-1]) or (value.isdigit() and 9 <= len(value) <= 15)
