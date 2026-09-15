import json, re, requests
from .config import SETTINGS

SYSTEM='''Ты аналитическое ядро системы раннего предупреждения. Анализируй только переданные факты. Не превращай слух в факт. Отделяй официальное подтверждение, независимое подтверждение, слух и отсутствие данных. Не утверждай, что событие произойдет. Оцени сценарий, вероятность, уверенность и риск для человека, находящегося в учреждении ФСИН. Если данных недостаточно, ставь probability=0 и confidence=0, а недостаток данных укажи в reason и missing_indicators. Поля probability, confidence и risk всегда должны быть целыми числами от 0 до 100, не объектами, не строками и не словами.'''


def _fallback(events, reason):
    official=sum(1 for e in events if any(x in e.get('url','') for x in ('kremlin.ru','government.ru','mil.ru','fsin.gov.ru','minjust.gov.ru','duma.gov.ru','council.gov.ru','publication.pravo.gov.ru')))
    regional=sum(1 for e in events if e.get('region'))
    probability=min(90,20+official*3+min(regional,20)*2)
    confidence=min(80,20+official*2+min(regional,20))
    risk=min(90,probability)
    return {"probability":probability,"confidence":confidence,"risk":risk,"decision":"WATCH","reason":reason,"signals":[f"official_or_primary_results={official}",f"regional_results={regional}"],"missing_indicators":["direct official decision confirming the scenario"]}


def _extract_json(text):
    if not isinstance(text,str):
        raise ValueError(f"empty or non-text model output: {text!r}")
    cleaned=text.strip()
    if cleaned.startswith("```"):
        cleaned=re.sub(r"^```(?:json)?\s*|\s*```$","",cleaned,flags=re.I|re.S).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as first_error:
        start=cleaned.find("{")
        end=cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(f"model output does not contain JSON: {cleaned[:300]!r}") from first_error
        try:
            return json.loads(cleaned[start:end+1])
        except json.JSONDecodeError as second_error:
            raise ValueError(f"invalid model JSON: {cleaned[:300]!r}") from second_error


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
    if isinstance(value,dict):
        return _score(value.get("value",0))
    if isinstance(value,(int,float)):
        return max(0,min(100,int(value)))
    if isinstance(value,str):
        m=re.search(r"-?\d+(?:[.,]\d+)?",value.replace("%",""))
        if m:
            return max(0,min(100,int(float(m.group(0).replace(",",".")))))
        if value.strip().lower() in {"неопределенная","неопределённая","unknown","uncertain","неизвестно"}:
            return 0
    return 0


def _compact_events(events, limit=60):
    compact=[]
    for e in events[-limit:]:
        compact.append({
            "url":str(e.get("url",""))[:1000],
            "title":str(e.get("title",""))[:500],
            "snippet":str(e.get("snippet",""))[:700],
            "region":str(e.get("region",""))[:120],
            "kind":str(e.get("kind",""))[:160],
            "source":str(e.get("source",""))[:80],
        })
    return compact


def analyze(events):
    if not SETTINGS.openai_api_key:
        return _fallback(events,"OPENAI_API_KEY is not configured; deterministic fallback used")
    compact_events=_compact_events(events)
    payload={
        "model":SETTINGS.openai_model,
        "instructions":SYSTEM,
        "input":json.dumps({"scenario":"мобилизационные или связанные с ФСИН действия после 20 сентября 2026 года","events":compact_events},ensure_ascii=False),
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
    except requests.HTTPError as exc:
        status=getattr(exc.response,"status_code",None)
        body=""
        try: body=exc.response.text[:300]
        except Exception: pass
        return _fallback(events,f"OpenAI analysis failed: HTTPError status={status} body={body}; deterministic fallback used")
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        detail=str(exc).replace("\n"," ")[:300]
        return _fallback(events,f"OpenAI analysis failed: {type(exc).__name__}: {detail}; deterministic fallback used")
