from requests import RequestException
from razvedchik.collectors import search_github, search_gitlab, search_openalex, search_stackexchange, search_wikidata
from razvedchik.entities import EntityGraph, page_entities, classify_identifier
from razvedchik.extract import identifiers
from razvedchik.models import Evidence, Investigation
from razvedchik.normalize import expand_queries, phone_variants
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


def test_fio_expansion_keeps_birth_year_as_context():
    queries = expand_queries("fio", "Иванов Иван Иванович 1981")
    assert '"Иванов Иван Иванович" 1981' in queries
    assert "1" not in queries
    assert "И И И" in queries


def test_fio_expansion_supports_full_birth_date():
    queries = expand_queries("fio", "Иванов Иван Иванович 18.12.1981")
    assert '"Иванов Иван Иванович" 18.12.1981' in queries
    assert "1" not in queries


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


def test_gitlab_collector_parses_public_user(monkeypatch):
    class Response:
        def raise_for_status(self): return None
        def json(self):
            return [{"username": "alpha", "name": "Alpha Example", "web_url": "https://gitlab.com/alpha", "public_email": "alpha@example.org"}]
    class Client:
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr("razvedchik.collectors.requests", Client())
    found = search_gitlab("Alpha")
    assert len(found) == 1
    assert found[0].source == "GitLab public user search"
    assert "@alpha" in found[0].snippet
    assert "alpha@example.org" in found[0].snippet


def test_stackexchange_collector_parses_public_user(monkeypatch):
    class Response:
        def raise_for_status(self): return None
        def json(self):
            return {"items": [{"user_id": 42, "display_name": "Alpha Example", "link": "https://stackoverflow.com/users/42/alpha-example", "reputation": 123, "website_url": "https://example.org"}]}
    class Client:
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr("razvedchik.collectors.requests", Client())
    found = search_stackexchange("Alpha")
    assert len(found) == 1
    assert found[0].source == "Stack Overflow public user search"
    assert "user_id: 42" in found[0].snippet


def test_openalex_collector_parses_public_author(monkeypatch):
    class Response:
        def raise_for_status(self): return None
        def json(self):
            return {"results": [{"id": "https://openalex.org/A123", "display_name": "Alpha Example", "works_count": 12, "cited_by_count": 34, "orcid": "https://orcid.org/0000-0000-0000-0001"}]}
    class Client:
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr("razvedchik.collectors.requests", Client())
    found = search_openalex("Alpha Example")
    assert len(found) == 1
    assert found[0].source == "OpenAlex public author search"
    assert "ORCID" in found[0].snippet


def test_wikidata_collector_parses_public_person(monkeypatch):
    class Response:
        def raise_for_status(self): return None
        def json(self):
            return {
                "results": {
                    "bindings": [
                        {
                            "item": {"value": "https://www.wikidata.org/entity/Q1"},
                            "itemLabel": {"value": "Alpha Example"},
                            "birth": {"value": "1981-12-18T00:00:00Z"},
                        }
                    ]
                }
            }
    class Client:
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr("razvedchik.collectors.requests", Client())
    found = search_wikidata("Alpha Example")
    assert len(found) == 1
    assert found[0].source == "Wikidata public knowledge base"
    assert "1981-12-18" in found[0].snippet


def test_relation_graph_and_report_serialization():
    inv = Investigation(mode="combined", query="Test Person")
    ev = Evidence("web", "https://example.org", "Result", "@alpha_user test@example.org", "query")
    eid = inv.add_evidence(ev)
    inv.add_candidate("candidate", "Result", {"@alpha_user", "test@example.org"}, {eid}, {"example.org"}, {"web"})
    inv.add_relation("@alpha_user", "co-occurs in source", "test@example.org", eid)
    inv.record_source_run("web", "query", 1)
    data = to_dict(inv)
    assert len(data["relations"]) == 1
    assert data["relations"][0]["evidence_ids"] == [eid]
    assert data["coverage"]["source_attempts"] == 1
    assert data["coverage"]["source_successes"] == 1
    assert "OpenAlex public author search" in data["coverage"]["direct_source_collectors"]


def test_configured_collectors_are_mode_aware():
    fio = configured_collectors(Investigation(mode="fio", query="x"))
    assert "GitHub public search" in fio
    assert "GitLab public user search" in fio
    assert "Stack Overflow public user search" in fio
    assert "OpenAlex public author search" in fio
    assert "Wikidata public knowledge base" in fio
    assert "Sherlock public username search (optional bridge)" not in fio
    username = configured_collectors(Investigation(mode="username", query="x"))
    assert "GitLab public user search" in username
    assert "Stack Overflow public user search" in username
    assert "Sherlock public username search (optional bridge)" in username


def test_entity_classification():
    assert classify_identifier("@alpha_user") == "username"
    assert classify_identifier("test@example.org") == "email"
    assert classify_identifier("79991234567") == "phone"


def test_entity_graph_keeps_sources_as_evidence_backed_edges():
    graph, edges = page_entities("Public profile", "@alpha_user test@example.org 79991234567", "https://example.org/profile", {"@alpha_user", "test@example.org", "79991234567"}, "evidence-1")
    assert "username:@alpha_user" in graph.entities
    assert "email:test@example.org" in graph.entities
    assert "phone:79991234567" in graph.entities
    assert any(edge[0] == "username:@alpha_user" and edge[1] == "found_on" for edge in edges)


def test_entity_graph_merge_preserves_evidence():
    first, second = EntityGraph(), EntityGraph()
    first.add("username", "@alpha_user", "evidence-1")
    second.add("username", "@alpha_user", "evidence-2")
    second.add("email", "test@example.org", "evidence-2")
    first.merge(second)
    assert first.entities["username:@alpha_user"].evidence_ids == {"evidence-1", "evidence-2"}
    assert "email:test@example.org" in first.entities


def test_entity_graph_does_not_create_identity_claim():
    graph, edges = page_entities("Same name only", "John Example", "https://example.org/profile", set(), "evidence-2")
    assert graph.entities
    assert not any(edge[1] == "same_as" for edge in edges)
