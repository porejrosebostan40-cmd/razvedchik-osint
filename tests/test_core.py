from razvedchik.extract import identifiers
from razvedchik.normalize import phone_variants


def test_identifier_extraction():
    found = identifiers("Contact @alpha_user or test@example.org, +7 999 123-45-67")
    assert "@alpha_user" in found
    assert "test@example.org" in found
    assert "79991234567" in found


def test_phone_variants():
    values = phone_variants("8 (999) 123-45-67")
    assert "+79991234567" in values
    assert "79991234567" in values
