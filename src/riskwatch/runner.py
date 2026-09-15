import requests
from datetime import datetime, timezone
from .config import SETTINGS, REGIONS, SOURCE_TEMPLATES, REGIONAL_TEMPLATES, CORE_TERMS
from .search import search
from .store import Store
from .ai import analyze

def _region(label):
    for r in REGIONS:
        if r in label: return r
    return ""

def _queries():
    terms=' OR '.join(f'"{x}"' for x in CORE_TERMS)
    core=[(n,t.format(terms=terms)) for n,t in SOURCE_TEMPLATES]
    regional=[]
    for r in REGIONS:
        for n,t in REGIONAL_TEMPLATES: regional.append((f"{n}: {r}",t.format(region=r,terms=terms)))
    batch=60
    hours=int((datetime.now(timezone.utc)-datetime(2026,1,1,tzinfo=timezone.utc)).total_seconds()//3600)
    start=(hours*batch)%len(regional)
    return core+[regional[(start+i)%len(regional)] for i in range(batch)]

def telegram(text):
    if not SETTINGS.telegram_token or not SETTINGS.telegram_chat_id: return
    try: requests.post(f"https://api.telegram.org/bot{SETTINGS.telegram_token}/sendMessage",json={"chat_id":SETTINGS.telegram_chat_id,"text":text[:4000]},timeout=20)
    except requests.RequestException: pass

def run():
    store=Store(); events=[]
    for label,q in _queries():
        for e in search(q): e["region"]=_region(label); e["kind"]=label; events.append(e)
    store.add_events(events)
    decision=analyze(store.recent(120)); store.save_decision(decision)
    p=int(decision.get("probability",0)); risk=int(decision.get("risk",0)); c=int(decision.get("confidence",0))
    if risk>=SETTINGS.alert_threshold or p>=SETTINGS.alert_threshold:
        telegram("RISKWATCH ALERT\n\nСценарий: мобилизационные/связанные с ФСИН действия после 20.09.2026\nВероятность: %s%%\nРиск: %s/100\nУверенность: %s%%\nРешение: %s\n\n%s\n\nСигналы: %s\nОтсутствующие индикаторы: %s"%(p,risk,c,decision.get('decision',''),decision.get('reason',''),'; '.join(decision.get('signals',[])[:6]),'; '.join(decision.get('missing_indicators',[])[:6])))
    return decision
