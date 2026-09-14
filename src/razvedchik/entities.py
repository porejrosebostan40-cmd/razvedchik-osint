from dataclasses import dataclass, field
import re
from urllib.parse import urlparse


@dataclass
class Entity:
    key: str
    kind: str
    value: str
    evidence_ids: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "kind": self.kind,
            "value": self.value,
            "evidence_ids": sorted(self.evidence_ids),
        }


@dataclass
class EntityGraph:
    entities: dict[str, Entity] = field(default_factory=dict)

    def add(self, kind: str, value: str, evidence_id: str) -> str:
        value = value.strip()
        key = f"{kind}:{value.lower()}"
        entity = self.entities.setdefault(key, Entity(key, kind, value))
        entity.evidence_ids.add(evidence_id)
        return key

    def to_dict(self) -> list[dict]:
        return [e.to_dict() for e in sorted(self.entities.values(), key=lambda x: (x.kind, x.value.lower()))]


def classify_identifier(value: str) -> str:
    if value.startswith("@"):
        return "username"
    if "@" in value and "." in value.rsplit("@", 1)[-1]:
        return "email"
    if value.isdigit() and 9 <= len(value) <= 15:
        return "phone"
    return "identifier"


def page_entities(title: str, snippet: str, url: str, identifiers: set[str], evidence_id: str) -> tuple[EntityGraph, list[tuple[str, str, str]]]:
    graph = EntityGraph()
    edges: list[tuple[str, str, str]] = []
    for value in sorted(identifiers):
        key = graph.add(classify_identifier(value), value, evidence_id)
        edges.append((key, "mentioned_on", url))

    host = urlparse(url).netloc.lower().removeprefix("www.")
    if host:
        domain_key = graph.add("domain", host, evidence_id)
        for key, _, _ in edges:
            edges.append((key, "found_on", domain_key))

    # Preserve the page title as a searchable label, but do not infer identity from it.
    label = re.sub(r"\s+", " ", title).strip()
    if label:
        label_key = graph.add("page", label[:240], evidence_id)
        for key, _, _ in edges:
            if key.startswith(("username:", "email:", "phone:")):
                edges.append((key, "appears_on", label_key))
    return graph, edges
