import hashlib
import math
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlsplit

SCENARIO_ID = "prisoner_mobilization"
STAGES = {
    0: ("baseline", ()),
    1: ("legal_or_policy_signal", ("закон", "указ", "постановлен", "приказ", "норматив", "поправк", "правил", "порядок", "изменен", "изменён")),
    2: ("administrative_preparation", ("распоряж", "поручен", "поручён", "инструкц", "совещан", "штаб", "подготов", "провер", "список", "учет", "учёт", "комисси")),
    3: ("organizational_or_logistical_action", ("формирован", "комплектован", "резерв", "контракт", "личный состав", "транспорт", "места", "размещен", "размещён", "снабжен", "снабж")),
    4: ("operational_implementation", ("направлен", "отправлен", "призван", "зачислен", "переведен", "переведён", "реализован", "исполнен", "начал")),
    5: ("root_scenario", ("осужден", "осуждён", "заключен", "заключён", "исправительн", "колони", "мест лишения свободы", "лишения свободы")),
}
NEGATIVE_TERMS = ("опроверг", "не подтверд", "отменен", "отменён", "отказ", "не планируется", "ложн", "фейк", "исключен", "исключён")
TARGET_TERMS = ("осужден", "осуждён", "заключен", "заключён", "исправительн", "колони", "мест лишения свободы", "фсин", "уфсин", "фку", "содержащихся")
ACTION_TERMS = ("мобилиз", "привлеч", "военн", "контракт", "зачислен", "направлен", "отправлен", "призван", "служб", "отбор", "медицин", "список", "учет", "учёт", "квот", "транспорт")
PRIMARY_DOMAINS = ("kremlin.ru", "government.ru", "mil.ru", "fsin.gov.ru", "publication.pravo.gov.ru", "minjust.gov.ru", "duma.gov.ru", "zakupki.gov.ru", "gov.ru")


def _domain(url):
    try:
        return urlsplit(str(url)).netloc.lower().split(":")[0].removeprefix("www.")
    except ValueError:
        return ""


def _text(e):
    return (str(e.get("title", "")) + " " + str(e.get("snippet", ""))).lower()


def _stage(e):
    text = _text(e)
    target = sum(1 for term in TARGET_TERMS if term in text)
    action = sum(1 for term in ACTION_TERMS if term in text)
    hits = []
    for n, (_, terms) in STAGES.items():
        score = sum(1 for term in terms if term in text)
        if score:
            # Stage 5 requires target-specific language; otherwise a generic military event
            # must never be mistaken for the root scenario.
            if n == 5 and target == 0:
                continue
            hits.append((score + (3 if n == 5 and action else 0), n))
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


def _event_id(e):
    return hashlib.sha256((str(e.get("url", "")) + "|" + str(e.get("title", ""))).encode()).hexdigest()[:16]


def _family(e):
    text = " ".join(_text(e).split())
    return " ".join(text.split()[:50])


def _is_primary(e):
    d = _domain(e.get("url", ""))
    return any(d == x or d.endswith("." + x) for x in PRIMARY_DOMAINS)


def evidence_score(events):
    """Deterministic evidence strength. This is not a probability."""
    events = list(events or [])
    target_events = [e for e in events if sum(term in _text(e) for term in TARGET_TERMS) >= 1]
    action_events = [e for e in target_events if sum(term in _text(e) for term in ACTION_TERMS) >= 1]
    domains = {_domain(e.get("url", "")) for e in target_events if _domain(e.get("url", ""))}
    primary = sum(1 for e in target_events if _is_primary(e))
    independent = min(4, len(domains))
    target_specificity = min(30, len(action_events) * 8)
    independence = min(25, max(0, independent - 1) * 8)
    primary_bonus = min(25, primary * 10)
    direct_bonus = 30 if any(_stage(e) == 5 and sum(term in _text(e) for term in ACTION_TERMS) >= 2 for e in events) else 0
    negative = sum(1 for e in events if any(t in _text(e) for t in NEGATIVE_TERMS))
    score = max(0, min(100, target_specificity + independence + primary_bonus + direct_bonus - min(35, negative * 8)))
    return {"score": score, "target_events": len(target_events), "action_events": len(action_events), "independent_domains": len(domains), "primary_events": primary, "negative_indicators": negative}


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
    recent = sum(1 for e in events if _timestamp(e) and 0 <= now - _timestamp(e) <= 3 * 86400)
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
    ev = evidence_score(events)

    if max_stage >= 5:
        next_stage, horizon = "root_scenario", "24-72h"
    elif max_stage == 4:
        next_stage, horizon = "root_scenario", "24-72h"
    elif max_stage == 3:
        next_stage, horizon = "operational_implementation", "24h-7d"
    elif max_stage == 2:
        next_stage, horizon = "organizational_or_logistical_action", "3-14d"
    else:
        next_stage, horizon = "administrative_preparation", "7-30d"

    return {
        "scenario_id": SCENARIO_ID,
        "pattern_stage": max_stage,
        "pattern_stage_name": STAGES[max_stage][0],
        "observed_stages": [STAGES[n][0] for n in active_stages],
        "next_stage": next_stage,
        "next_event_horizon": horizon,
        "independent_domains": len(domains),
        "regions_with_signals": len(regions),
        "negative_indicators": negative,
        "acceleration": acceleration,
        "structure_score": structure_score,
        "evidence_score": ev["score"],
        "evidence_metrics": ev,
        "interpretation": "ordered multi-stage chain is forming" if stage_count >= 2 and max_stage >= 2 else "isolated or early-stage signals; chain not established",
    }


def _deadline(now_ts, horizon):
    return now_ts + ({"24-72h": 72, "24h-7d": 168, "3-14d": 336, "7-30d": 720}.get(horizon, 720) * 3600)


def forecast_record(forecast, probability, now=None, evidence_ids=None):
    now_ts = float(now if now is not None else datetime.now(timezone.utc).timestamp())
    p = max(0, min(100, int(probability)))
    horizon = forecast.get("next_event_horizon", "7-30d")
    ids = list(evidence_ids or [])
    fingerprint = hashlib.sha256((SCENARIO_ID + "|" + horizon + "|" + ",".join(sorted(ids))).encode()).hexdigest()[:16]
    return {
        "forecast_id": fingerprint + "-" + str(int(now_ts)),
        "scenario_id": SCENARIO_ID,
        "created_ts": now_ts,
        "horizon": horizon,
        "deadline_ts": _deadline(now_ts, horizon),
        "target": SCENARIO_ID,
        "predicted_stage": forecast.get("next_stage", "baseline"),
        "probability": p,
        "structure_score": int(forecast.get("structure_score", 0)),
        "evidence_score": int(forecast.get("evidence_score", 0)),
        "evidence_ids": ids,
        "evidence_fingerprint": fingerprint,
        "resolved": False,
        "outcome": None,
        "resolved_ts": None,
        "brier": None,
    }


def _root_outcome(events):
    # Root success requires target-specific action, not merely a generic military event.
    for e in events:
        text = _text(e)
        target = sum(term in text for term in TARGET_TERMS)
        action = sum(term in text for term in ACTION_TERMS)
        if target >= 1 and action >= 2:
            return True
    return False


def resolve_forecasts(records, events, now=None):
    now_ts = float(now if now is not None else datetime.now(timezone.utc).timestamp())
    resolved = []
    root_hit = _root_outcome(events)
    for rec in records:
        if rec.get("resolved"):
            resolved.append(rec); continue
        if now_ts < float(rec.get("deadline_ts", 0)):
            resolved.append(rec); continue
        rec = dict(rec)
        # Only the root scenario resolves this ledger. Intermediate next-stage hits
        # are analytical observations, not successful root forecasts.
        outcome = 1 if root_hit else 0
        rec.update({"resolved": True, "outcome": outcome, "resolved_ts": now_ts, "brier": _brier(rec.get("probability", 0), outcome)})
        resolved.append(rec)
    return resolved


def _brier(probability, outcome):
    p = max(0.0, min(1.0, float(probability) / 100.0))
    return round((p - float(outcome)) ** 2, 6)


def calibration_summary(records):
    done = [r for r in records if r.get("resolved") and r.get("brier") is not None and r.get("scenario_id", SCENARIO_ID) == SCENARIO_ID]
    if not done:
        return {"resolved": 0, "brier": None, "brier_skill_score": None, "calibration_status": "insufficient_history"}
    brier = round(sum(float(r["brier"]) for r in done) / len(done), 6)
    base = sum(float(r.get("outcome", 0)) for r in done) / len(done)
    baseline_brier = base * (1 - base)
    skill = round(1 - brier / baseline_brier, 6) if baseline_brier > 0 else None
    bins = defaultdict(list)
    for r in done:
        bins[min(9, int(r.get("probability", 0)) // 10)].append(r.get("outcome", 0))
    calibration = [{"range": f"{b*10}-{b*10+9}", "n": len(v), "empirical_rate": round(sum(v)/len(v)*100,1)} for b,v in sorted(bins.items())]
    n = len(done)
    status = "insufficient_history" if n < 30 else ("preliminary" if n < 100 else "measured")
    return {"resolved": n, "base_rate": round(base*100,2), "brier": brier, "brier_skill_score": skill, "calibration": calibration, "calibration_status": status}


def render_context(forecast, calibration=None):
    text = "PATTERN_ENGINE\n" + "\n".join(f"{k}={v}" for k, v in forecast.items())
    if calibration:
        text += "\nCALIBRATION=" + str(calibration)
    return text + "\nstructure_score and evidence_score are evidence-strength measures, not probabilities; root probability requires temporal historical calibration."
