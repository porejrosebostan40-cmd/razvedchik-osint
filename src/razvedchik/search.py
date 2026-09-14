from bs4 import BeautifulSoup
import requests
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
from .models import Evidence

HEADERS = {"User-Agent": "Razvedchik/0.2 (+open-source-research)"}


def _clean_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            return unquote(target) or url
    except Exception:
        pass
    return url


def _parse_ddg(html: str, query: str, limit: int) -> list[Evidence]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Evidence] = []
    for result in soup.select(".result")[:limit]:
        a = result.select_one("a.result__a")
        snippet = result.select_one(".result__snippet")
        if not a:
            continue
        href = _clean_url(a.get("href", ""))
        title = a.get_text(" ", strip=True)
        text = snippet.get_text(" ", strip=True) if snippet else ""
        out.append(Evidence(source="DuckDuckGo", url=href, title=title, snippet=text, query=query))
    return out


def _parse_bing(html: str, query: str, limit: int) -> list[Evidence]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Evidence] = []
    for result in soup.select("li.b_algo")[:limit]:
        a = result.select_one("h2 a")
        snippet = result.select_one(".b_caption p")
        if not a:
            continue
        out.append(Evidence(
            source="Bing",
            url=a.get("href", ""),
            title=a.get_text(" ", strip=True),
            snippet=snippet.get_text(" ", strip=True) if snippet else "",
            query=query,
        ))
    return out


def search_web(query: str, limit: int = 8, timeout: int = 15) -> list[Evidence]:
    endpoints = [
        ("DuckDuckGo", "https://html.duckduckgo.com/html/?q=" + quote_plus(query)),
        ("Bing", "https://www.bing.com/search?q=" + quote_plus(query)),
    ]
    for source, url in endpoints:
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            parsed = _parse_ddg(response.text, query, limit) if source == "DuckDuckGo" else _parse_bing(response.text, query, limit)
            if parsed:
                return parsed
        except requests.RequestException:
            continue
    return []
