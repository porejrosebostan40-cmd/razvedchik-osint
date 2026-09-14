import re
from urllib.parse import urlparse

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
USERNAME = re.compile(r"(?<![\w@])@[A-Za-z0-9_.-]{3,32}\b")
PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d ()-]{7,}\d)(?!\d)")


def identifiers(text: str) -> set[str]:
    found: set[str] = set(EMAIL.findall(text))
    found.update(USERNAME.findall(text))
    for phone in PHONE.findall(text):
        digits = re.sub(r"\D", "", phone)
        if len(digits) >= 9:
            found.add(digits)
    return found


def domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""
