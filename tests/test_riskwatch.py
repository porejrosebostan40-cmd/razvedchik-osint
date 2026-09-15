import tempfile
from pathlib import Path

def test_config_matrix():
    from riskwatch.config import REGIONS, build_queries
    assert len(REGIONS) >= 80
    assert len(build_queries()) > 400

def test_store_roundtrip():
    from riskwatch.store import Store
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"state.json"
        s=Store(str(p)); s.add_events([{"url":"https://example.org/a","title":"x","source":"test"}]); s.save_decision({"risk":50,"probability":40,"confidence":70,"decision":"WATCH","reason":"test"})
        assert len(Store(str(p)).recent())==1

def test_ai_fallback_without_key(monkeypatch):
    import riskwatch.ai as ai
    monkeypatch.setattr(ai.SETTINGS,"openai_api_key","")
    d=ai.analyze([])
    assert d["decision"]=="NO_AI_KEY"
