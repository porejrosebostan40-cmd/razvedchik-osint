from types import SimpleNamespace

from razvedchik.collectors import search_sherlock


def test_sherlock_collector_parses_public_profile_urls():
    monkeypatch = None
    assert monkeypatch is None


def test_sherlock_collector_parses_public_profile_urls_with_mock(monkeypatch):
    monkeypatch.setattr("razvedchik.collectors.shutil.which", lambda name: "/usr/bin/sherlock")
    monkeypatch.setattr(
        "razvedchik.collectors.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="Found: https://example.org/user\nFound: https://social.example/user\n"
        ),
    )
    results = search_sherlock("alpha_user")
    assert [item.url for item in results] == [
        "https://example.org/user",
        "https://social.example/user",
    ]
    assert all(item.kind == "sherlock-profile" for item in results)
    assert all("@alpha_user" in item.snippet for item in results)


def test_sherlock_collector_rejects_email_like_input(monkeypatch):
    monkeypatch.setattr("razvedchik.collectors.shutil.which", lambda name: "/usr/bin/sherlock")
    assert search_sherlock("person@example.org") == []


def test_sherlock_collector_rejects_phone_like_input(monkeypatch):
    monkeypatch.setattr("razvedchik.collectors.shutil.which", lambda name: "/usr/bin/sherlock")
    assert search_sherlock("79991234567") == []


def test_sherlock_collector_rejects_option_like_input(monkeypatch):
    monkeypatch.setattr("razvedchik.collectors.shutil.which", lambda name: "/usr/bin/sherlock")
    assert search_sherlock("--help") == []
