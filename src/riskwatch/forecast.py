from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlsplit

STAGES = {
    0: ("baseline", ()),
    1: ("legal_or_policy_signal", ("закон", "указ", "постановлен", "приказ", "норматив", "поправк", "правил", "порядок", "изменен", "изменён")),
    2: ("administrative_preparation", ("распоряж", "поручен", "поручён", "инструкц", "совещан", "штаб", "подготов", "провер", "список", "учет", "учёт", "комисси")),
    3: ("organizational_or_logistical_action", ("формирован", "комплектован", "резерв", "контракт", "личный состав", "транспорт", "места", "размещен", "размещён", "снабжен", "снабж")),
    4: ("operational_implementation", ("направлен", "отправлен", "призван", "зачислен", "переведен", "переведён", "реализован", "исполнен", "начал")),
}
NEGATIVE_TERMS = ("опроверг", "не подтверд", "отменен", "отменён", "отказ", "не планируется", "ложн", "фейк")


def _domain(url):
    try:
        return urlsplit(str(url)).netloc.lower().split(":")[0].removeprefix("www.")
    except ValueError:
        return ""


def _text(e):
    return (str(e.get("title", "")) + " " + str(e.get("snippet", ""))).lower()


def _stage(e):
    text = _text(e)
    hits = []
    for n, (_, terms) in STAGES.items():
        score = sum(1 for term in terms if term in text)
        if score:
            hits.append((score, n))
    return max(hits)[1] if hits else 0


def _timestamp(e):
    for key in ("published_ts", "published", "date", "ts"):
        value = e.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
    return 0.0


def build_forecast(events):
    events = list(events or [])
    stage_events = defaultdict(list)
    for e in events:
        stage_events[_stage(e)].append(e)
    active_stages = sorted(k for k in stage_events if k > 0)
    max_stage = max(active_stages, default=0)
    domains = {d for d in (_domain(e.get("url", "")) for e in events) if d}
    regions = {str(e.get("region", "")).strip() for e in events if str(e.get("region", "")).strip()}
    negative = sum(1 for e in events if any(t in _text(e) for t in NEGATIVE_TERMS))
    now = datetime.now(timezone.utc).timestamp()
    recent = sum(1 for e in events if _timestamp(e) and now - _timestamp(e) <= 3 * 86400)
    older = sum(1 for e in events if _timestamp(e) and 3 * 86400 < now - _timestamp(e) <= 14 * 86400)
    acceleration = 1.0 if not older and recent else (round(min(3.0, recent / older), 2) if older else 0.0)

    stage_count = len(active_stages)
    ordered = active_stages == list(range(1, max_stage + 1)) if max_stage else False
    chain_bonus = min(32, stage_count * 8 + (6 if ordered else 0))
    independence_bonus = min(24, max(0, len(domains) - 1) * 8)
    geography_bonus = min(12, max(0, len(regions) - 1) * 3)
    acceleration_bonus = min(12, max(0.0, acceleration - 1.0) * 6)
    contradiction_penalty = min(30, negative * 10)
    structure_score = max(0, min(95, int(8 + chain_bonus + independence_bonus + geography_bonus + acceleration_bonus - contradiction_penalty)))

    next_stage = min(4, max_stage + 1)
    if max_stage <= 1:
        horizon = "7-30d"
    elif max_stage == 2:
        horizon = "3-14d"
    elif max_stage == 3:
        horizon = "24h-7d"
    else:
        horizon = "24-72h"

    return {
        "pattern_stage": max_stage,
        "pattern_stage_name": STAGES[max_stage][0],
        "observed_stages": [STAGES[n][0] for n in active_stages],
        "next_stage": STAGES[next_stage][0],
        "next_event_horizon": horizon,
        "independent_domains": len(domains),
        "regions_with_signals": len(regions),
        "negative_indicators": negative,
        "acceleration": acceleration,
        "structure_score": structure_score,
        "interpretation": "ordered multi-stage chain is forming" if stage_count >= 2 and max_stage >= 2 else "isolated or early-stage signals; chain not established",
    }


def render_context(forecast):
    return "PATTERN_ENGINE\n" + "\n".join(f"{k}={v}" for k, v in forecast.items()) + "\nstructure_score is evidence structure, not probability."
