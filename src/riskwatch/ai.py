import json, re, requests
from .config import SETTINGS

SYSTEM='''Ты аналитическое ядро системы раннего предупреждения. Анализируй только переданные факты. Не превращай слух в факт. Отделяй официальное подтверждение, независимое подтверждение, слух и отсутствие данных. Не утверждай, что событие произойдет. Оцени сценарий, вероятность, уверенность и риск для человека, находящегося в учреждении ФСИН. Учитывай временную последовательность, независимость источников, повторяемость признаков и альтернативные объяснения. Верни только JSON с полями probability, confidence, risk, decision, reason, signals, missing_indicators.'''


def _fallback(events, reason):
    official=sum(1 for e in events if any(x in e.get('url','') for x in ('kremlin.ru','government.ru','mil.ru','fsin.gov.ru','minjust.gov.ru','duma.gov.ru','council.gov.ru','publication.pravo.gov.ru')))
    regional=sum(1 for e in events if e.get('region'))
    probability=min(90,20+official*3+min(regional,20)*2)
    confidence=min(80,20+official*2+min(regional,20))
    risk=min(90,probability)
    return {"probability":probability,"confidence":confidence,"risk":risk,"decision":"WATCH","reason":reason,"signals":[f"official_or_primary_results={official}",f"regional_results={regional}"],"missing_indicators":["direct official decision confirming the scenario"]}


def _extract_json(text):
    if not isinstance(text,str):
        raise ValueError("empty or non-text model output")
    cleaned=text.strip()
    if cleaned.startswith("```"):
        cleaned=re.sub(r"^```(?:json)?\s*|\s*```$","",cleaned,flags=re.I|re.S).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start=cleaned.find("{")
        end=cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("model output does not contain JSON")
        return json.loads(cleaned[start:end+1])


def _response_text(data):
    text=data.get("output_text")
    if isinstance(text,str) and text.strip():
        return text
    chunks=[]
    for item in data.get("output",[]):
        for c in item.get("content",[]):
            if c.get("type")=="output_text" and isinstance(c.get("text"),str):
                chunks.append(c["text"])
    return "\n".join(chunks)


def _score(value):
    if isinstance(value,(int,float)):
        return max(0,min(100,int(value)))
    if isinstance(value,str):
        m=re.search(r"-?\d+(?:[.,]\d+)?",value.replace("%",""))
        if m:
            return max(0,min(100,int(float(m.group(0).replace(",",".")))))
    raise ValueError(f"invalid score: {value!r}")


def analyze(events):
    if not SETTINGS.openai_api_key:
        return _fallback(events,"OPENAI_API_KEY is not configured; deterministic fallback used")
    payload={
        "model":SETTINGS.openai_model,
        "input":[
            {"role":"system","content":SYSTEM},
            {"role":"user","content":json.dumps({"scenario":"мобилизационные или связанные с ФСИН действия после 20 сентября 2026 года","events":events[-100:]},ensure_ascii=False)}
        ],
        "text":{"format":{"type":"json_object"}},
        "store":False
    }
    try:
        r=requests.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {SETTINGS.openai_api_key}","Content-Type":"application/json"},json=payload,timeout=60)
        r.raise_for_status()
        data=r.json()
        result=_extract_json(_response_text(data))
        if not isinstance(result,dict):
            raise ValueError("model JSON is not an object")
        for k in ('probability','confidence','risk'):
            result[k]=_score(result.get(k,0))
        result.setdefault("decision","WATCH")
        result.setdefault("reason","OpenAI analysis completed")
        result.setdefault("signals",[])
        result.setdefault("missing_indicators",[])
        result["analysis_provider"]="openai"
        return result
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        return _fallback(events,f"OpenAI analysis failed: {type(exc).__name__}; deterministic fallback used")
