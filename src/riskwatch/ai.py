import hashlib, json, re, requests
from pathlib import Path
from urllib.parse import urlsplit
from .config import SETTINGS
from .forecast import _source_family, TARGET_TERMS, ACTION_TERMS
from .semantics import safe_root_event, has_target, is_negative

SCENARIO_ID='prisoner_mobilization'
SCENARIO_QUESTION='Будут ли мужчин из мест лишения свободы, прежде всего из исправительных колоний, мобилизовывать/привлекать к военной службе после 20 сентября 2026 года?'
SYSTEM='''Ты аналитическое ядро RiskWatch. Не являйся источником фактов: работай только с переданными events и deterministic evidence_chain.\nГлавный вопрос неизменен: будут ли мужчин из мест лишения свободы, прежде всего из исправительных колоний, мобилизовывать/привлекать к военной службе после 20 сентября 2026 года?\nRules include the root scenario requirement: 7) Для YES нужен target-specific root signal либо согласованная цепочка, ведущая к root scenario. 8) Для NO нужна явная отрицательная evidence; отсутствие новости само по себе не является доказательством NO. 9) Верни только JSON.\n'''
PRIMARY_DOMAINS=('kremlin.ru','government.ru','mil.ru','fsin.gov.ru','minjust.gov.ru','duma.gov.ru','council.gov.ru','publication.pravo.gov.ru','zakupki.gov.ru','gov.ru','epp.genproc.gov.ru')
NEGATIVE_TERMS=('опроверг','не подтверд','отменен','отменён','отказ','не планируется','ложн','фейк','исключен','исключён')

def _eid(e): return hashlib.sha256((str(e.get('url',''))+'|'+str(e.get('title',''))).encode()).hexdigest()[:16]
def _domain(url):
    try:return urlsplit(str(url)).netloc.lower().split(':')[0].removeprefix('www.')
    except ValueError:return ''
def _is_primary(url):
    d=_domain(url); return any(d==x or d.endswith('.'+x) for x in PRIMARY_DOMAINS)
def _fallback(events,reason,forecast=None,usage=None):
    forecast=forecast or {}
    result={'scenario_id':SCENARIO_ID,'scenario_question':SCENARIO_QUESTION,'probability':0,'confidence':0,'risk':0,'decision':'WATCH','reason':reason,'facts':[],'inferences':[],'evidence_event_ids':[],'signals':[f"pattern_stage={forecast.get('pattern_stage',0)}",f"structure_score={forecast.get('structure_score',0)}"],'missing_indicators':['прямое решение о мобилизации/привлечении мужчин из ИК','независимые де-факто подтверждения подготовительных действий','наблюдаемый следующий этап цепочки'],'next_event':'UNKNOWN','horizon':'UNKNOWN','forecast_basis':'insufficient evidence','scenario_answer':'UNKNOWN','pattern':forecast,'hallucination_guard':'fallback_no_claim_without_evidence','analysis_provider':'fallback'}
    if usage is not None: result['usage']=usage
    return result
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
def _event_text(e): return (str(e.get('title',''))+' '+str(e.get('snippet',''))).lower()
def _has_target(e): return has_target(e)
def _has_action(e):
    text=_event_text(e); return any(t in text for t in ACTION_TERMS)
def _has_negative(e): return is_negative(e)
def _has_root(e): return safe_root_event(e)
def _content_origin(e):
    if _is_primary(e.get('url','')): return 'primary:' + _source_family(e)
    title=re.sub(r'\W+',' ',str(e.get('title','')).lower()).strip(); snippet=re.sub(r'\W+',' ',str(e.get('snippet','')).lower()).strip()
    if not title:return 'publisher:' + _source_family(e)
    return 'content:' + hashlib.sha256((title+'|'+snippet).encode()).hexdigest()[:20]
def _compact_events(events,limit=6):
    unique={_eid(e):e for e in (events or [])}; selected=[]; seen=set()
    def add(e):
        eid=_eid(e)
        if eid in seen:return
        selected.append({'event_id':eid,'url':str(e.get('url',''))[:220],'title':str(e.get('title',''))[:120],'snippet':str(e.get('snippet',''))[:120],'region':str(e.get('region',''))[:40],'kind':str(e.get('kind',''))[:30]}); seen.add(eid)
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
    if not any(_has_target(e) and _has_action(e) for e in linked):return None
    return {'text':claim['text'].strip()[:600],'event_ids':ids}
def _validate(result,events,forecast=None):
    forecast=forecast or {}; allowed={_eid(e):e for e in events}; facts=[]; inf=[]
    for x in result.get('facts',[]) if isinstance(result.get('facts'),list) else []:
        y=_validate_claim(x,allowed)
        if y:facts.append(y)
    for x in result.get('inferences',[]) if isinstance(result.get('inferences'),list) else []:
        y=_validate_claim(x,allowed)
        if y:inf.append(y)
    used=list(dict.fromkeys(i for x in facts+inf for i in x['event_ids']))
    if not facts and not inf:return _fallback(events,'AI claims failed semantic evidence gate; rejected',forecast)
    domains={_domain(allowed[i].get('url','')) for i in used if _domain(allowed[i].get('url',''))}; families={_source_family(allowed[i]) for i in used if _source_family(allowed[i])}; origins={_content_origin(allowed[i]) for i in used}; effective_families={f for f in families if f}
    if len(origins)==1 and len(effective_families)>1: effective_families={'content_origin:' + next(iter(origins))}
    primary=any(_is_primary(allowed[i].get('url','')) for i in used); corroborated=len(domains)>=2 and len(effective_families)>=2 and len(origins)>=2
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
    result.update({'scenario_id':SCENARIO_ID,'scenario_question':SCENARIO_QUESTION,'scenario_answer':answer,'probability':p,'confidence':c,'risk':min(r,p),'facts':facts,'inferences':inf,'evidence_event_ids':used,'missing_indicators':result.get('missing_indicators',[]) if isinstance(result.get('missing_indicators',[]),list) else [],'next_event':str(result.get('next_event','UNKNOWN'))[:500] or 'UNKNOWN','horizon':str(result.get('horizon','UNKNOWN'))[:100] or 'UNKNOWN','forecast_basis':str(result.get('forecast_basis',''))[:900],'pattern':forecast,'hallucination_guard':'passed_evidence_gate_v2','evidence_quality':'corroborated_primary' if corroborated and primary else ('corroborated' if corroborated else 'single_source_or_nonindependent'),'evidence_domains':sorted(domains),'evidence_families':len(effective_families),'evidence_origins':len(origins)}); return result
def _save_ai_debug(response_data):
    try:
        raw=json.dumps(response_data,ensure_ascii=False,separators=(',',':'))
        raw=raw[:180000]
        Path('/tmp/riskwatch_ai_debug.json').write_text(raw,encoding='utf-8')
    except Exception:
        pass
def analyze(events,forecast,evidence_graph=None):
    forecast=dict(forecast or {})
    try:
        from .evidence import compact_chain
        forecast['evidence_chain']=compact_chain(evidence_graph or {})
    except Exception as e:
        forecast['evidence_chain']={'version':2,'metrics':{},'support_edges':[],'contradiction_edges':[],'fingerprint':'','error':type(e).__name__}
    if not SETTINGS.openai_api_key:return _fallback(events,'OPENAI_API_KEY is not configured',forecast)
    compact=_compact_events(events); context={'scenario_id':SCENARIO_ID,'scenario_question':SCENARIO_QUESTION,'pattern':{k:v for k,v in forecast.items() if k!='_events'},'evidence_chain':forecast.get('evidence_chain',{}),'events':compact}
    payload={'model':SETTINGS.openai_model,'instructions':SYSTEM,'input':'Return only JSON. Analyze only the evidence below. '+json.dumps(context,ensure_ascii=False,separators=(',',':')),'text':{'format':{'type':'json_object'}},'max_output_tokens':500,'store':False}
    try:
        r=requests.post('https://api.openai.com/v1/responses',headers={'Authorization':f'Bearer {SETTINGS.openai_api_key}','Content-Type':'application/json'},json=payload,timeout=60); r.raise_for_status(); response=r.json(); usage=response.get('usage',{}) or {}; result=_extract_json(_response_text(response))
        if not isinstance(result,dict):raise ValueError('model JSON is not object')
        result.setdefault('decision','WATCH'); result.setdefault('reason','OpenAI analysis completed'); validated=_validate(result,events,forecast); validated['usage']=usage
        if validated.get('reason')=='AI claims failed semantic evidence gate; rejected': _save_ai_debug(response)
        return validated
    except requests.HTTPError as e:
        body=''
        try:body=e.response.text[:300]
        except Exception:pass
        return _fallback(events,f'OpenAI HTTP failure: {getattr(e.response,"status_code",None)} {body}',forecast)
    except (requests.RequestException,ValueError,TypeError,KeyError) as e:return _fallback(events,f'OpenAI analysis failed: {type(e).__name__}: {str(e).replace(chr(10)," ")[:300]}',forecast)
