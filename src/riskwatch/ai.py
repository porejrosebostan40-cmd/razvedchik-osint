import hashlib, json, re, requests
from urllib.parse import urlsplit
from .config import SETTINGS

SYSTEM='''Ты аналитическое ядро системы раннего предупреждения с ЖЕСТКИМ КОНТРОЛЕМ ДОКАЗАТЕЛЬСТВ.
Работай только с переданными событиями. Ничего не додумывай, не дополняй памятью модели и не используй внешние знания.
Любое утверждение о факте должно ссылаться на один или несколько event_id из входных данных.
Если подтверждения нет — пиши UNKNOWN, а не предположение.
Разделяй FACT (прямо подтверждено источником), INFERENCE (логический вывод из нескольких FACT) и UNKNOWN.
Не называй слух, пересказ, комментарий или единичное сообщение подтвержденным фактом.
Не считай несколько публикаций независимым подтверждением, если они относятся к одному домену или явно перепечатывают один источник.
Для высокой вероятности нужны независимые подтверждения из разных доменов. probability выше 90 разрешена только при наличии минимум двух событий с разными доменами и хотя бы одного официального/первичного источника либо двух независимых первичных источников.
confidence не может быть выше качества доказательств. При отсутствии достаточных доказательств probability=0 и confidence=0.
risk не должен использоваться для повышения probability.
Не предсказывай событие только потому, что оно возможно или логично.
Верни только JSON и обязательно поля: probability, confidence, risk, decision, reason, facts, inferences, evidence_event_ids, missing_indicators.
В facts и inferences каждый объект должен содержать text и event_ids.
'''

PRIMARY_DOMAINS=('kremlin.ru','government.ru','mil.ru','fsin.gov.ru','minjust.gov.ru','duma.gov.ru','council.gov.ru','publication.pravo.gov.ru')


def _eid(e):
    return hashlib.sha256((str(e.get('url',''))+'|'+str(e.get('title',''))).encode()).hexdigest()[:16]


def _domain(url):
    try: return urlsplit(str(url)).netloc.lower().split(':')[0].removeprefix('www.')
    except ValueError: return ''


def _is_primary(url):
    domain=_domain(url)
    return any(domain==d or domain.endswith('.'+d) for d in PRIMARY_DOMAINS)


def _fallback(events, reason):
    official=sum(1 for e in events if _is_primary(e.get('url','')))
    regional=sum(1 for e in events if e.get('region'))
    return {
        'probability':0,'confidence':0,'risk':0,'decision':'WATCH','reason':reason,
        'facts':[],'inferences':[],'evidence_event_ids':[],
        'signals':[f'official_or_primary_results={official}',f'regional_results={regional}'],
        'missing_indicators':['direct official decision confirming the scenario','independent corroboration'],
        'hallucination_guard':'fallback_no_claim_without_evidence','analysis_provider':'fallback'
    }


def _extract_json(text):
    if not isinstance(text,str): raise ValueError(f'empty or non-text model output: {text!r}')
    cleaned=text.strip()
    if cleaned.startswith('```'): cleaned=re.sub(r'^```(?:json)?\s*|\s*```$','',cleaned,flags=re.I|re.S).strip()
    try: return json.loads(cleaned)
    except json.JSONDecodeError as first_error:
        start,end=cleaned.find('{'),cleaned.rfind('}')
        if start<0 or end<=start: raise ValueError(f'model output does not contain JSON: {cleaned[:300]!r}') from first_error
        try: return json.loads(cleaned[start:end+1])
        except json.JSONDecodeError as second_error: raise ValueError(f'invalid model JSON: {cleaned[:300]!r}') from second_error


def _response_text(data):
    text=data.get('output_text')
    if isinstance(text,str) and text.strip(): return text
    chunks=[]
    for item in data.get('output',[]):
        for c in item.get('content',[]):
            if c.get('type')=='output_text' and isinstance(c.get('text'),str): chunks.append(c['text'])
    return '\n'.join(chunks)


def _score(value):
    if isinstance(value,dict): return _score(value.get('value',0))
    if isinstance(value,(int,float)): return max(0,min(100,int(value)))
    if isinstance(value,str):
        m=re.search(r'-?\d+(?:[.,]\d+)?',value.replace('%',''))
        if m: return max(0,min(100,int(float(m.group(0).replace(',','.')))))
        if value.strip().lower() in {'неопределенная','неопределённая','unknown','uncertain','неизвестно'}: return 0
    return 0


def _compact_events(events, limit=12):
    selected=[]; seen=set()
    for e in reversed(events):
        eid=_eid(e)
        if eid in seen: continue
        selected.append({'event_id':eid,'url':str(e.get('url',''))[:400],'title':str(e.get('title',''))[:180],
                         'snippet':str(e.get('snippet',''))[:350],'region':str(e.get('region',''))[:80],'kind':str(e.get('kind',''))[:100]})
        seen.add(eid)
        if len(selected)>=limit: break
    return selected


def _validate(result, events):
    allowed={_eid(e):e for e in events}
    facts=result.get('facts',[]); inferences=result.get('inferences',[])
    if not isinstance(facts,list): facts=[]
    if not isinstance(inferences,list): inferences=[]

    def clean(items):
        out=[]
        for item in items:
            if not isinstance(item,dict): continue
            text=item.get('text'); ids=item.get('event_ids',[])
            if not isinstance(text,str) or not text.strip() or not isinstance(ids,list): continue
            ids=[x for x in ids if isinstance(x,str) and x in allowed]
            if ids: out.append({'text':text.strip()[:500],'event_ids':ids})
        return out

    facts=clean(facts); inferences=clean(inferences)
    used=list(dict.fromkeys(x for item in facts+inferences for x in item['event_ids']))
    if not facts and not inferences:
        return _fallback(events,'AI returned no evidence-linked facts or inferences; model result rejected by hallucination guard')

    domains={_domain(allowed[x].get('url','')) for x in used if x in allowed and _domain(allowed[x].get('url',''))}
    primary_domains={d for x in used if x in allowed and _is_primary(allowed[x].get('url','')) for d in [_domain(allowed[x].get('url',''))]}
    corroborated=len(domains)>=2
    primary=bool(primary_domains)

    p=_score(result.get('probability',0)); c=_score(result.get('confidence',0)); r=_score(result.get('risk',0))
    # Hard deterministic ceiling: no model output can override evidence quality.
    if not corroborated: p=min(p,60); c=min(c,50)
    elif not primary: p=min(p,85); c=min(c,70)
    else: p=min(p,95); c=min(c,90)
    if c>p: c=p

    result['probability']=p; result['confidence']=c; result['risk']=min(r,p)
    result['facts']=facts; result['inferences']=inferences; result['evidence_event_ids']=used
    result['missing_indicators']=result.get('missing_indicators',[]) if isinstance(result.get('missing_indicators',[]),list) else []
    result['hallucination_guard']='passed_evidence_gate'
    result['evidence_quality']='corroborated_primary' if corroborated and primary else ('corroborated' if corroborated else 'single_source_or_nonindependent')
    result['evidence_domains']=sorted(domains)
    return result


def analyze(events):
    if not SETTINGS.openai_api_key: return _fallback(events,'OPENAI_API_KEY is not configured; deterministic fallback used')
    compact=_compact_events(events)
    payload={'model':SETTINGS.openai_model,'instructions':SYSTEM,
             'input':('Return only valid JSON. '+json.dumps({'scenario':'мобилизационные или связанные с ФСИН действия после 20 сентября 2026 года','events':compact},ensure_ascii=False)),
             'text':{'format':{'type':'json_object'}},'max_output_tokens':700,'store':False}
    try:
        r=requests.post('https://api.openai.com/v1/responses',headers={'Authorization':f'Bearer {SETTINGS.openai_api_key}','Content-Type':'application/json'},json=payload,timeout=60)
        r.raise_for_status(); result=_extract_json(_response_text(r.json()))
        if not isinstance(result,dict): raise ValueError('model JSON is not an object')
        result.setdefault('decision','WATCH'); result.setdefault('reason','OpenAI analysis completed'); result.setdefault('signals',[]); result.setdefault('missing_indicators',[])
        return _validate(result,events)
    except requests.HTTPError as exc:
        status=getattr(exc.response,'status_code',None); body=''
        try: body=exc.response.text[:300]
        except Exception: pass
        return _fallback(events,f'OpenAI analysis failed: HTTPError status={status} body={body}; deterministic fallback used')
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        return _fallback(events,f'OpenAI analysis failed: {type(exc).__name__}: {str(exc).replace(chr(10)," ")[:300]}; deterministic fallback used')
