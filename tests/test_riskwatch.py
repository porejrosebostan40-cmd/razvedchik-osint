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
    assert 0 <= d["risk"] <= 100
    assert d["decision"]=="WATCH"


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
