from dataclasses import asdict
import json
import os
from pathlib import Path
from .models import Investigation


def configured_collectors(inv: Investigation) -> list[str]:
    collectors = ["web search", "GitHub public search"]
    if inv.mode in {"fio", "email", "username", "nickname", "combined"}:
        collectors.extend(["GitLab public user search", "Stack Overflow public user search"])
    if inv.mode in {"fio", "combined"}:
        collectors.append("Wikidata public knowledge base")
    if inv.mode in {"username", "nickname", "combined"}:
        collectors.append("Sherlock public username search (optional bridge)")
    return collectors


def coverage_summary(inv: Investigation) -> dict:
    source_names = {item.source for item in inv.evidence.values()}
    domains = {domain for candidate in inv.candidates.values() for domain in candidate.domains}
    identifiers = {identifier for candidate in inv.candidates.values() for identifier in candidate.identifiers}
    confirmed = sum(candidate.status == "confirmed by source" for candidate in inv.candidates.values())
    planner = "OpenAI Responses API" if os.getenv("OPENAI_API_KEY") else "deterministic fallback"
    direct = [name for name in configured_collectors(inv) if "optional bridge" not in name and name != "web search"]
    bridges = [name for name in configured_collectors(inv) if "optional bridge" in name]
    return {
        "waves_completed": inv.waves,
        "queries_searched": len(inv.searched),
        "queries_pending": len(inv.queue),
        "evidence_items": len(inv.evidence),
        "configured_collectors": configured_collectors(inv),
        "direct_source_collectors": direct,
        "optional_bridges": bridges,
        "observed_sources": sorted(source_names),
        "planner": planner,
        "domains_observed": len(domains),
        "identifiers_observed": len(identifiers),
        "candidates_total": len(inv.candidates),
        "candidates_confirmed_by_source": confirmed,
        "coverage_note": "Coverage is bounded by configured collectors, public-source visibility, search-engine results, source rate limits, and investigation limits.",
    }


def to_dict(inv: Investigation) -> dict:
    return {
        "mode": inv.mode,
        "query": inv.query,
        "waves": inv.waves,
        "stop_reason": inv.stop_reason,
        "coverage": coverage_summary(inv),
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
    coverage = data["coverage"]
    lines = [
        f"# Разведчик: {inv.query}",
        "",
        f"Режим: {inv.mode}",
        f"Волн: {inv.waves}",
        f"Причина остановки: {inv.stop_reason}",
        "",
        "## Покрытие расследования",
        f"- Запросов проверено: {coverage['queries_searched']}",
        f"- Доказательств собрано: {coverage['evidence_items']}",
        f"- Прямые источники: {', '.join(coverage['direct_source_collectors']) or 'нет'}",
        f"- Дополнительные мосты: {', '.join(coverage['optional_bridges']) or 'нет'}",
        f"- Фактически наблюдавшиеся источники: {', '.join(coverage['observed_sources']) or 'нет'}",
        f"- Планировщик: {coverage['planner']}",
        f"- Доменов обнаружено: {coverage['domains_observed']}",
        f"- Идентификаторов обнаружено: {coverage['identifiers_observed']}",
        f"- Кандидатов: {coverage['candidates_total']}; подтверждено источниками: {coverage['candidates_confirmed_by_source']}",
        f"- В очереди осталось: {coverage['queries_pending']}",
        f"- Ограничение покрытия: {coverage['coverage_note']}",
        "",
        "## Кандидаты",
    ]
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
