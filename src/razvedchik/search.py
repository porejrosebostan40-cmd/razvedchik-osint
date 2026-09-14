from bs4 import BeautifulSoup
import requests
from urllib.parse import quote_plus
from .models import Evidence

HEADERS = {"User-Agent": "Razvedchik/0.1 (+open-source-research)"}


def search_web(query: str, limit: int = 8, timeout: int = 15) -> list[Evidence]:
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    out: list[Evidence] = []
    for result in soup.select(".result")[:limit]:
        a = result.select_one("a.result__a")
        snippet = result.select_one(".result__snippet")
        if not a:
            continue
        href = a.get("href", "")
        title = a.get_text(" ", strip=True)
        text = snippet.get_text(" ", strip=True) if snippet else ""
        out.append(Evidence(source="DuckDuckGo", url=href, title=title, snippet=text, query=query))
    return out
