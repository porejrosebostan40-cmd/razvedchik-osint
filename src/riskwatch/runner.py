import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from .config import SETTINGS, REGIONS, SOURCE_TEMPLATES, REGIONAL_TEMPLATES, CORE_TERMS
from .search import search
from .store import Store
from .ai import analyze
from .forecast import build_forecast, forecast_record, resolve_forecasts, calibration_summary, render_context

BATCH_SIZE=30
MAX_WORKERS=8
SCENARIO_QUESTION='Будут ли мужчин из мест лишения свободы, прежде всего из исправительных колоний, мобилизовывать/привлекать к военной службе после 20 сентября 2026 года?'


def _region(label):
    for r in REGIONS:
        if r in label:return r
    return ''


def _queries(now=None):
    terms=' OR '.join(f'"{x}"' for x in CORE_TERMS); core=[(n,t.format(terms=terms)) for n,t in SOURCE_TEMPLATES]; regional=[]
    for r in REGIONS:
        for n,t in REGIONAL_TEMPLATES:regional.append((f'{n}: {r}',t.format(region=r,terms=terms)))
    if not regional:return core
    now=now or datetime.now(timezone.utc); slot=int(now.timestamp()//60)//20; start=(slot*BATCH_SIZE)%len(regional)
    return core+[regional[(start+i)%len(regional)] for i in range(min(BATCH_SIZE,len(regional)))]


def _collect_one(item):
    label,q=item
    try:
        results=search(q)
        for e in results:e['region']=_region(label);e['kind']=label
        return results
    except Exception:return []


def _throttled_decision(store):
    previous=store.last_decision()
    if previous:
        return {k:previous.get(k,v) for k,v in {'probability':0,'confidence':0,'risk':0,'decision':'WATCH','reason':'AI call throttled; previous decision reused','signals':[],'missing_indicators':[],'next_event':'UNKNOWN','horizon':'UNKNOWN','forecast_basis':'','pattern':{},'scenario_answer':'UNKNOWN','analysis_provider':'cached'}.items()}
    return None


def telegram(text):
    if not SETTINGS.telegram_token or not SETTINGS.telegram_chat_id:return
    try:requests.post(f'https://api.telegram.org/bot{SETTINGS.telegram_token}/sendMessage',json={'chat_id':SETTINGS.telegram_chat_id,'text':text[:4000]},timeout=20)
    except requests.RequestException:pass


def _evidence_ids(events):
    import hashlib
    return [hashlib.sha256((str(e.get('url',''))+'|'+str(e.get('title',''))).encode()).hexdigest()[:16] for e in events[-50:]]


def _episode_duplicate(store, forecast, evidence_ids):
    """Do not create a new statistically independent forecast every 20 minutes."""
    recent=[r for r in store.forecasts() if r.get('scenario_id')=='prisoner_mobilization' and not r.get('resolved')]
    fp=forecast_record(forecast,0,evidence_ids=evidence_ids).get('evidence_fingerprint')
    now=datetime.now(timezone.utc).timestamp()
    for r in recent:
        if r.get('evidence_fingerprint')==fp and now-float(r.get('created_ts',0))<6*3600:
            return True
    return False


def run():
    store=Store();events=[]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures=[pool.submit(_collect_one,item) for item in _queries()]
        for future in as_completed(futures):events.extend(future.result())
    store.add_events(events);all_events=store.recent(3000)
    resolved=resolve_forecasts(store.forecasts(),all_events)
    if resolved!=store.forecasts():store.replace_forecasts(resolved)
    calibration=calibration_summary(resolved);pattern=build_forecast(all_events)
    if store.ai_due():store.mark_ai_attempt();decision=analyze(all_events)
    else:
        decision=_throttled_decision(store)
        if decision is None:decision=analyze(all_events)

    model_probability=int(decision.get('probability',0))
    # A number is labelled calibrated only after enough temporally resolved,
    # root-scenario forecasts exist. Until then it cannot trigger a probability alert.
    calibrated_probability=0
    if calibration.get('calibration_status') in ('preliminary','measured'):
        calibrated_probability=model_probability
    decision['model_probability']=model_probability
    decision['probability']=calibrated_probability
    decision['pattern']=pattern;decision['calibration']=calibration;decision['scenario_question']=SCENARIO_QUESTION
    decision['next_event']=pattern.get('next_stage','UNKNOWN');decision['horizon']=pattern.get('next_event_horizon','UNKNOWN');decision['forecast_basis']=render_context(pattern,calibration)

    evidence_ids=_evidence_ids(all_events)
    if not _episode_duplicate(store,pattern,evidence_ids):
        store.save_forecast(forecast_record(pattern,model_probability,evidence_ids=evidence_ids))
    store.save_decision(decision)

    # No alert is allowed to masquerade as a calibrated probability. Before calibration,
    # only a separately labelled deterministic structural warning may be emitted.
    p=int(decision.get('probability',0));risk=int(decision.get('risk',0));c=int(decision.get('confidence',0));answer=decision.get('scenario_answer','UNKNOWN')
    calibrated=calibration.get('calibration_status') in ('preliminary','measured')
    structural_warning=(not calibrated and int(pattern.get('evidence_score',0))>=75 and int(pattern.get('structure_score',0))>=65)
    if (calibrated and (risk>=SETTINGS.alert_threshold or p>=SETTINGS.alert_threshold)) or structural_warning:
        alert_type='CALIBRATED_RISK_ALERT' if calibrated else 'STRUCTURAL_WARNING_UNCALIBRATED'
        telegram('RISKWATCH %s\n\n%s\n\nОтвет системы: %s\nКалиброванная вероятность: %s%%\nМодельная некалиброванная оценка: %s%%\nРиск: %s/100\nУверенность: %s%%\n\nСледующий вероятный шаг: %s\nГоризонт: %s\n\n%s\n\nСигналы: %s\nОтсутствующие индикаторы: %s' % (alert_type,SCENARIO_QUESTION,answer,p,decision.get('model_probability',0),risk,c,decision.get('next_event','UNKNOWN'),decision.get('horizon','UNKNOWN'),decision.get('reason',''),'; '.join(decision.get('signals',[])[:6]),'; '.join(decision.get('missing_indicators',[])[:6])))
    return decision
