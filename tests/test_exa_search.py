import requests

from riskwatch.exa_search import search
from riskwatch.search_result import SearchResult


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_normalizes_exa_results(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")

    def fake_post(*args, **kwargs):
        assert args[0] == "https://api.exa.ai/search"
        assert kwargs["headers"]["x-api-key"] == "test-key"
        assert kwargs["json"]["query"] == "test query"
        assert kwargs["timeout"] == 15
        return FakeResponse(payload={"results": [{"url": "https://example.com/article","title": "Article","highlights": ["First highlight.","Second highlight."],"publishedDate": "2026-01-01T00:00:00Z","author": "Author"}]})

    monkeypatch.setattr("riskwatch.exa_search.requests.post", fake_post)
    result = search("test query", limit=10)
    assert isinstance(result, SearchResult)
    assert len(result) == 1
    assert result[0]["source"] == "Exa"
    assert result[0]["url"] == "https://example.com/article"
    assert result[0]["title"] == "Article"
    assert result[0]["snippet"] == "First highlight. Second highlight."
    assert result[0]["publishedDate"] == "2026-01-01T00:00:00Z"
    assert result[0]["author"] == "Author"
    assert result[0]["query"] == "test query"
    assert result.telemetry["exa_raw"] == 1
    assert result.telemetry["after_url_filter"] == 1
    assert result.telemetry["after_dedup"] == 1


def test_deduplicates_and_limits(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setattr("riskwatch.exa_search.requests.post", lambda *args, **kwargs: FakeResponse(payload={"results":[{"url":"https://example.com/a","title":"A"},{"url":"https://example.com/a","title":"A duplicate"},{"url":"https://example.com/b","title":"B"}]}))
    result = search("q", limit=1)
    assert len(result) == 1
    assert result[0]["url"] == "https://example.com/a"
    assert result.telemetry["exa_raw"] == 3
    assert result.telemetry["after_dedup"] == 1


def test_missing_key_never_raises(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    result = search("q")
    assert result == []
    assert result.telemetry["reason"] == "missing_api_key"


def test_exa_429_never_raises(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setattr("riskwatch.exa_search.requests.post", lambda *args, **kwargs: FakeResponse(status_code=429))
    result = search("q")
    assert result == []
    assert result.telemetry["reason"] == "http_429"


def test_exa_timeout_never_raises(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    def fake_post(*args, **kwargs):
        raise requests.Timeout("timed out")
    monkeypatch.setattr("riskwatch.exa_search.requests.post", fake_post)
    result = search("q")
    assert result == []
    assert result.telemetry["reason"] == "timeout"


def test_exa_401_never_raises(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setattr("riskwatch.exa_search.requests.post", lambda *args, **kwargs: FakeResponse(status_code=401))
    result = search("q")
    assert result == []
    assert result.telemetry["reason"] == "http_401"


def test_exa_500_never_raises(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setattr("riskwatch.exa_search.requests.post", lambda *args, **kwargs: FakeResponse(status_code=500))
    result = search("q")
    assert result == []
    assert result.telemetry["reason"] == "http_500"


def test_exa_invalid_json_never_raises(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    class InvalidJsonResponse(FakeResponse):
        def json(self):
            raise ValueError("invalid json")
    monkeypatch.setattr("riskwatch.exa_search.requests.post", lambda *args, **kwargs: InvalidJsonResponse())
    result = search("q")
    assert result == []
    assert result.telemetry["reason"] == "invalid_response"


def test_exa_missing_author_never_raises(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    monkeypatch.setattr("riskwatch.exa_search.requests.post", lambda *args, **kwargs: FakeResponse(payload={"results":[{"url":"https://example.com/article","title":"Article","highlights":["Highlight."]}]}))
    result = search("q")
    assert len(result) == 1
    assert result[0].get("author") is None
