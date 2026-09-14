import json
import os
import requests

SYSTEM = """You are an OSINT investigation planner. Work only with public or legitimately accessible information. Never request bypasses, credentials, leaked databases, or private records. Return JSON with a list named queries. Queries must be concrete web-search queries that can discover public evidence or pivot identifiers. Do not assert that a person is identified."""


def ai_queries(mode: str, query: str, known: list[str]) -> list[str]:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return []
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        "input": f"Mode: {mode}\nSeed: {query}\nKnown identifiers: {known}\nReturn JSON only.",
        "instructions": SYSTEM,
    }
    try:
        r = requests.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        text = data.get("output_text", "")
        obj = json.loads(text)
        return [str(x) for x in obj.get("queries", []) if str(x).strip()][:8]
    except Exception:
        return []


def deterministic_queries(mode: str, query: str, known: list[str]) -> list[str]:
    base = [query]
    if mode == "fio":
        base += [f'"{query}"', f'"{query}" профиль', f'"{query}" телефон', f'"{query}" email']
    elif mode in {"username", "nickname"}:
        base += [f'"{query}"', f'"{query}" profile', f'"{query}" github', f'"{query}" telegram']
    elif mode == "phone":
        base += [f'"{query}"', f'"{query}" имя', f'"{query}" профиль', f'"{query}" контакт']
    elif mode == "email":
        base += [f'"{query}"', f'"{query}" profile', f'"{query}" github', f'"{query}" organization']
    for item in known:
        base.append(f'"{item}"')
    return list(dict.fromkeys(base))[:12]
