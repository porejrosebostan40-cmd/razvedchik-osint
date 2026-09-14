from razvedchik.sources import source_specs_for_mode


def test_source_registry_keeps_direct_sources_separate_from_bridge():
    specs = source_specs_for_mode("combined")
    names = [spec.name for spec in specs]
    assert names[:5] == [
        "web search",
        "GitHub public search",
        "GitLab public user search",
        "Stack Overflow public user search",
        "Wikidata public knowledge base",
    ]
    assert specs[-1].optional_bridge is True
    assert specs[-1].name == "Sherlock public username search (optional bridge)"


def test_source_registry_scopes_fio_to_relevant_sources():
    names = [spec.name for spec in source_specs_for_mode("fio")]
    assert "Wikidata public knowledge base" in names
    assert "Sherlock public username search (optional bridge)" not in names
