from dataclasses import asdict
import json
from pathlib import Path
from .models import Investigation


def to_dict(inv: Investigation) -> dict:
    return {
        "mode": inv.mode,
        "query": inv.query,
        "waves": inv.waves,
        "searched_queries": sorted(inv.searched),
        "evidence": [asdict(x) | {"evidence_id": x.evidence_id} for x in inv.evidence.values()],
        "candidates": [c.to_dict() for c in sorted(inv.candidates.values(), key=lambda x: x.score, reverse=True)],
    }


def write_reports(inv: Investigation, directory: str = "reports") -> tuple[str, str]:
    Path(directory).mkdir(parents=True, exist_ok=True)
    data = to_dict(inv)
    json_path = Path(directory) / "investigation.json"
    md_path = Path(directory) / "investigation.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# Разведчик: {inv.query}", "", f"Режим: {inv.mode}", f"Волн: {inv.waves}", "", "## Кандидаты"]
    for c in sorted(inv.candidates.values(), key=lambda x: x.score, reverse=True):
        lines += [f"### {c.key}", f"- Оценка: {c.score:.1f}", f"- Идентификаторы: {', '.join(sorted(c.identifiers)) or 'нет'}", f"- Метки: {', '.join(sorted(c.labels)) or 'нет'}", ""]
    lines += ["## Источники", ""]
    for e in inv.evidence.values():
        lines += [f"- [{e.title}]({e.url}) — {e.source}; запрос: `{e.query}`; уверенность: {e.confidence}", f"  {e.snippet}"]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return str(json_path), str(md_path)
