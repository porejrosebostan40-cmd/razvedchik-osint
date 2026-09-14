from razvedchik.correlation import ROLE_DE_FACTO, ROLE_DE_JURE, ROLE_UNKNOWN, correlate_phone, phone_conflicts
from razvedchik.models import Evidence, Investigation


def test_phone_owner_and_actual_user_remain_separate():
    inv = Investigation(mode="phone", query="79991234567")
    owner = Evidence(
        source="Registry-like public source",
        url="https://example.org/owner",
        title="Мария Иванова",
        snippet="79991234567 зарегистрирован на Марию Иванову",
        query="79991234567",
        kind="phone-owner",
    )
    user = Evidence(
        source="Public contact source",
        url="https://example.net/contact",
        title="Александр Иванов",
        snippet="79991234567 контакт Александр Иванов",
        query="79991234567",
        kind="phone-user",
    )
    for ev in (owner, user):
        eid = inv.add_evidence(ev)
        inv.add_candidate(ev.title, ev.title, {"79991234567"}, {eid}, {ev.url.split('/')[2]}, {ev.source})

    links = correlate_phone(inv, "79991234567")
    assert {link.role for link in links} == {ROLE_DE_JURE, ROLE_DE_FACTO}
    assert phone_conflicts(links)


def test_phone_mention_does_not_become_owner_or_user():
    inv = Investigation(mode="phone", query="79991234567")
    ev = Evidence(
        source="Web",
        url="https://example.org/page",
        title="Объявление",
        snippet="79991234567 упомянут в тексте объявления",
        query="79991234567",
    )
    eid = inv.add_evidence(ev)
    inv.add_candidate(ev.title, ev.title, {"79991234567"}, {eid}, {"example.org"}, {ev.source})

    links = correlate_phone(inv, "79991234567")
    assert len(links) == 1
    assert links[0].role == ROLE_UNKNOWN
    assert not phone_conflicts(links)
