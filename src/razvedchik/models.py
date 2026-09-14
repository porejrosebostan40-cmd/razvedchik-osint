from dataclasses import dataclass, field, asdict
from typing import Any
import hashlib
import json


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
class Candidate:
    key: str
    labels: set[str] = field(default_factory=set)
    identifiers: set[str] = field(default_factory=set)
    evidence_ids: set[str] = field(default_factory=set)
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "labels": sorted(self.labels),
            "identifiers": sorted(self.identifiers),
            "evidence_ids": sorted(self.evidence_ids),
            "score": round(self.score, 3),
        }


@dataclass
class Investigation:
    mode: str
    query: str
    waves: int = 0
    evidence: dict[str, Evidence] = field(default_factory=dict)
    candidates: dict[str, Candidate] = field(default_factory=dict)
    searched: set[str] = field(default_factory=set)
    queue: list[str] = field(default_factory=list)

    def add_evidence(self, item: Evidence) -> str:
        self.evidence[item.evidence_id] = item
        return item.evidence_id

    def add_candidate(self, key: str, label: str, identifiers: set[str], evidence_ids: set[str]) -> Candidate:
        candidate = self.candidates.setdefault(key, Candidate(key=key))
        candidate.labels.add(label)
        candidate.identifiers.update(identifiers)
        candidate.evidence_ids.update(evidence_ids)
        candidate.score = min(100.0, candidate.score + 5 + 3 * len(identifiers))
        return candidate
