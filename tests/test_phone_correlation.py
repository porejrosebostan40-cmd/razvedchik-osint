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


def test_one_person_can_be_both_owner_and_user():
    inv = Investigation(mode="phone", query="79991234567")
    ev1 = Evidence("Source A", "https://example.org/a", "Александр Иванов", "79991234567 зарегистрирован на Александра Иванова", "79991234567", kind="phone-owner")
    ev2 = Evidence("Source B", "https://example.net/b", "Александр Иванов", "79991234567 контакт Александр Иванов", "79991234567", kind="phone-user")
    eids = []
    for ev in (ev1, ev2):
        eid = inv.add_evidence(ev)
        eids.append(eid)
    inv.add_candidate("alex", "Александр Иванов", {"79991234567"}, set(eids), {"example.org", "example.net"}, {"Source A", "Source B"})

    links = correlate_phone(inv, "79991234567")
    assert len(links) == 1
    assert set(links[0].roles) == {ROLE_DE_JURE, ROLE_DE_FACTO}
    assert not phone_conflicts(links)


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
