import pytest

from razvedchik.agent import Agent
from razvedchik.models import Evidence
from razvedchik.sources import SourceSpec


def test_agent_records_entities_and_pivots(monkeypatch):
    agent = Agent("username", "alpha", max_waves=1, per_query=2)

    def fake_web(query, limit=2):
        return [Evidence("web", "https://example.org/profile", "Alpha profile", "Public page for @alpha with alpha@example.org", query)]

    specs = [SourceSpec("web search", fake_web, frozenset({"username"}))]
    monkeypatch.setattr("razvedchik.agent.source_specs_for_mode", lambda mode: specs)
    monkeypatch.setattr("razvedchik.agent.ai_queries", lambda *a, **k: [])
    monkeypatch.setattr("razvedchik.agent.deterministic_queries", lambda *a, **k: [])

    result = agent.run()
    assert "username:@alpha" in result.entity_graph.entities
    assert "email:alpha@example.org" in result.entity_graph.entities
    assert '"@alpha"' in result.queue
    assert result.stop_reason == "maximum waves reached"


def test_agent_rejects_unsafe_runtime_limits():
    with pytest.raises(ValueError):
        Agent("username", "alpha", max_waves=0)
    with pytest.raises(ValueError):
        Agent("username", "alpha", per_query=21)
    with pytest.raises(ValueError):
        Agent("username", "   ")
    with pytest.raises(ValueError):
        Agent("photo", "image.jpg")
