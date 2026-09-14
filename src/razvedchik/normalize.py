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
        alpha_parts = [part for part in parts if re.fullmatch(r"[\wА-Яа-яЁё-]+", part, flags=re.UNICODE)]
        year_or_date = [
            part for part in parts
            if re.fullmatch(r"(?:19|20)\d{2}", part)
            or re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-](?:19|20)\d{2}", part)
        ]
        if len(alpha_parts) >= 2:
            fio = " ".join(alpha_parts)
            variants = [q, fio, " ".join(part[0] for part in alpha_parts if part)]
            if year_or_date:
                variants.extend(f'"{fio}" {value}' for value in year_or_date)
            return list(dict.fromkeys(variants))
    return [q]
