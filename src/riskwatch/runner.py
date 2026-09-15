import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from .config import SETTINGS, REGIONS, SOURCE_TEMPLATES, REGIONAL_TEMPLATES, CORE_TERMS
from .search import search
from .store import Store
from .ai import analyze
from .forecast import build_forecast, forecast_record, resolve_forecasts, calibration_summary, render_context

BATCH_SIZE = 30
MAX_WORKERS = 8


def _region(label):
    for r in REGIONS:
        if r in label:
            return r
    return ""


def _queries(now=None):
    terms=' OR '.join(f'"{x}"' for x in CORE_TERMS)
    core=[(n,t.format(terms=terms)) for n,t in SOURCE_TEMPLATES]
    regional=[]
    for r in REGIONS:
        for n,t in REGIONAL_TEMPLATES:
            regional.append((f"{n}: {r}",t.format(region=r,terms=terms)))
    if not regional:
        return core
    now = now or datetime.now(timezone.utc)
    minutes_since_epoch = int(now.timestamp() // 60)
    slot = minutes_since_epoch // 20
    start=(slot * BATCH_SIZE) % len(regional)
    return core+[regional[(start+i)%len(regional)] for i in range(min(BATCH_SIZE,len(regional)))]


def _collect_one(item):
    label,q=item
    try:
        results=search(q)
        for e in results:
            e["region"]=_region(label)
            e["kind"]=label
        return results
    except Exception:
        return []


def _throttled_decision(store):
    previous=store.last_decision()
    if previous:
        return {
            "probability":int(previous.get("probability",0)),
            "confidence":int(previous.get("confidence",0)),
            "risk":int(previous.get("risk",0)),
            "decision":previous.get("decision","WATCH"),
            "reason":"AI call throttled; previous decision reused",
            "signals":previous.get("signals",[]),
            "missing_indicators":previous.get("missing_indicators",[]),
            "next_event":previous.get("next_event","UNKNOWN"),
            "horizon":previous.get("horizon","UNKNOWN"),
            "forecast_basis":previous.get("forecast_basis",""),
            "pattern":previous.get("pattern",{}),
            "analysis_provider":"cached",
        }
    return None


def telegram(text):
    if not SETTINGS.telegram_token or not SETTINGS.telegram_chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{SETTINGS.telegram_token}/sendMessage",
            json={"chat_id":SETTINGS.telegram_chat_id,"text":text[:4000]},
            timeout=20,
        )
    except requests.RequestException:
        pass


def run():
    store=Store()
    events=[]
    queries=_queries()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures=[pool.submit(_collect_one,item) for item in queries]
        for future in as_completed(futures):
            events.extend(future.result())
    store.add_events(events)
    all_events=store.recent(3000)

    # Resolve forecasts only after their full horizon has elapsed.
    resolved=resolve_forecasts(store.forecasts(),all_events)
    if resolved != store.forecasts():
        store.replace_forecasts(resolved)
    calibration=calibration_summary(resolved)
    pattern=build_forecast(all_events)

    if store.ai_due():
        store.mark_ai_attempt()
        decision=analyze(all_events)
    else:
        decision=_throttled_decision(store)
        if decision is None:
            decision=analyze(all_events)

    # The model is not allowed to turn structural evidence into a "pretty" probability.
    # The probability is kept only when historical calibration exists; otherwise it is
    # treated as uncalibrated and forced to zero for alerting purposes.
    calibrated_probability=int(decision.get("probability",0)) if calibration.get("resolved",0) >= 20 else 0
    decision["model_probability"]=int(decision.get("probability",0))
    decision["probability"]=calibrated_probability
    decision["pattern"]=pattern
    decision["calibration"]=calibration
    decision["next_event"]=pattern.get("next_stage","UNKNOWN")
    decision["horizon"]=pattern.get("next_event_horizon","UNKNOWN")
    decision["forecast_basis"]=render_context(pattern,calibration)

    # Every nonzero model estimate becomes a forecast record, but it cannot influence
    # alerting until empirical history proves the estimate is calibrated.
    store.save_forecast(forecast_record(pattern,decision["model_probability"]))
    store.save_decision(decision)

    p=int(decision.get("probability",0))
    risk=int(decision.get("risk",0))
    c=int(decision.get("confidence",0))
    if risk>=SETTINGS.alert_threshold or p>=SETTINGS.alert_threshold:
        telegram(
            "RISKWATCH ALERT\n\n"
            "Сценарий: мобилизационные/связанные с ФСИН действия после 20.09.2026\n"
            "Вероятность: %s%%\nРиск: %s/100\nУверенность: %s%%\n"
            "Решение: %s\n\nСледующий вероятный шаг: %s\nГоризонт: %s\n\n"
            "%s\n\nСигналы: %s\nОтсутствующие индикаторы: %s" % (
                p,risk,c,decision.get('decision',''),decision.get('next_event','UNKNOWN'),decision.get('horizon','UNKNOWN'),
                decision.get('reason',''),'; '.join(decision.get('signals',[])[:6]),
                '; '.join(decision.get('missing_indicators',[])[:6])
            )
        )
    return decision
