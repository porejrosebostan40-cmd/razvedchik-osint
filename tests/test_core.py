from razvedchik.collectors import search_github
from razvedchik.extract import identifiers
from razvedchik.models import Evidence, Investigation
from razvedchik.normalize import phone_variants


def test_identifier_extraction():
    found = identifiers("Contact @alpha_user or test@example.org, +7 999 123-45-67")
    assert "@alpha_user" in found
    assert "test@example.org" in found
    assert "79991234567" in found


def test_phone_variants():
    values = phone_variants("8 (999) 123-45-67")
    assert "+79991234567" in values
    assert "79991234567" in values


def test_candidate_confidence_progression():
    inv = Investigation(mode="fio", query="Test Person")
    ids = {"@alpha_user", "test@example.org"}
    for n in range(3):
        ev = Evidence("source", f"https://example{n}.org", f"Result {n}", "snippet", "query")
        eid = inv.add_evidence(ev)
        inv.add_candidate("candidate", "Result", ids, {eid}, {f"example{n}.org"})
    assert inv.candidates["candidate"].status == "confirmed by source"
    assert inv.candidates["candidate"].score > 0


def test_github_collector_handles_api_failure(monkeypatch):
    class Failed:
        def get(self, *args, **kwargs):
            raise RuntimeError("network")

    monkeypatch.setattr("razvedchik.collectors.requests", Failed())
    assert search_github("example") == []
