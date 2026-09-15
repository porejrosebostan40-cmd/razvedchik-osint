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

def test_accumulated_methodology_is_deterministic_and_not_sent_in_full_to_ai():
    from riskwatch.methodology import HEURISTICS, SOURCE_RULES, SEARCH_SEQUENCE, POSITIVE_INDICATORS, NEGATIVE_INDICATORS, METHODOLOGY_TEXT
    from riskwatch.ai import SYSTEM
    assert len(METHODOLOGY_TEXT)>500 and len(SOURCE_RULES)>=5 and len(SEARCH_SEQUENCE)>=8 and len(POSITIVE_INDICATORS)>=6 and len(NEGATIVE_INDICATORS)>=4
    assert any("Do not equate discussion" in rule for rule in HEURISTICS) and "root scenario" in SYSTEM.lower()
    assert len(SYSTEM) < len(METHODOLOGY_TEXT)

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
    events=[{"url":"https://example.org/a","title":"заключенные направлены на военную службу","kind":"source-a"},{"url":"https://example.org/b","title":"заключенные направлены на военную службу","kind":"source-b"}]; ids=[_eid(e) for e in events]; result={"probability":99,"confidence":99,"risk":99,"facts":[{"text":"fact","event_ids":ids}],"inferences":[],"scenario_answer":"YES"}; d=_validate(result,events); assert d["probability"]<=60

def test_ai_collapses_obvious_cross_domain_reposts():
    from riskwatch.ai import _validate, _eid
    title="заключенные направлены на военную службу"; events=[{"url":"https://example.com/a","title":title,"snippet":"отбор и военная служба"},{"url":"https://example.net/b","title":title,"snippet":"отбор и военная служба"}]; ids=[_eid(e) for e in events]; result={"probability":99,"confidence":99,"risk":99,"facts":[{"text":"fact","event_ids":ids}],"inferences":[],"scenario_answer":"YES"}; d=_validate(result,events); assert d["evidence_families"]==1 and d["probability"]<=60

def test_ai_caps_non_primary_corroboration():
    from riskwatch.ai import _validate, _eid
    events=[{"url":"https://example.org/a","title":"заключенные направлены на военную службу","kind":"source-a"},{"url":"https://example.net/b","title":"заключенные направлены на военную службу","kind":"source-b"}]; ids=[_eid(e) for e in events]; result={"probability":100,"confidence":100,"risk":100,"facts":[{"text":"fact","event_ids":ids}],"inferences":[],"scenario_answer":"YES"}; d=_validate(result,events); assert d["probability"]<=85

def test_ai_allows_high_but_not_absolute_primary_corroboration():
    from riskwatch.ai import _validate, _eid
    events=[{"url":"https://fsin.gov.ru/a","title":"заключенные направлены на военную службу","kind":"UFSIN"},{"url":"https://example.net/b","title":"заключенные направлены на военную службу","kind":"independent"}]; ids=[_eid(e) for e in events]; result={"probability":100,"confidence":100,"risk":100,"facts":[{"text":"fact","event_ids":ids}],"inferences":[],"scenario_answer":"YES"}; d=_validate(result,events); assert d["probability"]<=95 and d["probability"]<100

def test_ai_semantic_gate_requires_target_and_action():
    from riskwatch.ai import _validate, _eid
    events=[{"url":"https://fsin.gov.ru/a","title":"ФСИН сообщила о порядке работы","snippet":"новые правила"}]
    eid=_eid(events[0]); result={"probability":90,"confidence":90,"risk":90,"facts":[{"text":"unsupported claim","event_ids":[eid]}],"inferences":[],"scenario_answer":"YES"}
    d=_validate(result,events)
    assert d["analysis_provider"]=="fallback" and d["probability"]==0 and d["scenario_answer"]=="UNKNOWN"

def test_ai_semantic_gate_rejects_yes_without_root_signal():
    from riskwatch.ai import _validate, _eid
    events=[{"url":"https://fsin.gov.ru/a","title":"ФСИН подготовила списки заключенных","snippet":"отбор и учет"}]
    eid=_eid(events[0]); result={"probability":70,"confidence":60,"risk":70,"facts":[{"text":"preparation signal","event_ids":[eid]}],"inferences":[],"scenario_answer":"YES"}
    d=_validate(result,events)
    assert d["hallucination_guard"]=="passed_evidence_gate_v2" and d["scenario_answer"]=="UNKNOWN"

def test_ai_semantic_gate_rejects_no_without_negative_signal():
    from riskwatch.ai import _validate, _eid
    events=[{"url":"https://fsin.gov.ru/a","title":"ФСИН подготовила списки заключенных","snippet":"отбор и учет"}]
    eid=_eid(events[0]); result={"probability":10,"confidence":60,"risk":10,"facts":[{"text":"preparation signal","event_ids":[eid]}],"inferences":[],"scenario_answer":"NO"}
    d=_validate(result,events)
    assert d["hallucination_guard"]=="passed_evidence_gate_v2" and d["scenario_answer"]=="UNKNOWN"

def test_pattern_engine_recognizes_ordered_chain_and_next_step():
    from riskwatch.forecast import build_forecast
    events=[{"url":"https://government.ru/a","title":"Правительство изменило порядок","snippet":"новые правила"},{"url":"https://fsin.gov.ru/b","title":"Поручено подготовить списки заключенных","snippet":"проверка и учет"},{"url":"https://example.net/c","title":"Подготовлены места и транспорт","snippet":"снабжение и размещение"}]; f=build_forecast(events); assert f["pattern_stage"]==3 and f["next_stage"]=="operational_implementation" and f["structure_score"]>30

def test_root_stage_requires_target_specificity():
    from riskwatch.forecast import build_forecast
    f=build_forecast([{"url":"https://example.org/a","title":"призван на военную службу","snippet":""}]); assert f["pattern_stage"]<5

def test_evidence_score_is_not_probability():
    from riskwatch.forecast import evidence_score
    e=evidence_score([{"url":"https://fsin.gov.ru/a","title":"ФСИН подготовила списки заключенных для отбора на военную службу","snippet":""}]); assert 0<=e["score"]<=100

def test_source_family_independence_ignores_search_engines_and_subdomains():
    from riskwatch.forecast import evidence_score
    events=[{"url":"https://www.example.com/a","title":"заключенные привлечены к военной службе","snippet":""},{"url":"https://news.example.com/b","title":"заключенные привлечены к военной службе","snippet":""},{"url":"https://www.bing.com/search?q=x","title":"заключенные привлечены к военной службе","snippet":""}]
    e=evidence_score(events); assert e["source_families"]==1 and e["independent_domains"]==1

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

def test_evidence_graph_collapses_same_family_and_ignores_search_engine():
    from riskwatch.evidence import build_evidence_graph
    events=[
        {"url":"https://www.example.com/a","title":"заключенные привлечены к военной службе","snippet":"отбор"},
        {"url":"https://news.example.com/b","title":"заключенные привлечены к военной службе","snippet":"отбор"},
        {"url":"https://bing.com/search?q=x","title":"заключенные привлечены к военной службе","snippet":"отбор"},
    ]
    g=build_evidence_graph(events)
    assert g["metrics"]["source_families"]==1 and g["metrics"]["edges"]==0

def test_evidence_graph_requires_target_match():
    from riskwatch.evidence import build_evidence_graph
    events=[
        {"url":"https://example.com/a","title":"заключенные привлечены к военной службе","snippet":""},
        {"url":"https://other.net/b","title":"военнослужащие направлены на службу","snippet":""},
    ]
    g=build_evidence_graph(events)
    assert g["metrics"]["edges"]==0

def test_evidence_graph_requires_temporal_order_for_stage_chain():
    from riskwatch.evidence import build_evidence_graph
    events=[
        {"url":"https://government.ru/a","title":"ФСИН поручено подготовить списки заключенных","snippet":"учет","published_ts":200},
        {"url":"https://example.net/b","title":"заключенные направлены на военную службу","snippet":"военная служба","published_ts":100},
    ]
    g=build_evidence_graph(events)
    assert g["metrics"]["ordered_support_edges"]==0

def test_evidence_graph_strengthens_independent_primary_regional_chain():
    from riskwatch.evidence import build_evidence_graph
    events=[
        {"url":"https://fsin.gov.ru/a","title":"ФСИН подготовила списки заключенных для отбора на военную службу","snippet":"учет","published_ts":100,"region":""},
        {"url":"https://example.net/b","title":"заключенные направлены на военную службу","snippet":"военная служба","published_ts":200,"region":"Республика Северная Осетия — Алания"},
    ]
    g=build_evidence_graph(events)
    assert g["metrics"]["source_families"]==2 and g["metrics"]["ordered_support_edges"]>=1 and g["metrics"]["chain_score"]>30

def test_evidence_graph_penalizes_contradiction():
    from riskwatch.evidence import build_evidence_graph
    events=[
        {"url":"https://government.ru/a","title":"заключенные привлечены к военной службе","snippet":"отбор","published_ts":100},
        {"url":"https://example.net/b","title":"привлечение заключенных к военной службе не планируется","snippet":"","published_ts":200},
    ]
    g=build_evidence_graph(events)
    assert g["metrics"]["contradictions"]>=1 and g["metrics"]["chain_score"]<40

def test_site_scoped_search_rejects_wrong_domain_results():
    from riskwatch.search import _matches_site, _site_targets
    q='site:fsin.gov.ru "заключенные" "военная служба"'
    targets=_site_targets(q)
    assert targets==('fsin.gov.ru',)
    assert _matches_site('https://fsin.gov.ru/news/1',targets)
    assert _matches_site('https://vologda.fsin.gov.ru/news/1',targets)
    assert not _matches_site('https://www.bing.com/search?q=x',targets)
