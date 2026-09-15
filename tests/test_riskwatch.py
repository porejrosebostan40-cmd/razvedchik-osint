import tempfile
from datetime import datetime, timezone
from pathlib import Path

def test_config_matrix():
    from riskwatch.config import REGIONS, SOURCE_TEMPLATES, REGIONAL_TEMPLATES, build_queries
    assert len(REGIONS)>=80 and len(SOURCE_TEMPLATES)>=20 and len(REGIONAL_TEMPLATES)>=8 and len(build_queries())>700

def test_source_matrix_contains_independent_and_public_sources():
    from riskwatch.config import SOURCE_TEMPLATES
    names={name for name,_ in SOURCE_TEMPLATES}
    assert {"Reuters","ТАСС","РИА Новости","Интерфакс","РБК","Медиазона","Telegram public","VK public","YouTube public"}.issubset(names)

def test_accumulated_methodology_is_loaded_by_ai():
    from riskwatch.ai import SYSTEM, METHODOLOGY_TEXT
    from riskwatch.methodology import HEURISTICS, SOURCE_RULES, SEARCH_SEQUENCE, POSITIVE_INDICATORS, NEGATIVE_INDICATORS
    assert METHODOLOGY_TEXT in SYSTEM and len(SOURCE_RULES)>=5 and len(SEARCH_SEQUENCE)>=8 and len(POSITIVE_INDICATORS)>=6 and len(NEGATIVE_INDICATORS)>=4
    assert any("Do not equate discussion" in rule for rule in HEURISTICS) and "root scenario" in SYSTEM.lower()

def test_methodology_has_target_specific_final_stage():
    from riskwatch.methodology import STAGES
    assert STAGES[-1][0]==5 and STAGES[-1][1]=="root_scenario" and "correctional institutions" in STAGES[-1][2]

def test_store_roundtrip():
    from riskwatch.store import Store
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"state.json"; s=Store(str(p)); s.add_events([{"url":"https://example.org/a","title":"x","source":"test"}]); s.save_decision({"risk":50,"probability":40,"confidence":70,"decision":"WATCH","reason":"test"}); assert len(Store(str(p)).recent())==1

def test_root_scenario_is_prison_mobilization():
    from riskwatch.ai import SCENARIO_ID, SCENARIO_QUESTION, _fallback
    assert SCENARIO_ID=="prisoner_mobilization" and "исправительных колоний" in SCENARIO_QUESTION and "мобилизовывать" in SCENARIO_QUESTION
    d=_fallback([],"test"); assert d["scenario_id"]==SCENARIO_ID and d["scenario_answer"]=="UNKNOWN" and d["probability"]==0

def test_ai_fallback_function():
    from riskwatch.ai import _fallback
    d=_fallback([],"test"); assert d["probability"]==0 and d["confidence"]==0 and d["risk"]==0 and d["decision"]=="WATCH"

def test_ai_rejects_unlinked_claims():
    from riskwatch.ai import _validate, _eid
    events=[{"url":"https://example.org/a","title":"A","kind":"source-a"}]; result={"probability":99,"confidence":99,"risk":99,"facts":[],"inferences":[],"evidence_event_ids":["fake"],"scenario_answer":"YES"}; d=_validate(result,events); assert d["probability"]==0 and d["scenario_answer"]=="UNKNOWN"

def test_ai_requires_domain_independence_not_kind_labels():
    from riskwatch.ai import _validate, _eid
    events=[{"url":"https://example.org/a","title":"A","kind":"source-a"},{"url":"https://example.org/b","title":"B","kind":"source-b"}]; ids=[_eid(e) for e in events]; result={"probability":99,"confidence":99,"risk":99,"facts":[{"text":"fact","event_ids":ids}],"inferences":[],"scenario_answer":"YES"}; d=_validate(result,events); assert d["probability"]<=60

def test_ai_collapses_obvious_cross_domain_reposts():
    from riskwatch.ai import _validate, _eid
    title="Государство изменило порядок исполнения решения"; events=[{"url":"https://example.org/a","title":title,"snippet":"новый порядок"},{"url":"https://example.net/b","title":title,"snippet":"новый порядок"}]; ids=[_eid(e) for e in events]; result={"probability":99,"confidence":99,"risk":99,"facts":[{"text":"fact","event_ids":ids}],"inferences":[],"scenario_answer":"YES"}; d=_validate(result,events); assert d["evidence_families"]==1 and d["probability"]<=60

def test_ai_caps_non_primary_corroboration():
    from riskwatch.ai import _validate, _eid
    events=[{"url":"https://example.org/a","title":"A","kind":"source-a"},{"url":"https://example.net/b","title":"B","kind":"source-b"}]; ids=[_eid(e) for e in events]; result={"probability":100,"confidence":100,"risk":100,"facts":[{"text":"fact","event_ids":ids}],"inferences":[],"scenario_answer":"YES"}; d=_validate(result,events); assert d["probability"]<=85

def test_ai_allows_high_but_not_absolute_primary_corroboration():
    from riskwatch.ai import _validate, _eid
    events=[{"url":"https://fsin.gov.ru/a","title":"A","kind":"UFSIN"},{"url":"https://example.net/b","title":"B","kind":"independent"}]; ids=[_eid(e) for e in events]; result={"probability":100,"confidence":100,"risk":100,"facts":[{"text":"fact","event_ids":ids}],"inferences":[],"scenario_answer":"YES"}; d=_validate(result,events); assert d["probability"]<=95 and d["probability"]<100

def test_pattern_engine_recognizes_ordered_chain_and_next_step():
    from riskwatch.forecast import build_forecast
    events=[{"url":"https://government.ru/a","title":"Правительство изменило порядок","snippet":"новые правила"},{"url":"https://fsin.gov.ru/b","title":"Поручено подготовить списки","snippet":"проверка и учет"},{"url":"https://example.net/c","title":"Подготовлены места и транспорт","snippet":"снабжение и размещение"}]; f=build_forecast(events); assert f["pattern_stage"]==3 and f["next_stage"]=="operational_implementation" and f["structure_score"]>30

def test_root_stage_requires_target_specificity():
    from riskwatch.forecast import build_forecast
    f=build_forecast([{"url":"https://example.org/a","title":"призван на военную службу","snippet":""}]); assert f["pattern_stage"]<5

def test_evidence_score_is_not_probability():
    from riskwatch.forecast import evidence_score
    e=evidence_score([{"url":"https://fsin.gov.ru/a","title":"ФСИН подготовила списки заключенных для отбора на военную службу","snippet":""}]); assert 0<=e["score"]<=100

def test_root_forecast_resolves_only_on_root_event():
    from riskwatch.forecast import build_forecast, forecast_record, resolve_forecasts
    f=build_forecast([{"url":"https://government.ru/a","title":"изменен порядок"}]); r=forecast_record(f,73,now=1000,evidence_ids=["x"]); unrelated={"url":"https://example.org/x","title":"призван на военную службу","published_ts":999}; done=resolve_forecasts([r],[unrelated],now=r["deadline_ts"]+1)[0]; assert done["resolved"] and done["outcome"]==0

def test_root_forecast_ignores_root_event_before_forecast_creation():
    from riskwatch.forecast import build_forecast, forecast_record, resolve_forecasts
    f=build_forecast([{"url":"https://government.ru/a","title":"изменен порядок"}]); r=forecast_record(f,73,now=1000,evidence_ids=["x"]); prior={"url":"https://fsin.gov.ru/x","title":"заключенный привлечен к военной службе и направлен","published_ts":900}; done=resolve_forecasts([r],[prior],now=r["deadline_ts"]+1)[0]; assert done["outcome"]==0

def test_walk_forward_calibration_needs_history_and_uses_prior_bins():
    from riskwatch.forecast import calibration_summary, calibrate_probability
    records=[{"resolved":True,"scenario_id":"prisoner_mobilization","probability":50,"outcome":i%2,"brier":0.25} for i in range(29)]
    assert calibration_summary(records)["calibration_status"]=="insufficient_history"
    records.append({"resolved":True,"scenario_id":"prisoner_mobilization","probability":50,"outcome":1,"brier":0.25}); c=calibrate_probability(50,records); assert c["status"]=="preliminary" and 0<c["probability"]<100 and c["bin_sample"]==30

def test_calibration_summary_is_not_measured_too_early():
    from riskwatch.forecast import calibration_summary
    records=[{"resolved":True,"scenario_id":"prisoner_mobilization","probability":50,"outcome":i%2,"brier":0.25} for i in range(99)]; assert calibration_summary(records)["calibration_status"]=="preliminary"; records.append({"resolved":True,"scenario_id":"prisoner_mobilization","probability":50,"outcome":1,"brier":0.25}); assert calibration_summary(records)["calibration_status"]=="measured"

def test_issued_probability_is_evaluated_separately():
    from riskwatch.forecast import calibration_summary
    records=[{"resolved":True,"scenario_id":"prisoner_mobilization","raw_probability":80,"issued_probability":50,"outcome":1,"brier":0.04,"issued_brier":0.25} for _ in range(30)]
    s=calibration_summary(records); assert s["brier"]==0.04 and s["issued_brier"]==0.25 and s["calibration_status"]=="preliminary"

def test_regional_rotation_changes_each_20_minute_slot():
    from riskwatch.runner import _queries
    a=_queries(datetime(2026,9,15,12,0,tzinfo=timezone.utc)); b=_queries(datetime(2026,9,15,12,20,tzinfo=timezone.utc)); assert a[0]==b[0] and a[14:]!=b[14:]

def test_regional_rotation_repeats_after_full_cycle():
    from riskwatch.config import REGIONS, REGIONAL_TEMPLATES
    from riskwatch.runner import _queries
    a=_queries(datetime(2026,9,15,12,0,tzinfo=timezone.utc)); b=_queries(datetime(2026,9,15,12,0,tzinfo=timezone.utc).replace(day=15)); assert len(a)==len(b) and len(REGIONS)*len(REGIONAL_TEMPLATES)>=300
