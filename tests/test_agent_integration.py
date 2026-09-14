import pytest

from razvedchik.agent import Agent
from razvedchik.models import Evidence


def test_agent_records_entities_and_pivots(monkeypatch):
    agent = Agent("username", "alpha", max_waves=1, per_query=2)

    monkeypatch.setattr(
        "razvedchik.agent.search_web",
        lambda query, limit=2: [
            Evidence(
                source="web",
                url="https://example.org/profile",
                title="Alpha profile",
                snippet="Public page for @alpha with alpha@example.org",
                query=query,
            )
        ],
    )
    monkeypatch.setattr("razvedchik.agent.search_github", lambda *a, **k: [])
    monkeypatch.setattr("razvedchik.agent.search_gitlab", lambda *a, **k: [])
    monkeypatch.setattr("razvedchik.agent.search_sherlock", lambda *a, **k: [])
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
