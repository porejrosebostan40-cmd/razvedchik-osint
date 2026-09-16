from datetime import datetime, timezone

from riskwatch.forecast import _root_event, _stage, _root_outcome, build_forecast, calibrate_probability


def event(title, snippet="", url="https://example.ru/a", ts=None, region=""):
    e = {"title": title, "snippet": snippet, "url": url, "region": region}
    if ts is not None:
        e["ts"] = ts
    return e


def test_generic_prison_news_is_not_root():
    e = event("В колонии заключенные получили медицинскую помощь и приняли участие в мероприятии")
    assert not _root_event(e)
    assert _stage(e) != 5


def test_denial_is_not_root():
    e = event("ФСИН: заключенных не будут привлекать к военной службе, сообщение опровергнуто")
    assert not _root_event(e)
    assert _stage(e) != 5


def test_target_specific_military_action_is_root():
    e = event(
        "Заключенные из исправительной колонии призваны на военную службу",
        "Минобороны подтвердило зачисление и направление заключенных в воинскую часть",
        url="https://mil.ru/example",
    )
    assert _root_event(e)
    assert _stage(e) == 5


def test_undated_event_cannot_resolve_time_bounded_forecast():
    e = event(
        "Заключенные из исправительной колонии призваны на военную службу",
        "Минобороны подтвердило зачисление и направление",
        url="https://mil.ru/example",
    )
    assert not _root_outcome([e], start_ts=1, end_ts=10**12)


def test_insufficient_calibration_is_unavailable_not_zero_percent():
    result = calibrate_probability(70, [], horizon="24-72h")
    assert result["status"] == "insufficient_history"
    assert result["probability"] is None


def test_regional_diversity_counts_regions_not_source_families():
    events = [
        event("ФСИН подготовила списки заключенных для отбора", url="https://one.ru/a", region="Region A"),
        event("ФСИН подготовила списки заключенных для отбора", url="https://two.ru/a", region="Region B"),
    ]
    forecast = build_forecast(events)
    assert forecast["regions_with_signals"] == 2
