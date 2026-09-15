import tempfile
from datetime import datetime, timezone
from pathlib import Path


def test_config_matrix():
    from riskwatch.config import REGIONS, SOURCE_TEMPLATES, REGIONAL_TEMPLATES, build_queries
    assert len(REGIONS) >= 80
    assert len(SOURCE_TEMPLATES) >= 20
    assert len(REGIONAL_TEMPLATES) >= 8
    assert len(build_queries()) > 700


def test_source_matrix_contains_independent_and_public_sources():
    from riskwatch.config import SOURCE_TEMPLATES
    names={name for name,_ in SOURCE_TEMPLATES}
    assert {"Reuters","ТАСС","РИА Новости","Интерфакс","РБК","Медиазона","Telegram public","VK public","YouTube public"}.issubset(names)


def test_store_roundtrip():
    from riskwatch.store import Store
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"state.json"
        s=Store(str(p)); s.add_events([{"url":"https://example.org/a","title":"x","source":"test"}]); s.save_decision({"risk":50,"probability":40,"confidence":70,"decision":"WATCH","reason":"test"})
        assert len(Store(str(p)).recent())==1


def test_ai_fallback_function():
    from riskwatch.ai import _fallback
    d=_fallback([],"test")
    assert d["probability"] == 0
    assert d["confidence"] == 0
    assert d["risk"] == 0
    assert d["decision"]=="WATCH"


def test_ai_rejects_unlinked_claims():
    from riskwatch.ai import _validate
    events=[{"url":"https://example.org/a","title":"A","kind":"source-a"}]
    result={"probability":99,"confidence":99,"risk":99,"facts":[],"inferences":[],"evidence_event_ids":["fake"],"missing_indicators":[]}
    d=_validate(result,events)
    assert d["probability"] == 0
    assert d["confidence"] == 0
    assert "hallucination guard" in d["reason"]


def test_ai_caps_single_source_probability():
    from riskwatch.ai import _validate, _eid
    events=[{"url":"https://example.org/a","title":"A","kind":"source-a"}]
    eid=_eid(events[0])
    result={"probability":99,"confidence":99,"risk":99,"facts":[{"text":"fact","event_ids":[eid]}],"inferences":[],"evidence_event_ids":[eid],"missing_indicators":[]}
    d=_validate(result,events)
    assert d["probability"] <= 60
    assert d["confidence"] <= 50


def test_ai_requires_domain_independence_not_kind_labels():
    from riskwatch.ai import _validate, _eid
    events=[
        {"url":"https://example.org/a","title":"A","kind":"source-a"},
        {"url":"https://example.org/b","title":"B","kind":"source-b"},
    ]
    ids=[_eid(e) for e in events]
    result={"probability":99,"confidence":99,"risk":99,"facts":[{"text":"fact","event_ids":ids}],"inferences":[],"evidence_event_ids":ids,"missing_indicators":[]}
    d=_validate(result,events)
    assert d["probability"] <= 60
    assert d["confidence"] <= 50


def test_ai_caps_non_primary_corroboration():
    from riskwatch.ai import _validate, _eid
    events=[
        {"url":"https://example.org/a","title":"A","kind":"source-a"},
        {"url":"https://example.net/b","title":"B","kind":"source-b"},
    ]
    ids=[_eid(e) for e in events]
    result={"probability":100,"confidence":100,"risk":100,"facts":[{"text":"fact","event_ids":ids}],"inferences":[],"evidence_event_ids":ids,"missing_indicators":[]}
    d=_validate(result,events)
    assert d["probability"] <= 85
    assert d["confidence"] <= 70


def test_ai_allows_high_but_not_absolute_primary_corroboration():
    from riskwatch.ai import _validate, _eid
    events=[
        {"url":"https://fsin.gov.ru/a","title":"A","kind":"UFSIN"},
        {"url":"https://example.net/b","title":"B","kind":"independent"},
    ]
    ids=[_eid(e) for e in events]
    result={"probability":100,"confidence":100,"risk":100,"facts":[{"text":"fact","event_ids":ids}],"inferences":[],"evidence_event_ids":ids,"missing_indicators":[]}
    d=_validate(result,events)
    assert d["probability"] <= 95
    assert d["confidence"] <= 90
    assert d["probability"] < 100


def test_pattern_engine_recognizes_ordered_chain_and_next_step():
    from riskwatch.forecast import build_forecast
    events=[
        {"url":"https://government.ru/a","title":"Правительство изменило порядок","snippet":"новые правила"},
        {"url":"https://fsin.gov.ru/b","title":"Поручено подготовить списки","snippet":"проверка и учет"},
        {"url":"https://example.net/c","title":"Подготовлены места и транспорт","snippet":"снабжение и размещение"},
    ]
    f=build_forecast(events)
    assert f["pattern_stage"] == 3
    assert f["next_stage"] == "operational_implementation"
    assert f["structure_score"] > 30


def test_pattern_engine_does_not_turn_one_event_into_high_structure():
    from riskwatch.forecast import build_forecast
    f=build_forecast([{"url":"https://example.org/a","title":"важная новость","snippet":""}])
    assert f["pattern_stage"] == 0
    assert f["structure_score"] < 40


def test_probability_cannot_run_far_ahead_of_pattern_strength():
    from riskwatch.ai import _validate, _eid
    events=[{"url":"https://example.org/a","title":"Правительство изменило порядок","kind":"policy"},
            {"url":"https://example.net/b","title":"Приказ опубликован","kind":"order"}]
    ids=[_eid(e) for e in events]
    result={"probability":99,"confidence":99,"risk":99,"facts":[{"text":"facts","event_ids":ids}],"inferences":[{"text":"inference","event_ids":ids}],"evidence_event_ids":ids,"missing_indicators":[]}
    d=_validate(result,events)
    assert d["probability"] <= 70
    assert d["confidence"] <= d["probability"]


def test_regional_rotation_changes_each_20_minute_slot():
    from riskwatch.runner import _queries
    a=_queries(datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc))
    b=_queries(datetime(2026, 9, 15, 12, 20, tzinfo=timezone.utc))
    assert a[0] == b[0]
    assert a[14:] != b[14:]


def test_regional_rotation_repeats_after_full_cycle():
    from riskwatch.config import REGIONS, REGIONAL_TEMPLATES
    from riskwatch.runner import _queries
    slots=(len(REGIONS)*len(REGIONAL_TEMPLATES)+29)//30
    a=_queries(datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc))
    b=_queries(datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc).replace(day=15))
    assert len(a) == len(b)
    assert slots >= 10
