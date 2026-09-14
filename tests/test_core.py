from requests import RequestException
from razvedchik.collectors import search_github
from razvedchik.entities import EntityGraph, page_entities, classify_identifier
from razvedchik.extract import identifiers
from razvedchik.models import Evidence, Investigation
from razvedchik.normalize import phone_variants
from razvedchik.report import configured_collectors, to_dict


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
    assert data["coverage"]["queries_searched"] == 0
    assert data["coverage"]["candidates_total"] == 1
    assert data["coverage"]["configured_collectors"][-1] == "Sherlock public username search"


def test_configured_collectors_are_mode_aware():
    assert configured_collectors(Investigation(mode="fio", query="x")) == ["web search", "GitHub public search"]
    assert "Sherlock public username search" in configured_collectors(Investigation(mode="username", query="x"))


def test_entity_classification():
    assert classify_identifier("@alpha_user") == "username"
    assert classify_identifier("test@example.org") == "email"
    assert classify_identifier("79991234567") == "phone"


def test_entity_graph_keeps_sources_as_evidence_backed_edges():
    graph, edges = page_entities(
        "Public profile",
        "@alpha_user test@example.org 79991234567",
        "https://example.org/profile",
        {"@alpha_user", "test@example.org", "79991234567"},
        "evidence-1",
    )
    assert "username:@alpha_user" in graph.entities
    assert "email:test@example.org" in graph.entities
    assert "phone:79991234567" in graph.entities
    assert any(edge[0] == "username:@alpha_user" and edge[1] == "found_on" for edge in edges)


def test_entity_graph_merge_preserves_evidence():
    first = EntityGraph()
    second = EntityGraph()
    first.add("username", "@alpha_user", "evidence-1")
    second.add("username", "@alpha_user", "evidence-2")
    second.add("email", "test@example.org", "evidence-2")
    first.merge(second)
    assert first.entities["username:@alpha_user"].evidence_ids == {"evidence-1", "evidence-2"}
    assert "email:test@example.org" in first.entities


def test_entity_graph_does_not_create_identity_claim():
    graph, edges = page_entities(
        "Same name only",
        "John Example",
        "https://example.org/profile",
        set(),
        "evidence-2",
    )
    assert graph.entities
    assert not any(edge[1] == "same_as" for edge in edges)
