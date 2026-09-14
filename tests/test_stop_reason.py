from razvedchik.models import Investigation
from razvedchik.report import to_dict


def test_stop_reason_is_serialized():
    inv = Investigation(mode="fio", query="Test Person", stop_reason="no new queries")
    data = to_dict(inv)
    assert data["stop_reason"] == "no new queries"
