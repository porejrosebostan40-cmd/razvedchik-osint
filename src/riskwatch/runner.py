import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from .config import SETTINGS, REGIONS, SOURCE_TEMPLATES, REGIONAL_TEMPLATES, CORE_TERMS
from .search import search
from .store import Store
from .ai import analyze

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


def _throttled_decision(store, events):
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
            "analysis_provider":"cached",
        }
    return analyze(events)


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
    if store.ai_due():
        store.mark_ai_attempt()
        decision=analyze(store.recent(120))
    else:
        decision=_throttled_decision(store,events)
    store.save_decision(decision)
    p=int(decision.get("probability",0))
    risk=int(decision.get("risk",0))
    c=int(decision.get("confidence",0))
    if risk>=SETTINGS.alert_threshold or p>=SETTINGS.alert_threshold:
        telegram(
            "RISKWATCH ALERT\n\n"
            "Сценарий: мобилизационные/связанные с ФСИН действия после 20.09.2026\n"
            "Вероятность: %s%%\nРиск: %s/100\nУверенность: %s%%\n"
            "Решение: %s\n\n%s\n\nСигналы: %s\n"
            "Отсутствующие индикаторы: %s" % (
                p,risk,c,decision.get('decision',''),decision.get('reason',''),
                '; '.join(decision.get('signals',[])[:6]),
                '; '.join(decision.get('missing_indicators',[])[:6])
            )
        )
    return decision
