import requests
from requests import RequestException
from .models import Evidence


API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "Razvedchik/0.2"}


def search_github(query: str, limit: int = 6, timeout: int = 10) -> list[Evidence]:
    """Search only public GitHub users/repos; never accesses private data."""
    try:
        response = requests.get(
            f"{API}/search/users",
            params={"q": query, "per_page": min(limit, 10)},
            headers=HEADERS,
            timeout=timeout,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
    except (RequestException, ValueError):
        return []

    out: list[Evidence] = []
    for item in items:
        login = item.get("login", "")
        url = item.get("html_url", "")
        if not login or not url:
            continue
        out.append(Evidence(
            source="GitHub public search",
            url=url,
            title=f"GitHub user: {login}",
            snippet=f"Public GitHub account matching query: {query}",
            query=query,
            kind="github-user",
            confidence="found mention",
        ))
    return out
