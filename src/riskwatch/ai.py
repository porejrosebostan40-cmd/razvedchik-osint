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
    raw_verdict=result.get('verdict', result.get('scenario_answer')) if isinstance(result,dict) else None
    if not isinstance(raw_verdict,str): return _fallback(events,'AI response missing verdict; rejected',forecast)
    verdict=raw_verdict.strip().lower()
    if verdict in ('undetermined','unknown','indeterminate'):
        raw_facts=result.get('facts',[]); raw_inf=result.get('inferences',[])
        if (isinstance(raw_facts,list) and raw_facts) or (isinstance(raw_inf,list) and raw_inf):
            return _fallback(events,'AI undetermined response contained claims; rejected',forecast)
        result.update({'scenario_id':SCENARIO_ID,'scenario_question':SCENARIO_QUESTION,'scenario_answer':'UNKNOWN','probability':None,'confidence':0,'risk':None,'facts':[],'inferences':[],'evidence_event_ids':[],'missing_indicators':result.get('missing_indicators',[]) if isinstance(result.get('missing_indicators',[]),list) else [],'next_event':str(result.get('next_event','UNKNOWN'))[:500] or 'UNKNOWN','horizon':str(result.get('horizon','UNKNOWN'))[:100] or 'UNKNOWN','forecast_basis':str(result.get('forecast_basis',''))[:900],'pattern':forecast,'hallucination_guard':'passed_evidence_gate_valid_unknown','evidence_quality':'none_required_valid_unknown','evidence_domains':[],'evidence_families':0,'evidence_origins':0,'analysis_provider':'openai'})
        return result
    if verdict not in ('yes','no'):
        return _fallback(events,f'AI response has invalid verdict: {raw_verdict!r}',forecast)
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
    answer='YES' if verdict=='yes' else 'NO'
    linked_events=[allowed[i] for i in used]
    if answer=='YES' and not any(_has_root(e) for e in linked_events):answer='UNKNOWN'
    if answer=='NO' and not any(_has_negative(e) for e in linked_events):answer='UNKNOWN'
    if c>p:c=p
    result.update({'scenario_id':SCENARIO_ID,'scenario_question':SCENARIO_QUESTION,'scenario_answer':answer,'probability':p,'confidence':c,'risk':min(r,p),'facts':facts,'inferences':inf,'evidence_event_ids':used,'missing_indicators':result.get('missing_indicators',[]) if isinstance(result.get('missing_indicators',[]),list) else [],'next_event':str(result.get('next_event','UNKNOWN'))[:500] or 'UNKNOWN','horizon':str(result.get('horizon','UNKNOWN'))[:100] or 'UNKNOWN','forecast_basis':str(result.get('forecast_basis',''))[:900],'pattern':forecast,'hallucination_guard':'passed_evidence_gate_v2','evidence_quality':'corroborated_primary' if corroborated and primary else ('corroborated' if corroborated else 'single_source_or_nonindependent'),'evidence_domains':sorted(domains),'evidence_families':len(effective_families),'evidence_origins':len(origins),'analysis_provider':'openai'}); return result
def _save_ai_debug(response_data,validated=None):
    try:
        payload={'response':response_data,'validation':validated}
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
        raw=raw[:180000]
        Path('/tmp/riskwatch_ai_debug.json').write_text(raw,encoding='utf-8')
    except Exception as e:
        print(f"DEBUG: _save_ai_debug failed: {e!r}")
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
        result.setdefault('decision','WATCH'); result.setdefault('reason','OpenAI analysis completed')
        print(f"DEBUG: AI raw verdict={result.get('verdict')!r}")
        validated=_validate(result,events,forecast); validated['usage']=usage
        if validated.get('reason'):
            print(f"DEBUG: calling _save_ai_debug, reason={validated.get('reason')!r}")
            _save_ai_debug(response,validated)
            print(f"DEBUG: after _save_ai_debug, file exists={Path('/tmp/riskwatch_ai_debug.json').exists()}")
        return validated
    except requests.HTTPError as e:
        body=''
        try:body=e.response.text[:300]
        except Exception:pass
        return _fallback(events,f'OpenAI HTTP failure: {getattr(e.response,"status_code",None)} {body}',forecast)
    except (requests.RequestException,ValueError,TypeError,KeyError) as e:return _fallback(events,f'OpenAI analysis failed: {type(e).__name__}: {str(e).replace(chr(10)," ")[:300]}',forecast)

# === AI ORCHESTRATION: plan_queries + filter_events ===
# Добавить в конец ai.py, после функции analyze()

PLANNER_SYSTEM = """Ты планировщик поисковых запросов для OSINT-мониторинга.
Твоя задача: для заданного региона РФ и сценария prisoner_mobilization
сгенерировать 4-6 коротких поисковых запросов, которые Bing реально обработает.

Правила:
1. Каждый запрос — 2-5 слов, максимум 40 символов.
2. НЕ используй OR, AND, кавычки, скобки — Bing их игнорирует на длинных запросах.
3. НЕ используй site: — мы фильтруем URL отдельно.
4. Используй: регион + термин из сценария (ФСИН, осужденные, колония, мобилизация, военная служба, УФСИН).
5. Один запрос — одна тема. Не пытайся охватить всё сразу.
6. Если регион — город федерального значения (Москва, СПб), используй название города.
7. Если регион — республика/край/область, используй короткое название (без "республика", "край", "область").

Ответ — строго JSON: {"queries": ["запрос1", "запрос2", ...]}"""

FILTER_SYSTEM = """Ты фильтр результатов поиска для сценария prisoner_mobilization.
Твоя задача: из списка результатов поиска (title + snippet + url) выбрать релевантные
сценарию "будут ли мужчин из мест лишения свободы мобилизовывать/привлекать к военной службе".

Критерии релевантности (достаточно ОДНОГО):
1. Упоминаются осужденные/заключенные/колонии/ИК/ФСИН/УФСИН/СИЗО
2. Упоминается мобилизация/военная служба/контракт/призыв + регион РФ
3. Упоминается конкретное исправительное учреждение в регионе
4. Официальный документ о военной службе для осужденных

НЕ релевантно:
- Спорт, культура, происшествия без связи с военной службой
- Общие новости региона без упоминания ИК/осужденных
- Зарубежные новости
- Дубликаты одной новости

Ответ — строго JSON: {"relevant": [true/false для каждого результата], "reasons": ["краткая причина для каждого"]}"""


def _call_openai(system: str, user: str, max_tokens: int = 500) -> dict:
    """Унифицированный вызов OpenAI Responses API."""
    if not SETTINGS.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    payload = {
        "model": SETTINGS.openai_model,
        "instructions": system,
        "input": user,
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": max_tokens,
        "store": False,
    }
    r = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {SETTINGS.openai_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    response = r.json()
    return _extract_json(_response_text(response))


def plan_queries(region: str, scenario: str = "prisoner_mobilization") -> list:
    """AI-планировщик: генерирует 4-6 коротких запросов для региона."""
    user = f"Регион: {region}\nСценарий: {scenario}\nСгенерируй 4-6 коротких поисковых запросов."
    try:
        result = _call_openai(PLANNER_SYSTEM, user, max_tokens=200)
        queries = result.get("queries", [])
        valid = [q.strip() for q in queries if isinstance(q, str) and 3 <= len(q.strip()) <= 60]
        return valid[:6]
    except Exception:
        return _fallback_queries(region)


def _fallback_queries(region: str) -> list:
    """Детерминированный fallback, если AI недоступен."""
    short = region
    for suffix in ("Республика ", "республика ", " край", " область", " автономный округ", " АО"):
        short = short.replace(suffix, "")
    short = short.strip()
    return [
        f"ФСИН {short}",
        f"осужденные {short} мобилизация",
        f"колония {short} военная служба",
        f"{short} УФСИН новости",
    ]


def filter_events(events: list, scenario: str = "prisoner_mobilization") -> list:
    """AI-фильтр: отбирает релевантные события из сырой выдачи."""
    import sys

    print(
        f"DEBUG filter_events: input={len(events or [])}",
        file=sys.stderr,
        flush=True,
    )
    if not events:
        print("DEBUG filter_events: empty input -> []", file=sys.stderr, flush=True)
        return []

    seen_urls = set()
    unique = []
    for e in events:
        url = e.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(e)

    print(
        f"DEBUG filter_events: unique={len(unique)}",
        file=sys.stderr,
        flush=True,
    )

    BATCH = 20
    filtered = []
    debug_batches = []
    for i in range(0, len(unique), BATCH):
        batch = unique[i:i + BATCH]
        items = []
        for j, e in enumerate(batch):
            items.append({
                "i": j,
                "title": str(e.get("title", ""))[:150],
                "snippet": str(e.get("snippet", ""))[:200],
                "url": str(e.get("url", ""))[:100],
            })
        user = f"Сценарий: {scenario}\nРезультаты поиска:\n{json.dumps(items, ensure_ascii=False)}\n\nОпредели релевантность каждого результата."
        try:
            result = _call_openai(FILTER_SYSTEM, user, max_tokens=400)
            relevant = result.get("relevant", [])
            reasons = result.get("reasons", [])
            passed = 0
            for j, e in enumerate(batch):
                if j < len(relevant) and relevant[j]:
                    e["ai_relevance_reason"] = reasons[j] if j < len(reasons) else ""
                    filtered.append(e)
                    passed += 1
            preview = json.dumps(result, ensure_ascii=False)[:400]
            print(
                f"DEBUG filter_events: batch={i // BATCH + 1} size={len(batch)} "
                f"result_preview={preview!r} relevant_type={type(relevant).__name__} "
                f"relevant_len={len(relevant) if isinstance(relevant, list) else 'NA'} "
                f"passed={passed}",
                file=sys.stderr,
                flush=True,
            )
            debug_batches.append({
                "batch": i // BATCH + 1,
                "size": len(batch),
                "result_preview": preview,
                "relevant_type": type(relevant).__name__,
                "relevant_len": len(relevant) if isinstance(relevant, list) else None,
                "passed": passed,
            })
        except Exception as e:
            fallback_passed = 0
            for e in batch:
                if has_target(e):
                    filtered.append(e)
                    fallback_passed += 1
            print(
                f"DEBUG filter_events: batch={i // BATCH + 1} size={len(batch)} "
                f"EXCEPTION={type(e).__name__}: {str(e).replace(chr(10), ' ')[:400]} "
                f"fallback_passed={fallback_passed}",
                file=sys.stderr,
                flush=True,
            )
            debug_batches.append({
                "batch": i // BATCH + 1,
                "size": len(batch),
                "exception": f"{type(e).__name__}: {str(e).replace(chr(10), ' ')[:400]}",
                "fallback_passed": fallback_passed,
            })

    try:
        Path("/tmp/riskwatch_filter_debug.json").write_text(
            json.dumps({
                "input": len(events),
                "unique": len(unique),
                "batches": debug_batches,
                "filtered": len(filtered),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(
            f"DEBUG filter_events: debug_file_exception={type(e).__name__}: {e}",
            file=sys.stderr,
            flush=True,
        )

    print(
        f"DEBUG filter_events: total_filtered={len(filtered)}",
        file=sys.stderr,
        flush=True,
    )
    return filtered
