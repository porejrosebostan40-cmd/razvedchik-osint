import os
import hashlib
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from .config import SETTINGS, REGIONS, SOURCE_TEMPLATES, REGIONAL_TEMPLATES, CORE_TERMS
from .search import search
from .store import Store
from .ai import analyze
from .forecast import build_forecast, forecast_record, calibration_summary, calibrate_probability, render_context, _stage, _timestamp, _brier, _has_target
from .evidence import build_evidence_graph, compact_chain
from .semantics import safe_root_event

BATCH_SIZE = 30
MAX_WORKERS = 8
SCENARIO_ID = 'prisoner_mobilization'
SCENARIO_QUESTION = 'Будут ли мужчин из мест лишения свободы, прежде всего из исправительных колоний, мобилизовывать/привлекать к военной службе после 20 сентября 2026 года?'


def _region(label):
    for r in REGIONS:
        if r in label:
            return r
    return ''


def _regional_matrix():
    terms = ' OR '.join(f'"{x}"' for x in CORE_TERMS)
    return [(f'{n}: {r}', t.format(region=r, terms=terms)) for r in REGIONS for n, t in REGIONAL_TEMPLATES]


def _queries(now):
    """Legacy time-slot query builder retained only for compatibility tests; production uses _queries_from_cursor."""
    terms = ' OR '.join(f'"{x}"' for x in CORE_TERMS)
    core = [(n, t.format(terms=terms)) for n, t in SOURCE_TEMPLATES]
    regional = _regional_matrix()
    if not regional:
        return core
    slot = int(now.timestamp()) // 1200
    start = (slot * BATCH_SIZE) % len(regional)
    return core + [regional[(start + i) % len(regional)] for i in range(min(BATCH_SIZE, len(regional)))]


def _queries_from_cursor(cursor=0):
    terms = ' OR '.join(f'"{x}"' for x in CORE_TERMS)
    core = [(n, t.format(terms=terms)) for n, t in SOURCE_TEMPLATES]
    regional = _regional_matrix()
    if not regional:
        return core, int(cursor or 0), False
    start = int(cursor or 0) % len(regional)
    remaining = len(regional) - start
    batch_len = min(BATCH_SIZE, remaining)
    batch = regional[start:start + batch_len]
    next_cursor = start + batch_len
    wrapped = next_cursor == len(regional)
    if wrapped:
        next_cursor = 0
    return core + batch, next_cursor, wrapped


def _collect_one(item):
    label, q = item
    try:
        results = search(q)
        for e in results:
            e['region'] = _region(label)
            e['kind'] = label
        return results, False
    except Exception:
        return [], True


def _throttled_decision(store):
    previous = store.last_decision()
    if previous:
        return {k: previous.get(k, v) for k, v in {
            'probability': None, 'confidence': 0, 'risk': None, 'decision': 'WATCH',
            'reason': 'AI call throttled; previous decision reused', 'signals': [],
            'missing_indicators': [], 'next_event': 'UNKNOWN', 'horizon': 'UNKNOWN',
            'forecast_basis': '', 'pattern': {}, 'scenario_answer': 'UNKNOWN',
            'analysis_provider': 'cached'
        }.items()}
    return {
        'scenario_id': SCENARIO_ID,
        'scenario_question': SCENARIO_QUESTION,
        'scenario_answer': 'UNKNOWN',
        'probability': None,
        'model_probability': None,
        'confidence': 0,
        'risk': None,
        'model_risk': None,
        'decision': 'WATCH',
        'reason': 'AI call throttled; no reservation acquired',
        'signals': [],
        'missing_indicators': [],
        'next_event': 'UNKNOWN',
        'horizon': 'UNKNOWN',
        'forecast_basis': '',
        'analysis_provider': 'not_called',
        'pattern': {},
        'evidence_chain': {},
        'analytical_status': 'NOT_ATTEMPTED',
    }


def _no_evidence_decision(pattern, chain, signals):
    return {
        'scenario_id': SCENARIO_ID,
        'scenario_question': SCENARIO_QUESTION,
        'scenario_answer': 'UNKNOWN',
        'probability': None,
        'model_probability': None,
        'confidence': 0,
        'risk': None,
        'model_risk': None,
        'decision': 'WATCH',
        'reason': 'No target-specific evidence events survived retrieval/URL validation; analysis not performed',
        'facts': [],
        'inferences': [],
        'evidence_event_ids': [],
        'signals': signals,
        'missing_indicators': ['валидные результаты публичного поиска', 'независимые источники', 'target-specific evidence'],
        'next_event': 'UNKNOWN',
        'horizon': 'UNKNOWN',
        'forecast_basis': 'no evidence',
        'analysis_provider': 'not_called',
        'hallucination_guard': 'not_run_no_evidence',
        'pattern': pattern,
        'evidence_chain': chain,
        'analytical_status': 'FAILED_NO_EVIDENCE',
    }


def _analytical_status(decision):
    provider = decision.get('analysis_provider')
    if provider == 'fallback':
        return 'FAILED_AI'
    if provider == 'not_called' or provider == 'cached':
        return 'NOT_ATTEMPTED'
    if provider == 'openai' and str(decision.get('hallucination_guard', '')).startswith('passed_evidence_gate'):
        return 'OK'
    return 'FAILED_AI'


def telegram(text):
    if not SETTINGS.telegram_token or not SETTINGS.telegram_chat_id:
        return
    try:
        requests.post(f'https://api.telegram.org/bot{SETTINGS.telegram_token}/sendMessage', json={'chat_id': SETTINGS.telegram_chat_id, 'text': text[:4000]}, timeout=20)
    except requests.RequestException:
        pass


def _evidence_ids(events):
    relevant = [e for e in events if _stage(e) > 0 or safe_root_event(e)]
    relevant = sorted(relevant, key=lambda e: (_stage(e), e.get('published_ts', e.get('published', e.get('date', 0)))), reverse=True)[:20]
    return [hashlib.sha256((str(e.get('url', '')) + '|' + str(e.get('title', ''))).encode()).hexdigest()[:16] for e in relevant]


def _episode_duplicate(store, forecast, evidence_ids):
    recent = [r for r in store.forecasts() if r.get('scenario_id') == SCENARIO_ID and not r.get('resolved')]
    fp = forecast_record(forecast, 0, evidence_ids=evidence_ids).get('evidence_fingerprint')
    now = datetime.now(timezone.utc).timestamp()
    return any(r.get('evidence_fingerprint') == fp and now - float(r.get('created_ts', 0)) < 6 * 3600 for r in recent)


def _root_outcome(events, start_ts, end_ts):
    for e in events:
        ts = _timestamp(e)
        if not ts:
            continue
        if ts < start_ts or ts > end_ts:
            continue
        if safe_root_event(e):
            return True
    return False


def _resolve_forecasts(records, events, now=None):
    now = float(now if now is not None else datetime.now(timezone.utc).timestamp())
    out = []
    for rec in records:
        if rec.get('resolved') or now < float(rec.get('deadline_ts', 0)):
            out.append(rec)
            continue
        start = float(rec.get('created_ts', 0))
        deadline = float(rec.get('deadline_ts', now))
        outcome = 1 if _root_outcome(events, start, deadline) else 0
        rec = dict(rec)
        raw = rec.get('raw_probability', rec.get('probability', 0))
        issued = rec.get('issued_probability', raw)
        rec.update({'resolved': True, 'outcome': outcome, 'resolved_ts': now, 'brier': _brier(raw, outcome), 'issued_brier': _brier(issued, outcome)})
        out.append(rec)
    return out


def _retrieval_telemetry(items, collected, new_events=0, previous_total=0):
    regional_items = [x for x in items if x[0].startswith(('regional', 'region')) or ': ' in x[0]]
    with_results = sum(bool(collected.get(i, [])) for i in range(len(items)))
    regional_with_results = sum(bool(collected.get(i, [])) for i, item in enumerate(items) if item in regional_items)
    attempted = len(items)
    score = round(100 * with_results / attempted, 1) if attempted else 0.0
    filter_counts = {'raw_results':0,'after_search_url_filter':0,'after_site_filter':0,'after_dedup':0}
    for result in collected.values():
        telemetry=getattr(result,'telemetry',{}) or {}
        for key in filter_counts:
            filter_counts[key]+=int(telemetry.get(key,0) or 0)
    filter_counts['events_after_dedup']=int(new_events)
    filter_counts['events_total_valid']=int(previous_total + new_events)
    return {
        'queries_attempted': attempted,
        'queries_with_results': with_results,
        'regional_queries_attempted': len(regional_items),
        'regional_queries_with_results': regional_with_results,
        'result_count': sum(len(v) for v in collected.values()),
        'retrieval_coverage_score': score,
        'coverage_is_retrieval_not_reality': True,
        'filter_counts': filter_counts,
    }


def run():
    store = Store()
    events = []
    cursor = int(store.get_meta('regional_cursor', 0) or 0)
    cycle = int(store.get_meta('regional_cycle', 0) or 0)
    items, next_cursor, wrapped = _queries_from_cursor(cursor)
    collected = {}
    collection_failed = False
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_collect_one, item): i for i, item in enumerate(items)}
        for future in as_completed(futures):
            i = futures[future]
            result, failed = future.result()
            collected[i] = result
            collection_failed = collection_failed or failed
            events.extend(result)

    previous_total = len(store.recent(3000))
    # TEMP: pre-A1 dump
    import json
    from pathlib import Path
    Path("/tmp/riskwatch_pre_a1.json").write_text(
        json.dumps([
            {
                "url": e.get("url", ""),
                "title": e.get("title", ""),
                "snippet": e.get("snippet", ""),
                "query": e.get("query", ""),
                "region": e.get("region", ""),
            }
            for e in events
        ], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    import sys
    print(f"DEBUG PRE-A1: {len(events)} events", file=sys.stderr)
    # END TEMP
    new_events = store.add_events([e for e in events if _has_target(e)])
    if not collection_failed:
        store.set_meta('regional_cursor', next_cursor)
        if wrapped:
            store.set_meta('regional_cycle', cycle + 1)
    all_events = store.recent(3000)
    resolved = _resolve_forecasts(store.forecasts(), all_events)
    if resolved != store.forecasts():
        store.replace_forecasts(resolved)

    scenario_events = [e for e in all_events if _has_target(e)]
    pattern = build_forecast(scenario_events)
    graph = build_evidence_graph(all_events)
    chain = compact_chain(graph)
    pattern['evidence_chain'] = chain
    pattern['retrieval'] = _retrieval_telemetry(items, collected, new_events, previous_total)
    pattern['retrieval']['regional_cursor'] = int(store.get_meta('regional_cursor', 0) or 0)
    pattern['retrieval']['regional_cycle'] = int(store.get_meta('regional_cycle', 0) or 0)
    pattern['retrieval']['regional_batch_wrapped'] = wrapped
    pattern['retrieval']['regional_collection_failed'] = collection_failed
    signals = [f"pattern_stage={pattern.get('pattern_stage',0)}", f"structure_score={pattern.get('structure_score',0)}"]

    if not all_events or not graph.get('nodes'):
        decision = _no_evidence_decision(pattern, chain, signals)
        decision['calibration'] = calibration_summary(resolved)
        decision['probability_calibration'] = {'probability': None, 'status': 'no_evidence', 'sample': len([r for r in resolved if r.get('resolved')])}
        store.save_decision(decision)
        return decision

    calibration = calibration_summary(resolved)
    if os.getenv("RESERVATION_OK", "").lower() == "true":
        decision = analyze(scenario_events, pattern, graph)
    else:
        decision = _throttled_decision(store)

    raw_model_probability = decision.get('probability')
    model_probability = int(raw_model_probability) if isinstance(raw_model_probability, (int, float)) else 0
    horizon = pattern.get('next_event_horizon')
    cal = calibrate_probability(model_probability, resolved, horizon=horizon)
    calibrated = cal.get('status') in ('preliminary', 'measured')
    calibrated_probability = float(cal.get('probability')) if calibrated else None
    issued_probability = calibrated_probability if calibrated else None

    decision['model_probability'] = model_probability if raw_model_probability is not None else None
    decision['probability'] = issued_probability
    decision['probability_calibration'] = cal
    decision['model_risk'] = int(decision.get('risk', 0)) if decision.get('risk') is not None else 0
    decision['risk'] = round(issued_probability) if calibrated else None
    decision['pattern'] = pattern
    decision['signals'] = signals
    decision['calibration'] = calibration
    decision['evidence_chain'] = chain
    decision['scenario_question'] = SCENARIO_QUESTION
    decision['next_event'] = pattern.get('next_stage', 'UNKNOWN')
    decision['horizon'] = horizon or 'UNKNOWN'
    decision['forecast_basis'] = render_context(pattern, calibration)
    decision['analytical_status'] = _analytical_status(decision)

    evidence_ids = _evidence_ids(all_events)
    if not _episode_duplicate(store, pattern, evidence_ids):
        store.save_forecast(forecast_record(pattern, model_probability, evidence_ids=evidence_ids, calibrated_probability=issued_probability))
    store.save_decision(decision)

    p = float(decision.get('probability')) if decision.get('probability') is not None else None
    c = int(decision.get('confidence', 0))
    answer = decision.get('scenario_answer', 'UNKNOWN')
    structural_warning = (not calibrated and int(pattern.get('evidence_score', 0)) >= 75 and int(pattern.get('structure_score', 0)) >= 65 and int(chain.get('metrics', {}).get('chain_score', 0)) >= 55)
    if (calibrated and p >= SETTINGS.alert_threshold) or structural_warning:
        alert_type = 'CALIBRATED_RISK_ALERT' if calibrated else 'STRUCTURAL_WARNING_UNCALIBRATED'
        probability_text = f'{p:.1f}%' if p is not None else 'UNAVAILABLE'
        telegram('RISKWATCH %s\n\n%s\n\nОтвет системы: %s\nКалиброванная вероятность: %s\nМодельная некалиброванная оценка: %s%%\nМодельный риск: %s/100\nУверенность модели: %s%%\n\nСледующий вероятный шаг: %s\nГоризонт: %s\nЦепь доказательств: %s/100\n\n%s\n\nСигналы: %s\nОтсутствующие индикаторы: %s' % (
            alert_type, SCENARIO_QUESTION, answer, probability_text, decision.get('model_probability', 0), decision.get('model_risk', 0), c,
            decision.get('next_event', 'UNKNOWN'), decision.get('horizon', 'UNKNOWN'), chain.get('metrics', {}).get('chain_score', 0), decision.get('reason', ''),
            '; '.join(decision.get('signals', [])[:6]), '; '.join(decision.get('missing_indicators', [])[:6])
        ))
    return decision
