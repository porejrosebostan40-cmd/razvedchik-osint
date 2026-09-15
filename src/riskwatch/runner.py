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
        return {'probability':int(previous.get('probability',0)),'confidence':int(previous.get('confidence',0)),'risk':int(previous.get('risk',0)),'decision':previous.get('decision','WATCH'),'reason':'AI call throttled; previous decision reused','signals':previous.get('signals',[]),'missing_indicators':previous.get('missing_indicators',[]),'next_event':previous.get('next_event','UNKNOWN'),'horizon':previous.get('horizon','UNKNOWN'),'forecast_basis':previous.get('forecast_basis',''),'pattern':previous.get('pattern',{}),'scenario_answer':previous.get('scenario_answer','UNKNOWN'),'analysis_provider':'cached'}
    return None

def telegram(text):
    if not SETTINGS.telegram_token or not SETTINGS.telegram_chat_id:return
    try:requests.post(f'https://api.telegram.org/bot{SETTINGS.telegram_token}/sendMessage',json={'chat_id':SETTINGS.telegram_chat_id,'text':text[:4000]},timeout=20)
    except requests.RequestException:pass

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
    calibrated_probability=int(decision.get('probability',0)) if calibration.get('resolved',0)>=20 else 0
    decision['model_probability']=int(decision.get('probability',0));decision['probability']=calibrated_probability
    decision['pattern']=pattern;decision['calibration']=calibration;decision['scenario_question']=SCENARIO_QUESTION
    decision['next_event']=pattern.get('next_stage','UNKNOWN');decision['horizon']=pattern.get('next_event_horizon','UNKNOWN');decision['forecast_basis']=render_context(pattern,calibration)
    store.save_forecast(forecast_record(pattern,decision['model_probability']));store.save_decision(decision)
    p=int(decision.get('probability',0));risk=int(decision.get('risk',0));c=int(decision.get('confidence',0));answer=decision.get('scenario_answer','UNKNOWN')
    if risk>=SETTINGS.alert_threshold or p>=SETTINGS.alert_threshold:
        telegram('RISKWATCH ALERT\n\n'+SCENARIO_QUESTION+'\n\nОтвет системы: %s\nКалиброванная вероятность: %s%%\nМодельная некалиброванная оценка: %s%%\nРиск: %s/100\nУверенность: %s%%\n\nСледующий вероятный шаг: %s\nГоризонт: %s\n\n%s\n\nСигналы: %s\nОтсутствующие индикаторы: %s' % (answer,p,decision.get('model_probability',0),risk,c,decision.get('next_event','UNKNOWN'),decision.get('horizon','UNKNOWN'),decision.get('reason',''),'; '.join(decision.get('signals',[])[:6]),'; '.join(decision.get('missing_indicators',[])[:6])))
    return decision
