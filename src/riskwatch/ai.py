import json, requests
from .config import SETTINGS
SYSTEM='''Ты аналитическое ядро системы раннего предупреждения. Анализируй только переданные факты. Не превращай слух в факт. Отделяй официальное подтверждение, независимое подтверждение, слух и отсутствие данных. Не утверждай, что событие произойдет. Оцени сценарий, вероятность, уверенность и риск для человека, находящегося в учреждении ФСИН. Учитывай временную последовательность, независимость источников, повторяемость признаков и альтернативные объяснения. Верни только JSON с полями probability, confidence, risk, decision, reason, signals, missing_indicators.'''
def _fallback(events, reason):
    official=sum(1 for e in events if any(x in e.get('url','') for x in ('kremlin.ru','government.ru','mil.ru','fsin.gov.ru','minjust.gov.ru','duma.gov.ru','council.gov.ru','publication.pravo.gov.ru')))
    regional=sum(1 for e in events if e.get('region'))
    probability=min(90,20+official*3+min(regional,20)*2)
    confidence=min(80,20+official*2+min(regional,20))
    risk=min(90,probability)
    return {"probability":probability,"confidence":confidence,"risk":risk,"decision":"WATCH","reason":reason,"signals":[f"official_or_primary_results={official}",f"regional_results={regional}"],"missing_indicators":["direct official decision confirming the scenario"]}
def analyze(events):
    if not SETTINGS.openai_api_key: return _fallback(events,"OPENAI_API_KEY is not configured; deterministic fallback used")
    payload={"model":SETTINGS.openai_model,"input":[{"role":"system","content":SYSTEM},{"role":"user","content":json.dumps({"scenario":"мобилизационные или связанные с ФСИН действия после 20 сентября 2026 года","events":events[-100:]},ensure_ascii=False)}],"text":{"format":{"type":"json_object"}},"store":False}
    try:
        r=requests.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {SETTINGS.openai_api_key}","Content-Type":"application/json"},json=payload,timeout=60); r.raise_for_status(); data=r.json()
        text=data.get("output_text","")
        if not text:
            for item in data.get("output",[]):
                for c in item.get("content",[]):
                    if c.get("type")=="output_text": text=c.get("text","")
        result=json.loads(text)
        for k in ('probability','confidence','risk'): result[k]=max(0,min(100,int(result.get(k,0))))
        return result
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        return _fallback(events,f"OpenAI analysis failed: {type(exc).__name__}; deterministic fallback used")
