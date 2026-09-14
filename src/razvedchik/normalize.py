import re


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def phone_variants(value: str) -> list[str]:
    d = normalize_phone(value)
    if not d:
        return []
    variants = {d, "+" + d, "".join(d)}
    if len(d) == 11 and d.startswith("8"):
        variants.add("+7" + d[1:])
        variants.add("7" + d[1:])
    return sorted(variants)


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def expand_queries(mode: str, query: str) -> list[str]:
    q = normalize_text(query)
    if mode in {"phone", "combined"} and re.fullmatch(r"[+\d()\-\s]{7,}", q):
        return phone_variants(q)
    if mode in {"fio", "combined"}:
        parts = q.split()
        if len(parts) >= 2:
            return [q, " ".join(parts[:2]), " ".join(p[0] for p in parts if p)]
    return [q]
