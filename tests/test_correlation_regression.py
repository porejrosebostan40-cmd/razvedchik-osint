from razvedchik.models import Evidence, Investigation


def test_identifier_free_evidence_uses_unique_candidate_keys():
    inv = Investigation(mode="fio", query="Test Person")
    first = Evidence("web", "https://example.org/one", "First", "no identifiers", "query")
    second = Evidence("web", "https://example.org/two", "Second", "no identifiers", "query")
    first_id = inv.add_evidence(first)
    second_id = inv.add_evidence(second)
    inv.add_candidate(f"evidence:{first_id}", first.title, set(), {first_id}, {"example.org"}, {"web"})
    inv.add_candidate(f"evidence:{second_id}", second.title, set(), {second_id}, {"example.org"}, {"web"})
    assert set(inv.candidates) == {f"evidence:{first_id}", f"evidence:{second_id}"}
