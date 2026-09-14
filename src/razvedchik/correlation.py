from dataclasses import dataclass, field

from .models import Candidate, Evidence, Investigation


ROLE_DE_JURE = "de jure"
ROLE_DE_FACTO = "de facto"
ROLE_UNKNOWN = "unknown relationship"


@dataclass
class PhoneLink:
    candidate_key: str
    roles: set[str] = field(default_factory=set)
    score: float = 0.0
    evidence_ids: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)

    @property
    def role(self) -> str:
        if not self.roles:
            return ROLE_UNKNOWN
        return ", ".join(sorted(self.roles))

    def to_dict(self) -> dict:
        return {
            "candidate_key": self.candidate_key,
            "roles": sorted(self.roles),
            "role": self.role,
            "score": round(self.score, 3),
            "evidence_ids": sorted(self.evidence_ids),
            "reasons": list(dict.fromkeys(self.reasons)),
        }


def _phone_evidence(evidence: Evidence, phone: str) -> bool:
    return phone in f"{evidence.title} {evidence.snippet}"


def _role_from_evidence(evidence: Evidence) -> tuple[str, str] | None:
    kind = evidence.kind.lower()
    if "de-jure" in kind or "owner" in kind or "registered" in kind:
        return ROLE_DE_JURE, "Источник помечает связь как владение/регистрацию."
    if "de-facto" in kind or "user" in kind or "contact-label" in kind:
        return ROLE_DE_FACTO, "Источник помечает связь как фактическое использование."
    return None


def correlate_phone(inv: Investigation, phone: str) -> list[PhoneLink]:
    """Build a conservative phone relationship view without treating mentions as ownership."""
    links: dict[str, PhoneLink] = {}
    for candidate in inv.candidates.values():
        if phone not in candidate.identifiers:
            continue
        link = links.setdefault(candidate.key, PhoneLink(candidate.key))
        for evidence_id in candidate.evidence_ids:
            evidence = inv.evidence.get(evidence_id)
            if not evidence or not _phone_evidence(evidence, phone):
                continue
            link.evidence_ids.add(evidence_id)
            role = _role_from_evidence(evidence)
            if role:
                role_name, reason = role
                link.roles.add(role_name)
                link.reasons.append(reason)
            else:
                link.reasons.append("Найдено упоминание номера; само по себе оно не доказывает владельца или фактического пользователя.")
        link.score = min(100.0, len(link.evidence_ids) * 8.0 + len(candidate.domains) * 4.0 + len(candidate.sources) * 4.0)
        if not link.roles:
            link.roles.add(ROLE_UNKNOWN)

    return sorted(links.values(), key=lambda x: (-x.score, x.candidate_key))


def phone_conflicts(links: list[PhoneLink]) -> bool:
    de_jure_keys = {link.candidate_key for link in links if ROLE_DE_JURE in link.roles}
    de_facto_keys = {link.candidate_key for link in links if ROLE_DE_FACTO in link.roles}
    return bool(de_jure_keys and de_facto_keys and de_jure_keys != de_facto_keys)
