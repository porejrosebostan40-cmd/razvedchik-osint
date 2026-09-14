from razvedchik.planner import _response_text, ai_queries, deterministic_queries


def test_response_text_supports_responses_api_shapes():
    assert _response_text({"output_text": "{\"queries\": [\"one\"]}"}) == '{"queries": ["one"]}'
    assert _response_text({"output": [{"content": [{"text": "{\"queries\": [\"two\"]}"}]}]}) == '{"queries": ["two"]}'


def test_deterministic_planner_expands_known_identifiers():
    queries = deterministic_queries("username", "alpha", ["@alpha", "alpha@example.org"])
    assert '"@alpha"' in queries
    assert '"alpha@example.org"' in queries
    assert len(queries) <= 12


def test_ai_planner_accepts_valid_json(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"output_text": '{"queries": ["alpha profile", "alpha github"]}'}

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("razvedchik.planner.requests.post", lambda *a, **k: Response())
    assert ai_queries("username", "alpha", []) == ["alpha profile", "alpha github"]


def test_ai_planner_fails_closed_on_invalid_json(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"output_text": "not json"}

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("razvedchik.planner.requests.post", lambda *a, **k: Response())
    assert ai_queries("username", "alpha", []) == []
