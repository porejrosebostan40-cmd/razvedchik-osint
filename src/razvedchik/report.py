from dataclasses import asdict
import json
from pathlib import Path
from .models import Investigation


def to_dict(inv: Investigation) -> dict:
    return {
        "mode": inv.mode,
        "query": inv.query,
        "waves": inv.waves,
        "stop_reason": inv.stop_reason,
        "searched_queries": sorted(inv.searched),
        "evidence": [asdict(x) | {"evidence_id": x.evidence_id} for x in inv.evidence.values()],
        "candidates": [c.to_dict() for c in sorted(inv.candidates.values(), key=lambda x: x.score, reverse=True)],
        "entities": inv.entity_graph.to_dict(),
        "relations": [r.to_dict() for r in inv.relations],
    }


def write_reports(inv: Investigation, directory: str = "reports") -> tuple[str, str]:
    Path(directory).mkdir(parents=True, exist_ok=True)
    data = to_dict(inv)
    json_path = Path(directory) / "investigation.json"
    md_path = Path(directory) / "investigation.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# Разведчик: {inv.query}", "", f"Режим: {inv.mode}", f"Волн: {inv.waves}", f"Причина остановки: {inv.stop_reason}", "", "## Кандидаты"]
    for c in sorted(inv.candidates.values(), key=lambda x: x.score, reverse=True):
        lines += [f"### {c.key}", f"- Статус: {c.status}", f"- Оценка: {c.score:.1f}", f"- Идентификаторы: {', '.join(sorted(c.identifiers)) or 'нет'}", f"- Источники: {', '.join(sorted(c.sources)) or 'нет'}", f"- Домены: {', '.join(sorted(c.domains)) or 'нет'}", ""]
    lines += ["## Сущности", ""]
    for entity in inv.entity_graph.entities.values():
        lines.append(f"- `{entity.kind}`: `{entity.value}`; доказательства: {', '.join(sorted(entity.evidence_ids))}")
    lines += ["", "## Граф связей", ""]
    for r in inv.relations:
        lines.append(f"- `{r.left}` — **{r.relation}** — `{r.right}`; доказательства: {', '.join(sorted(r.evidence_ids))}")
    lines += ["", "## Источники", ""]
    for e in inv.evidence.values():
        lines += [f"- [{e.title}]({e.url}) — {e.source}; запрос: `{e.query}`; уверенность: {e.confidence}", f"  {e.snippet}"]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return str(json_path), str(md_path)
