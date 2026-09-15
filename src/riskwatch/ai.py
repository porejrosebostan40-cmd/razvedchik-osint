import hashlib, json, re, requests
from urllib.parse import urlsplit
from .config import SETTINGS
from .forecast import build_forecast, _source_family, TARGET_TERMS, ACTION_TERMS

SCENARIO_ID='prisoner_mobilization'
SCENARIO_QUESTION='Будут ли мужчин из мест лишения свободы, прежде всего из исправительных колоний, мобилизовывать/привлекать к военной службе после 20 сентября 2026 года?'

# The long methodology remains deterministic in methodology.py/forecast.py.
# Only the minimum analytical protocol is sent to the model to keep TPM bounded.
SYSTEM='''Ты аналитическое ядро RiskWatch. Не являйся источником фактов: работай только с переданными events и deterministic evidence_chain.
Главный вопрос неизменен: будут ли мужчин из мест лишения свободы, прежде всего из исправительных колоний, мобилизовывать/привлекать к военной службе после 20 сентября 2026 года?
Правила: 1) FACT и INFERENCE должны ссылаться только на event_id из входа. 2) Не считай поисковик источником. 3) Не считай перепечатки независимым подтверждением. 4) Не создавай отсутствующие события, связи или документы. 5) Разделяй основной сценарий и следующий наблюдаемый этап. 6) Если доказательств недостаточно — scenario_answer=UNKNOWN. 7) Для YES нужен target-specific root signal либо согласованная цепочка, ведущая к root. 8) Для NO нужна явная отрицательная evidence; отсутствие новости само по себе не является доказательством NO. 9) Верни только JSON.
'''
PRIMARY_DOMAINS=('kremlin.ru','government.ru','mil.ru','fsin.gov.ru','minjust.gov.ru','duma.gov.ru','council.gov.ru','publication.pravo.gov.ru','zakupki.gov.ru','gov.ru','epp.genproc.gov.ru')
NEGATIVE_TERMS=('опроверг','не подтверд','отменен','отменён','отказ','не планируется','ложн','фейк','исключен','исключён')

def _eid(e): return hashlib.sha256((str(e.get('url',''))+'|'+str(e.get('title',''))).encode()).hexdigest()[:16]
def _domain(url):
    try:return urlsplit(str(url)).netloc.lower().split(':')[0].removeprefix('www.')
    except ValueError:return ''
def _is_primary(url):
    d=_domain(url); return any(d==x or d.endswith('.'+x) for x in PRIMARY_DOMAINS)

def _fallback(events,reason,forecast=None):
    forecast=forecast or build_forecast(events)
    return {'scenario_id':SCENARIO_ID,'scenario_question':SCENARIO_QUESTION,'probability':0,'confidence':0,'risk':0,'decision':'WATCH','reason':reason,'facts':[],'inferences':[],'evidence_event_ids':[],'signals':[f"pattern_stage={forecast.get('pattern_stage',0)}",f"structure_score={forecast.get('structure_score',0)}"],'missing_indicators':['прямое решение о мобилизации/привлечении мужчин из ИК','независимые де-факто подтверждения подготовительных действий','наблюдаемый следующий этап цепочки'],'next_event':'UNKNOWN','horizon':'UNKNOWN','forecast_basis':'insufficient evidence','scenario_answer':'UNKNOWN','pattern':forecast,'hallucination_guard':'fallback_no_claim_without_evidence','analysis_provider':'fallback'}

def _extract_json(text):
    if not isinstance(text,str):raise ValueError('empty model output')
    text=text.strip(); text=re.sub(r'^```(?:json)?\s*|\s*```$','',text,flags=re.I|re.S).strip()
    try:return json.loads(text)
    except json.JSONDecodeError:
        a,b=text.find('{'),text.rfind('}')
        if a<0 or b<=a:raise ValueError('model output has no JSON object')
        return json.loads(text[a:b+1])

def _response_text(data):
    if isinstance(data.get('output_text'),str) and data['output_text'].strip():return data['output_text']
    chunks=[]
    for item in data.get('output',[]):
        for c in item.get('content',[]):
            if c.get('type')=='output_text' and isinstance(c.get('text'),str):chunks.append(c['text'])
    return '\n'.join(chunks)

def _score(v):
    if isinstance(v,dict):return _score(v.get('value',0))
    if isinstance(v,(int,float)):return max(0,min(100,int(v)))
    if isinstance(v,str):
        m=re.search(r'-?\d+(?:[.,]\d+)?',v)
        if m:return max(0,min(100,int(float(m.group(0).replace(',','.')))))
    return 0

def _timestamp(e):
    v=e.get('published_ts') or e.get('ts') or e.get('date') or e.get('published')
    try:return float(v)
    except (TypeError,ValueError):return 0

def _event_text(e):
    return (str(e.get('title',''))+' '+str(e.get('snippet',''))).lower()

def _has_target(e):
    text=_event_text(e); return any(t in text for t in TARGET_TERMS)
def _has_action(e):
    text=_event_text(e); return any(t in text for t in ACTION_TERMS)
def _has_negative(e):
    text=_event_text(e); return any(t in text for t in NEGATIVE_TERMS)
def _has_root(e):
    text=_event_text(e)
    direct=('привлечен','привлечён','зачислен','зачислён','направлен','отправлен','отправл','призван','заключил контракт','заключен контракт','заключён контракт','начал службу')
    return _has_target(e) and any(t in text for t in direct)

def _compact_events(events,limit=10):
    unique={_eid(e):e for e in (events or [])}
    selected=[]; seen=set()
    def add(e):
        eid=_eid(e)
        if eid in seen:return
        selected.append({'event_id':eid,'url':str(e.get('url',''))[:220],'title':str(e.get('title',''))[:120],'snippet':str(e.get('snippet',''))[:180],'region':str(e.get('region',''))[:40],'kind':str(e.get('kind',''))[:30]})
        seen.add(eid)
    # Preserve decisive evidence even when it is older than the newest search results.
    for e in sorted(unique.values(),key=lambda e: (_has_root(e), _has_target(e) and _has_action(e), _is_primary(e.get('url','')), _timestamp(e)),reverse=True):
        if _has_root(e): add(e)
        if len(selected)>=limit: break
    if len(selected)<limit:
        for e in sorted(unique.values(),key=_timestamp,reverse=True):
            if _has_target(e) or _has_action(e): add(e)
            if len(selected)>=limit: break
    if len(selected)<limit:
        for e in sorted(unique.values(),key=_timestamp,reverse=True):
            add(e)
            if len(selected)>=limit: break
    return selected

def _validate_claim(claim,allowed):
    if not isinstance(claim,dict) or not isinstance(claim.get('text'),str) or not isinstance(claim.get('event_ids'),list):return None
    ids=[i for i in claim['event_ids'] if isinstance(i,str) and i in allowed]
    if not ids:return None
    linked=[allowed[i] for i in ids]
    # A claim must be anchored by at least one concrete event containing both
    # the target population and an action relevant to military involvement.
    if not any(_has_target(e) and _has_action(e) for e in linked):return None
    return {'text':claim['text'].strip()[:600],'event_ids':ids}

def _validate(result,events,forecast=None):
    forecast=forecast or build_forecast(events); allowed={_eid(e):e for e in events}
    facts=[]; inf=[]
    for x in result.get('facts',[]) if isinstance(result.get('facts'),list) else []:
        y=_validate_claim(x,allowed)
        if y:facts.append(y)
    for x in result.get('inferences',[]) if isinstance(result.get('inferences'),list) else []:
        y=_validate_claim(x,allowed)
        if y:inf.append(y)
    used=list(dict.fromkeys(i for x in facts+inf for i in x['event_ids']))
    if not facts and not inf:return _fallback(events,'AI claims failed semantic evidence gate; rejected',forecast)
    domains={_domain(allowed[i].get('url','')) for i in used if _domain(allowed[i].get('url',''))}
    families={_source_family(allowed[i]) for i in used if _source_family(allowed[i])}
    primary=any(_is_primary(allowed[i].get('url','')) for i in used)
    corroborated=len(domains)>=2 and len(families)>=2
    p,c,r=_score(result.get('probability')),_score(result.get('confidence')),_score(result.get('risk'))
    if not corroborated:p,c=min(p,60),min(c,50)
    elif not primary:p,c=min(p,85),min(c,70)
    else:p,c=min(p,95),min(c,90)
    structure=int(forecast.get('structure_score',0)); stage=int(forecast.get('pattern_stage',0))
    if stage<2 and structure<40:p,c=min(p,60),min(c,50)
    if structure<70:p=min(p,max(55,structure+15))
    answer=str(result.get('scenario_answer','UNKNOWN')).upper()
    if answer not in ('YES','NO','UNKNOWN'):answer='UNKNOWN'
    linked_events=[allowed[i] for i in used]
    if answer=='YES' and not any(_has_root(e) for e in linked_events):answer='UNKNOWN'
    if answer=='NO' and not any(_has_negative(e) for e in linked_events):answer='UNKNOWN'
    if c>p:c=p
    result.update({'scenario_id':SCENARIO_ID,'scenario_question':SCENARIO_QUESTION,'scenario_answer':answer,'probability':p,'confidence':c,'risk':min(r,p),'facts':facts,'inferences':inf,'evidence_event_ids':used,'missing_indicators':result.get('missing_indicators',[]) if isinstance(result.get('missing_indicators',[]),list) else [],'next_event':str(result.get('next_event','UNKNOWN'))[:500] or 'UNKNOWN','horizon':str(result.get('horizon','UNKNOWN'))[:100] or 'UNKNOWN','forecast_basis':str(result.get('forecast_basis',''))[:900],'pattern':forecast,'hallucination_guard':'passed_evidence_gate_v2','evidence_quality':'corroborated_primary' if corroborated and primary else ('corroborated' if corroborated else 'single_source_or_nonindependent'),'evidence_domains':sorted(domains),'evidence_families':len(families)})
    return result

def analyze(events):
    forecast=build_forecast(events)
    try:
        from .evidence import build_evidence_graph, compact_chain
        forecast['evidence_chain']=compact_chain(build_evidence_graph(events))
    except Exception as e:
        forecast['evidence_chain']={'version':1,'metrics':{},'support_edges':[],'contradiction_edges':[],'fingerprint':'','error':type(e).__name__}
    if not SETTINGS.openai_api_key:return _fallback(events,'OPENAI_API_KEY is not configured',forecast)
    compact=_compact_events(events)
    context={'scenario_id':SCENARIO_ID,'scenario_question':SCENARIO_QUESTION,'pattern':{k:v for k,v in forecast.items() if k!='_events'},'evidence_chain':forecast.get('evidence_chain',{}),'events':compact}
    payload={'model':SETTINGS.openai_model,'instructions':SYSTEM,'input':'Return only JSON. Analyze only the evidence below. '+json.dumps(context,ensure_ascii=False,separators=(',',':')),'text':{'format':{'type':'json_object'}},'max_output_tokens':900,'store':False}
    try:
        r=requests.post('https://api.openai.com/v1/responses',headers={'Authorization':f'Bearer {SETTINGS.openai_api_key}','Content-Type':'application/json'},json=payload,timeout=60); r.raise_for_status(); result=_extract_json(_response_text(r.json()))
        if not isinstance(result,dict):raise ValueError('model JSON is not object')
        result.setdefault('decision','WATCH'); result.setdefault('reason','OpenAI analysis completed')
        return _validate(result,events,forecast)
    except requests.HTTPError as e:
        body=''
        try:body=e.response.text[:300]
        except Exception:pass
        return _fallback(events,f'OpenAI HTTP failure: {getattr(e.response,"status_code",None)} {body}',forecast)
    except (requests.RequestException,ValueError,TypeError,KeyError) as e:return _fallback(events,f'OpenAI analysis failed: {type(e).__name__}: {str(e).replace(chr(10)," ")[:300]}',forecast)
