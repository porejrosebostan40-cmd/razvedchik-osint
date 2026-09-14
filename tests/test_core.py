from requests import RequestException
from razvedchik.collectors import search_github
from razvedchik.extract import identifiers
from razvedchik.models import Evidence, Investigation
from razvedchik.normalize import phone_variants
from razvedchik.report import to_dict


def test_identifier_extraction():
    found = identifiers("Contact @alpha_user or test@example.org, +7 999 123-45-67")
    assert "@alpha_user" in found
    assert "test@example.org" in found
    assert "79991234567" in found


def test_phone_variants():
    values = phone_variants("8 (999) 123-45-67")
    assert "+79991234567" in values
    assert "79991234567" in values


def test_candidate_needs_independent_sources():
    inv = Investigation(mode="fio", query="Test Person")
    ids = {"@alpha_user", "test@example.org"}
    for n in range(3):
        ev = Evidence("same-source", f"https://example{n}.org", f"Result {n}", "snippet", "query")
        eid = inv.add_evidence(ev)
        inv.add_candidate("candidate", "Result", ids, {eid}, {f"example{n}.org"}, {ev.source})
    assert inv.candidates["candidate"].status == "possible match"


def test_candidate_confirms_with_independent_sources():
    inv = Investigation(mode="fio", query="Test Person")
    ids = {"@alpha_user", "test@example.org"}
    for n, source in enumerate(("web", "github", "registry")):
        ev = Evidence(source, f"https://example{n}.org", f"Result {n}", "snippet", "query")
        eid = inv.add_evidence(ev)
        inv.add_candidate("candidate", "Result", ids, {eid}, {f"example{n}.org"}, {source})
    assert inv.candidates["candidate"].status == "confirmed by source"
    assert inv.candidates["candidate"].score > 0


def test_github_collector_handles_api_failure(monkeypatch):
    class Failed:
        def get(self, *args, **kwargs):
            raise RequestException("network")

    monkeypatch.setattr("razvedchik.collectors.requests", Failed())
    assert search_github("example") == []


def test_relation_graph_and_report_serialization():
    inv = Investigation(mode="combined", query="Test Person")
    ev = Evidence("web", "https://example.org", "Result", "@alpha_user test@example.org", "query")
    eid = inv.add_evidence(ev)
    inv.add_candidate("candidate", "Result", {"@alpha_user", "test@example.org"}, {eid}, {"example.org"}, {"web"})
    inv.add_relation("@alpha_user", "co-occurs in source", "test@example.org", eid)
    data = to_dict(inv)
    assert len(data["relations"]) == 1
    assert data["relations"][0]["evidence_ids"] == [eid]
