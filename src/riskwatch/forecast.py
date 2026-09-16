import hashlib
import re
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
    5: ("root_scenario", ()),
}
NEGATIVE_TERMS = ("опроверг", "не подтверд", "отменен", "отменён", "отказ", "не планируется", "ложн", "фейк", "исключен", "исключён")
TARGET_TERMS = ("осужден", "осуждён", "заключен", "заключён", "исправительн", "колони", "мест лишения свободы", "фсин", "уфсин", "фку", "содержащихся")
ACTION_TERMS = ("мобилиз", "привлеч", "военн", "контракт", "зачислен", "направлен", "отправлен", "призван", "служб", "отбор", "медицин", "список", "учет", "учёт", "квот", "транспорт")
MILITARY_ANCHORS = ("мобилиз", "военн", "военком", "военнослуж", "арм", "сво", "вооружен", "вооружён", "министерств оборон", "минобороны", "вооруженные силы", "вооружённые силы")
DIRECT_ACTION_TERMS = ("привлеч", "зачислен", "зачислён", "направлен", "отправлен", "отправл", "призван", "заключил контракт", "заключен контракт", "заключён контракт", "начал службу")
NEGATION_RE = re.compile(r"\bне\s+(?:будут|будет|стал|стали|станут|привлеч|зачислен|зачислён|направлен|отправлен|призван|мобилиз)")
PRIMARY_DOMAINS = ("kremlin.ru", "government.ru", "mil.ru", "fsin.gov.ru", "publication.pravo.gov.ru", "minjust.gov.ru", "duma.gov.ru", "zakupki.gov.ru", "gov.ru")
SEARCH_ENGINES = ("duckduckgo.com", "bing.com", "google.com", "yandex.ru", "yandex.com")


def _domain(url):
    try:
        return urlsplit(str(url)).netloc.lower().split(":")[0].removeprefix("www.")
    except ValueError:
        return ""


def _source_family(e):
    domain = _domain(e.get("url", ""))
    if not domain:
        return ""
    for suffix in PRIMARY_DOMAINS:
        if domain == suffix or domain.endswith("." + suffix):
            return suffix
    parts = domain.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def _text(e):
    return (str(e.get("title", "")) + " " + str(e.get("snippet", ""))).lower()


def _has_target(e):
    return any(term in _text(e) for term in TARGET_TERMS)


def _is_negative(e):
    text = _text(e)
    return any(term in text for term in NEGATIVE_TERMS) or bool(NEGATION_RE.search(text))


def _has_military_anchor(e):
    return any(term in _text(e) for term in MILITARY_ANCHORS)


def _has_direct_military_action(e):
    text = _text(e)
    return _has_target(e) and _has_military_anchor(e) and any(term in text for term in DIRECT_ACTION_TERMS) and not _is_negative(e)


def _root_event(e):
    return _has_direct_military_action(e)


def _stage(e):
    text = _text(e)
    if _root_event(e):
        return 5
    target = _has_target(e)
    hits = []
    for n, (_, terms) in STAGES.items():
        if n == 5:
            continue
        score = sum(1 for term in terms if term in text)
        if not score:
            continue
        # Administrative and operational target-specific stages require a target.
        # Logistics may be generic because its target linkage can come from earlier events.
        if n in (2, 4) and not target:
            continue
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


def _eid(e):
    return hashlib.sha256((str(e.get("url", "")) + "|" + str(e.get("title", ""))).encode()).hexdigest()[:16]


def _is_primary(e):
    d = _domain(e.get("url", ""))
    return any(d == x or d.endswith("." + x) for x in PRIMARY_DOMAINS)


def _target_events(events):
    return [e for e in events if _has_target(e)]


def evidence_score(events):
    events = list(events or [])
    target = _target_events(events)
    action = [e for e in target if any(t in _text(e) for t in ACTION_TERMS)]
    families = {_source_family(e) for e in target if _source_family(e) and _source_family(e) not in SEARCH_ENGINES}
    primary = sum(_is_primary(e) for e in target)
    direct = 30 if any(_root_event(e) for e in events) else 0
    neg = sum(_is_negative(e) for e in events)
    score = max(0, min(100, min(30, len(action) * 8) + min(25, max(0, len(families) - 1) * 8) + min(25, primary * 10) + direct - min(35, neg * 8)))
    return {"score": score, "target_events": len(target), "action_events": len(action), "independent_domains": len(families), "source_families": len(families), "primary_events": primary, "negative_indicators": neg}


def build_forecast(events):
    events = list(events or [])
    active = sorted({s for s in (_stage(e) for e in events) if s > 0})
    max_stage = max(active, default=0)
    families = {_source_family(e) for e in events if _source_family(e) and _source_family(e) not in SEARCH_ENGINES}
    regions = {str(e.get("region", "")).strip() for e in events if str(e.get("region", "")).strip()}
    negative = sum(_is_negative(e) for e in events)
    now = datetime.now(timezone.utc).timestamp()
    recent = sum(1 for e in events if _timestamp(e) and 0 <= now - _timestamp(e) <= 3 * 86400)
    older = sum(1 for e in events if _timestamp(e) and 3 * 86400 < now - _timestamp(e) <= 14 * 86400)
    acceleration = 1.0 if not older and recent else (round(min(3.0, recent / older), 2) if older else 0.0)
    ordered = active == list(range(1, max_stage + 1)) if max_stage else False
    structure = max(0, min(95, int(8 + min(32, len(active) * 8 + (6 if ordered else 0)) + min(24, max(0, len(families) - 1) * 8) + min(12, max(0, len(regions) - 1) * 3) + min(12, max(0, acceleration - 1) * 6) - min(30, negative * 10))))
    ev = evidence_score(events)
    if max_stage >= 4:
        nxt, horizon = "root_scenario", "24-72h"
    elif max_stage == 3:
        nxt, horizon = "operational_implementation", "24h-7d"
    elif max_stage == 2:
        nxt, horizon = "organizational_or_logistical_action", "3-14d"
    else:
        nxt, horizon = "administrative_preparation", "7-30d"
    return {"scenario_id": SCENARIO_ID, "pattern_stage": max_stage, "pattern_stage_name": STAGES[max_stage][0], "observed_stages": [STAGES[n][0] for n in active], "next_stage": nxt, "next_event_horizon": horizon, "independent_domains": len(families), "source_families": len(families), "regions_with_signals": len(regions), "acceleration": acceleration, "structure_score": structure, "evidence_score": ev["score"], "evidence_metrics": ev, "negative_indicators": negative, "interpretation": "ordered multi-stage chain is forming" if len(active) >= 2 and max_stage >= 2 else "isolated or early-stage signals; chain not established", "_events": events}


def _deadline(now, horizon):
    return now + {"24-72h": 72, "24h-7d": 168, "3-14d": 336, "7-30d": 720}.get(horizon, 720) * 3600


def _target_fingerprint(events, horizon):
    relevant = [e for e in events if _stage(e) > 0 or _root_event(e)]
    strongest = sorted(relevant, key=lambda e: (_stage(e), _timestamp(e)), reverse=True)[:12]
    ids = sorted({_eid(e) for e in strongest})
    return hashlib.sha256((SCENARIO_ID + "|" + horizon + "|" + ",".join(ids)).encode()).hexdigest()[:16]


def forecast_record(forecast, probability, now=None, evidence_ids=None, calibrated_probability=None):
    now = float(now if now is not None else datetime.now(timezone.utc).timestamp())
    horizon = forecast.get("next_event_horizon", "7-30d")
    ids = list(evidence_ids or [])
    fp = _target_fingerprint(forecast.get("_events", []), horizon) if forecast.get("_events") else hashlib.sha256((SCENARIO_ID + "|" + horizon + "|" + ",".join(sorted(ids))).encode()).hexdigest()[:16]
    raw = max(0, min(100, int(probability)))
    issued = raw if calibrated_probability is None else max(0, min(100, float(calibrated_probability)))
    return {"forecast_id": fp + "-" + str(int(now)), "scenario_id": SCENARIO_ID, "created_ts": now, "horizon": horizon, "deadline_ts": _deadline(now, horizon), "target": SCENARIO_ID, "predicted_stage": forecast.get("next_stage", "baseline"), "probability": raw, "raw_probability": raw, "issued_probability": issued, "structure_score": int(forecast.get("structure_score", 0)), "evidence_score": int(forecast.get("evidence_score", 0)), "evidence_ids": ids, "evidence_fingerprint": fp, "resolved": False, "outcome": None, "resolved_ts": None, "brier": None, "issued_brier": None}


def _root_outcome(events, start_ts=None, end_ts=None):
    for e in events:
        ts = _timestamp(e)
        if not ts:
            continue
        if start_ts is not None and ts < start_ts:
            continue
        if end_ts is not None and ts > end_ts:
            continue
        if _root_event(e):
            return True
    return False


def resolve_forecasts(records, events, now=None):
    now = float(now if now is not None else datetime.now(timezone.utc).timestamp())
    out = []
    for rec in records:
        if rec.get("resolved") or now < float(rec.get("deadline_ts", 0)):
            out.append(rec)
            continue
        start = float(rec.get("created_ts", 0))
        deadline = float(rec.get("deadline_ts", now))
        outcome = 1 if _root_outcome(events, start_ts=start, end_ts=deadline) else 0
        rec = dict(rec)
        raw = rec.get("raw_probability", rec.get("probability", 0))
        issued = rec.get("issued_probability", raw)
        rec.update({"resolved": True, "outcome": outcome, "resolved_ts": now, "brier": _brier(raw, outcome), "issued_brier": _brier(issued, outcome)})
        out.append(rec)
    return out


def _brier(probability, outcome):
    return round((max(0, min(1, float(probability) / 100)) - float(outcome)) ** 2, 6)


def _resolved(records):
    return [r for r in records if r.get("resolved") and r.get("outcome") is not None and r.get("scenario_id", SCENARIO_ID) == SCENARIO_ID]


def calibrate_probability(raw_probability, records, horizon=None):
    done = _resolved(records)
    if horizon:
        horizon_done = [r for r in done if r.get("horizon") == horizon]
        if len(horizon_done) >= 30:
            done = horizon_done
    n = len(done)
    raw = max(0, min(100, int(raw_probability)))
    if n < 30:
        return {"probability": None, "status": "insufficient_history", "sample": n, "raw": raw, "horizon": horizon}
    bucket = min(9, raw // 10)
    prior = [r for r in done if min(9, int(r.get("raw_probability", r.get("probability", 0))) // 10) == bucket]
    if len(prior) < 5:
        return {"probability": None, "status": "insufficient_bin_history", "sample": n, "bin_sample": len(prior), "raw": raw, "horizon": horizon}
    rate = (sum(int(r.get("outcome", 0)) for r in prior) + 1) / (len(prior) + 2)
    return {"probability": round(rate * 100, 1), "status": "preliminary" if n < 100 else "measured", "sample": n, "bin_sample": len(prior), "raw": raw, "horizon": horizon}


def calibration_summary(records):
    done = _resolved(records)
    if not done:
        return {"resolved": 0, "brier": None, "issued_brier": None, "brier_skill_score": None, "issued_brier_skill_score": None, "calibration_status": "insufficient_history"}
    raw_brier = round(sum(float(r.get("brier", _brier(r.get("raw_probability", r.get("probability", 0)), r.get("outcome", 0)))) for r in done) / len(done), 6)
    issued_brier = round(sum(float(r.get("issued_brier", _brier(r.get("issued_probability", r.get("raw_probability", 0)), r.get("outcome", 0)))) for r in done) / len(done), 6)
    base = sum(float(r.get("outcome", 0)) for r in done) / len(done)
    baseline = base * (1 - base)
    raw_skill = round(1 - raw_brier / baseline, 6) if baseline else None
    issued_skill = round(1 - issued_brier / baseline, 6) if baseline else None
    bins = defaultdict(list)
    for r in done:
        p = r.get("issued_probability", r.get("raw_probability", r.get("probability", 0)))
        bins[min(9, int(float(p)) // 10)].append(r.get("outcome", 0))
    cal = [{"range": f"{b*10}-{b*10+9}", "n": len(v), "empirical_rate": round(sum(v) / len(v) * 100, 1)} for b, v in sorted(bins.items())]
    n = len(done)
    status = "insufficient_history" if n < 30 else ("preliminary" if n < 100 else "measured")
    return {"resolved": n, "base_rate": round(base * 100, 2), "brier": raw_brier, "issued_brier": issued_brier, "brier_skill_score": raw_skill, "issued_brier_skill_score": issued_skill, "calibration": cal, "calibration_status": status}


def render_context(forecast, calibration=None):
    text = "PATTERN_ENGINE\n" + "\n".join(f"{k}={v}" for k, v in forecast.items() if not k.startswith("_"))
    if calibration:
        text += "\nCALIBRATION=" + str(calibration)
    return text + "\nstructure_score and evidence_score are evidence-strength measures, not probabilities; root probability requires temporal historical calibration."
