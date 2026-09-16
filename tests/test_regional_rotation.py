from riskwatch.config import REGIONS, REGIONAL_TEMPLATES
from riskwatch.runner import BATCH_SIZE, _queries
from riskwatch.store import Store


def test_regional_rotation_covers_all_queries_in_27_runs_without_overlap():
    total = len(REGIONS) * len(REGIONAL_TEMPLATES)
    assert total == 801
    cursor = 0
    batches = []
    for _ in range(27):
        items, next_cursor, wrapped = _queries(cursor)
        regional = tuple(items[len(items) - BATCH_SIZE:])
        batches.append(regional)
        cursor = next_cursor

    flattened = [item for batch in batches for item in batch]
    assert len(set(flattened)) == total
    assert all(set(batches[i]).isdisjoint(batches[i + 1]) for i in range(26))
    assert cursor == 0
    assert len(batches[-1]) == total % BATCH_SIZE


def test_regional_rotation_wraps_only_on_final_partial_batch():
    total = len(REGIONS) * len(REGIONAL_TEMPLATES)
    cursor = 0
    wrapped = []
    for _ in range(27):
        items, next_cursor, did_wrap = _queries(cursor)
        wrapped.append(did_wrap)
        cursor = next_cursor
    assert wrapped[:-1] == [False] * 26
    assert wrapped[-1] is True
    assert total % BATCH_SIZE == 21


def test_store_persists_cursor_and_cycle():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        store = Store(str(path))
        store.set_meta("regional_cursor", 780)
        store.set_meta("regional_cycle", 3)
        restored = Store(str(path))
        assert restored.get_meta("regional_cursor") == 780
        assert restored.get_meta("regional_cycle") == 3
