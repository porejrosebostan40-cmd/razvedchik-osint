import hashlib, json, re, requests
from urllib.parse import urlsplit
from .config import SETTINGS
from .forecast import build_forecast, render_context
from .methodology import METHODOLOGY_TEXT, HEURISTICS, SOURCE_RULES, SEARCH_SEQUENCE, POSITIVE_INDICATORS, NEGATIVE_INDICATORS, OUTPUT_RULES

SCENARIO_ID='prisoner_mobilization'
SCENARIO_QUESTION='Будут ли мужчин из мест лишения свободы, прежде всего из исправительных колоний, мобилизовывать/привлекать к военной службе после 20 сентября 2026 года?'

SYSTEM='''Ты аналитическое ядро системы раннего предупреждения. Главный и неизменный объект прогнозирования — SCENARIO: будут ли мужчин из мест лишения свободы, прежде всего из исправительных колоний, мобилизовывать/привлекать к военной службе после 20 сентября 2026 года.

Главный вопрос всегда один: БУДУТ ИЛИ НЕ БУДУТ. Не подменяй его вопросом о том, появился ли конкретный документ, сколько СМИ написали об этом или насколько громко обсуждается тема.

Твоя задача — восстановить причинно-следственную цепочку действий государства. Ищи не только прямое подтверждение конечного решения. Установи: что уже произошло; какие промежуточные стадии сформировались; какой следующий шаг логически необходим или наиболее вероятен; ведёт ли последовательность к мобилизации/привлечению мужчин из исправительных колоний либо, наоборот, от неё удаляется.

События могут быть разного типа: документы, решения, поручения, кадровые/организационные действия, логистика, изменения правил, фактические действия на местах. Один документ + два независимых де-факто события могут быть сильнее десятка публикаций.

Разделяй FACT, INFERENCE и UNKNOWN. Каждый FACT/INFERENCE обязан ссылаться на event_ids. Не считай число публикаций доказательством. Перепечатки, синдикацию и сообщения из одного первоисточника объединяй в одну evidence family.

Обязательно анализируй обе стороны гипотезы: признаки движения К СЦЕНАРИЮ и признаки движения ОТ СЦЕНАРИЯ. Отсутствие ожидаемого следующего шага является отрицательным доказательством только тогда, когда этот шаг должен был быть наблюдаемым в рассматриваемом горизонте.

Различай два прогноза: (1) вероятность основного сценария и (2) вероятность следующего наблюдаемого шага. Это разные величины и их нельзя смешивать.

Используй накопленную методику ниже как обязательный протокол, а не как справочную подсказку. Не выдумывай дополнительные правила, источники или факты. Если доказательств недостаточно — UNKNOWN.

''' + METHODOLOGY_TEXT + '''

Верни только JSON: probability, confidence, risk, decision, reason, facts, inferences, evidence_event_ids, missing_indicators, next_event, horizon, forecast_basis, scenario_answer.
'''
PRIMARY_DOMAINS=('kremlin.ru','government.ru','mil.ru','fsin.gov.ru','minjust.gov.ru','duma.gov.ru','council.gov.ru','publication.pravo.gov.ru','zakupki.gov.ru','gov.ru','epp.genproc.gov.ru')

def _eid(e): return hashlib.sha256((str(e.get('url',''))+'|'+str(e.get('title',''))).encode()).hexdigest()[:16]
def _domain(url):
    try: return urlsplit(str(url)).netloc.lower().split(':')[0].removeprefix('www.')
    except ValueError: return ''
def _is_primary(url):
    d=_domain(url); return any(d==x or d.endswith('.'+x) for x in PRIMARY_DOMAINS)
def _family(e):
    text=(str(e.get('title',''))+' '+str(e.get('snippet',''))).lower(); text=re.sub(r'[^\w\sа-яё]',' ',text,flags=re.I)
    return ' '.join(w for w in text.split() if len(w)>2)[:300]

def _fallback(events,reason,forecast=None):
    forecast=forecast or build_forecast(events)
    return {'probability':0,'confidence':0,'risk':0,'decision':'WATCH','reason':reason,'facts':[],'inferences':[],'evidence_event_ids':[],'signals':[f"pattern_stage={forecast.get('pattern_stage',0)}",f"structure_score={forecast.get('structure_score',0)}"],'missing_indicators':['прямое решение о мобилизации/привлечении мужчин из ИК','независимые де-факто подтверждения подготовительных действий','наблюдаемый следующий этап цепочки'],'next_event':'UNKNOWN','horizon':'UNKNOWN','forecast_basis':'insufficient evidence','scenario_answer':'UNKNOWN','pattern':forecast,'hallucination_guard':'fallback_no_claim_without_evidence','analysis_provider':'fallback'}

def _extract_json(text):
    if not isinstance(text,str): raise ValueError('empty model output')
    text=text.strip(); text=re.sub(r'^```(?:json)?\s*|\s*```$','',text,flags=re.I|re.S).strip()
    try:return json.loads(text)
    except json.JSONDecodeError:
        a,b=text.find('{'),text.rfind('}');
        if a<0 or b<=a: raise ValueError('model output has no JSON object')
        return json.loads(text[a:b+1])

def _response_text(data):
    if isinstance(data.get('output_text'),str) and data['output_text'].strip(): return data['output_text']
    chunks=[]
    for item in data.get('output',[]):
        for c in item.get('content',[]):
            if c.get('type')=='output_text' and isinstance(c.get('text'),str): chunks.append(c['text'])
    return '\n'.join(chunks)

def _score(v):
    if isinstance(v,dict): return _score(v.get('value',0))
    if isinstance(v,(int,float)): return max(0,min(100,int(v)))
    if isinstance(v,str):
        m=re.search(r'-?\d+(?:[.,]\d+)?',v)
        if m:return max(0,min(100,int(float(m.group(0).replace(',','.')))))
    return 0

def _compact_events(events,limit=24):
    out=[]; seen=set()
    for e in reversed(events):
        eid=_eid(e)
        if eid in seen:continue
        out.append({'event_id':eid,'url':str(e.get('url',''))[:400],'title':str(e.get('title',''))[:180],'snippet':str(e.get('snippet',''))[:400],'region':str(e.get('region',''))[:80],'kind':str(e.get('kind',''))[:100]}); seen.add(eid)
        if len(out)>=limit:break
    return out

def _validate(result,events,forecast=None):
    forecast=forecast or build_forecast(events); allowed={_eid(e):e for e in events}
    def clean(items):
        out=[]
        for x in items if isinstance(items,list) else []:
            if not isinstance(x,dict) or not isinstance(x.get('text'),str) or not isinstance(x.get('event_ids'),list):continue
            ids=[i for i in x['event_ids'] if isinstance(i,str) and i in allowed]
            if ids:out.append({'text':x['text'].strip()[:600],'event_ids':ids})
        return out
    facts=clean(result.get('facts')); inf=clean(result.get('inferences')); used=list(dict.fromkeys(i for x in facts+inf for i in x['event_ids']))
    if not facts and not inf:return _fallback(events,'AI returned no evidence-linked facts/inferences; rejected',forecast)
    domains={_domain(allowed[i].get('url','')) for i in used if _domain(allowed[i].get('url',''))}; families={_family(allowed[i]) for i in used if _family(allowed[i])}; primary=any(_is_primary(allowed[i].get('url','')) for i in used)
    corroborated=len(domains)>=2 and len(families)>=2
    p,c,r=_score(result.get('probability')), _score(result.get('confidence')), _score(result.get('risk'))
    if not corroborated:p,c=min(p,60),min(c,50)
    elif not primary:p,c=min(p,85),min(c,70)
    else:p,c=min(p,95),min(c,90)
    structure=int(forecast.get('structure_score',0)); stage=int(forecast.get('pattern_stage',0))
    if stage<2 and structure<40:p,c=min(p,60),min(c,50)
    if structure<70:p=min(p,max(55,structure+15))
    if c>p:c=p
    answer=str(result.get('scenario_answer','UNKNOWN')).upper()
    if answer not in ('YES','NO','UNKNOWN'):answer='UNKNOWN'
    result.update({'scenario_id':SCENARIO_ID,'scenario_question':SCENARIO_QUESTION,'scenario_answer':answer,'probability':p,'confidence':c,'risk':min(r,p),'facts':facts,'inferences':inf,'evidence_event_ids':used,'missing_indicators':result.get('missing_indicators',[]) if isinstance(result.get('missing_indicators',[]),list) else [],'next_event':str(result.get('next_event','UNKNOWN'))[:500] or 'UNKNOWN','horizon':str(result.get('horizon','UNKNOWN'))[:100] or 'UNKNOWN','forecast_basis':str(result.get('forecast_basis',''))[:900],'pattern':forecast,'hallucination_guard':'passed_evidence_gate','evidence_quality':'corroborated_primary' if corroborated and primary else ('corroborated' if corroborated else 'single_source_or_nonindependent'),'evidence_domains':sorted(domains),'evidence_families':len(families)})
    return result

def analyze(events):
    forecast=build_forecast(events)
    if not SETTINGS.openai_api_key:return _fallback(events,'OPENAI_API_KEY is not configured',forecast)
    payload={'model':SETTINGS.openai_model,'instructions':SYSTEM,'input':('Return only JSON. '+render_context(forecast)+'\n'+json.dumps({'scenario_id':SCENARIO_ID,'scenario_question':SCENARIO_QUESTION,'methodology_rules':{'source_rules':SOURCE_RULES,'search_sequence':SEARCH_SEQUENCE,'positive_indicators':POSITIVE_INDICATORS,'negative_indicators':NEGATIVE_INDICATORS,'heuristics':HEURISTICS,'output_rules':OUTPUT_RULES},'events':_compact_events(events)},ensure_ascii=False)),'text':{'format':{'type':'json_object'}},'max_output_tokens':1400,'store':False}
    try:
        r=requests.post('https://api.openai.com/v1/responses',headers={'Authorization':f'Bearer {SETTINGS.openai_api_key}','Content-Type':'application/json'},json=payload,timeout=60); r.raise_for_status(); result=_extract_json(_response_text(r.json()))
        if not isinstance(result,dict):raise ValueError('model JSON is not object')
        result.setdefault('decision','WATCH'); result.setdefault('reason','OpenAI analysis completed')
        return _validate(result,events,forecast)
    except requests.HTTPError as e:
        body='';
        try:body=e.response.text[:300]
        except Exception:pass
        return _fallback(events,f'OpenAI HTTP failure: {getattr(e.response,"status_code",None)} {body}',forecast)
    except (requests.RequestException,ValueError,TypeError,KeyError) as e:return _fallback(events,f'OpenAI analysis failed: {type(e).__name__}: {str(e).replace(chr(10)," ")[:300]}',forecast)
