from datetime import datetime, timezone


def test_safe_root_rejects_negative_denial():
    from riskwatch.semantics import safe_root_event
    e = {"url": "https://example.org/a", "title": "ФСИН сообщила: заключенных не будут привлекать к военной службе", "snippet": "мобилизация исключена"}
    assert not safe_root_event(e)


def test_safe_root_rejects_non_military_prisoner_action():
    from riskwatch.semantics import safe_root_event
    e = {"url": "https://example.org/a", "title": "Заключенных направили на работы", "snippet": "транспорт и размещение"}
    assert not safe_root_event(e)


def test_safe_root_accepts_explicit_military_action():
    from riskwatch.semantics import safe_root_event
    e = {"url": "https://example.org/a", "title": "Заключенных направили на военную службу", "snippet": "после отбора"}
    assert safe_root_event(e)


def test_runner_resolution_ignores_untimestamped_event():
    from riskwatch.runner import _root_outcome
    e = {"url": "https://example.org/a", "title": "Заключенных направили на военную службу", "snippet": ""}
    assert not _root_outcome([e], 1000, 2000)


def test_runner_resolution_ignores_pre_creation_root_event():
    from riskwatch.runner import _root_outcome
    e = {"url": "https://example.org/a", "title": "Заключенных направили на военную службу", "snippet": "военная служба", "published_ts": 900}
    assert not _root_outcome([e], 1000, 2000)


def test_runner_resolution_accepts_in_window_root_event():
    from riskwatch.runner import _root_outcome
    e = {"url": "https://example.org/a", "title": "Заключенных направили на военную службу", "snippet": "военная служба", "published_ts": 1500}
    assert _root_outcome([e], 1000, 2000)


def test_retrieval_telemetry_is_explicitly_not_reality_coverage():
    from riskwatch.runner import _retrieval_telemetry
    items = [("core", "q1"), ("regional: A", "q2"), ("regional: B", "q3")]
    telemetry = _retrieval_telemetry(items, {0: [], 1: [{"url": "https://example.org/a"}], 2: []})
    assert telemetry["queries_attempted"] == 3
    assert telemetry["queries_with_results"] == 1
    assert telemetry["regional_queries_attempted"] == 2
    assert telemetry["regional_queries_with_results"] == 1
    assert telemetry["coverage_is_retrieval_not_reality"] is True


def test_semantics_keeps_fsin_context_from_being_a_root_by_itself():
    from riskwatch.semantics import safe_root_event
    e = {"url": "https://fsin.gov.ru/a", "title": "ФСИН: заключенные прошли медицинский осмотр", "snippet": "подготовка документов"}
    assert not safe_root_event(e)
