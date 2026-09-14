import re
import shutil
import subprocess

import requests
from requests import RequestException
from .models import Evidence


API = "https://api.github.com"
GITLAB_API = "https://gitlab.com/api/v4"
STACK_API = "https://api.stackexchange.com/2.3/users"
WIKIDATA_API = "https://query.wikidata.org/sparql"
OPENALEX_API = "https://api.openalex.org/authors"
HEADERS = {"Accept": "application/json", "User-Agent": "Razvedchik/0.4"}
URL_RE = re.compile(r"https?://[^\s<>\"']+")


def search_github(query: str, limit: int = 6, timeout: int = 10) -> list[Evidence]:
    """Search only public GitHub users; never accesses private data."""
    try:
        response = requests.get(f"{API}/search/users", params={"q": query, "per_page": min(limit, 10)}, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        items = response.json().get("items", [])
    except (RequestException, ValueError):
        return []
    out: list[Evidence] = []
    for item in items:
        login, url = item.get("login", ""), item.get("html_url", "")
        if login and url:
            out.append(Evidence("GitHub public search", url, f"GitHub user: {login}", f"Public GitHub account matching query: @{login}; search seed: {query}", query, "github-user", "found mention"))
    return out


def search_gitlab(query: str, limit: int = 6, timeout: int = 10) -> list[Evidence]:
    """Search public GitLab users through GitLab's unauthenticated users endpoint."""
    clean = query.strip().lstrip("@")
    if not clean or clean.startswith("-"):
        return []
    try:
        response = requests.get(f"{GITLAB_API}/users", params={"search": clean, "per_page": min(limit, 10)}, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        items = response.json()
    except (RequestException, ValueError):
        return []
    out: list[Evidence] = []
    for item in items:
        username, name, url = item.get("username", ""), item.get("name", ""), item.get("web_url", "")
        if not username or not url:
            continue
        public_email = item.get("public_email") or ""
        details = f"Public GitLab user @{username}"
        if name:
            details += f"; name: {name}"
        if public_email:
            details += f"; public email: {public_email}"
        details += f"; search seed: {query}"
        out.append(Evidence("GitLab public user search", url, f"GitLab user: {username}" + (f" — {name}" if name else ""), details, query, "gitlab-user", "found mention"))
    return out


def search_stackexchange(query: str, limit: int = 6, timeout: int = 10) -> list[Evidence]:
    """Search public Stack Overflow users by display name."""
    clean = " ".join(query.strip().split())
    if not clean or clean.startswith("-"):
        return []
    try:
        response = requests.get(STACK_API, params={"site": "stackoverflow", "inname": clean, "pagesize": min(limit, 10)}, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        items = response.json().get("items", [])
    except (RequestException, ValueError):
        return []
    out: list[Evidence] = []
    for item in items:
        user_id, name, url = item.get("user_id"), item.get("display_name", ""), item.get("link", "")
        if not user_id or not url:
            continue
        snippet = f"Public Stack Overflow user: {name}; user_id: {user_id}; search seed: {query}"
        if item.get("reputation") is not None:
            snippet += f"; reputation: {item['reputation']}"
        if item.get("website_url"):
            snippet += f"; website: {item['website_url']}"
        out.append(Evidence("Stack Overflow public user search", url, f"Stack Overflow user: {name}", snippet, query, "stackoverflow-user", "found mention"))
    return out


def search_wikidata(query: str, limit: int = 6, timeout: int = 15) -> list[Evidence]:
    """Search exact human-name labels in public Wikidata."""
    clean = " ".join(query.strip().split())
    if not clean or len(clean) > 160 or '"' in clean or "\\" in clean:
        return []
    escaped = clean.replace("'", "\\'")
    sparql = f'''SELECT ?item ?itemLabel ?birth WHERE {{
  ?item wdt:P31 wd:Q5; rdfs:label ?label.
  FILTER(LANG(?label) = "ru" || LANG(?label) = "en")
  FILTER(STR(?label) = '{escaped}')
  OPTIONAL {{ ?item wdt:P569 ?birth. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ru,en". }}
}} LIMIT {min(limit, 10)}'''
    try:
        response = requests.get(WIKIDATA_API, params={"query": sparql, "format": "json"}, headers={"Accept": "application/sparql-results+json", "User-Agent": HEADERS["User-Agent"]}, timeout=timeout)
        response.raise_for_status()
        bindings = response.json().get("results", {}).get("bindings", [])
    except (RequestException, ValueError):
        return []
    out: list[Evidence] = []
    for row in bindings:
        item = row.get("item", {}).get("value", "")
        label = row.get("itemLabel", {}).get("value", clean)
        birth = row.get("birth", {}).get("value", "")
        if not item:
            continue
        snippet = f"Public Wikidata human entity: {label}; seed: {query}" + (f"; birth: {birth[:10]}" if birth else "")
        out.append(Evidence("Wikidata public knowledge base", item, f"Wikidata: {label}", snippet, query, "wikidata-person", "found mention"))
    return out


def search_openalex(query: str, limit: int = 6, timeout: int = 10) -> list[Evidence]:
    """Search public OpenAlex author records by author name."""
    clean = " ".join(query.strip().split())
    if not clean or clean.startswith("-") or len(clean) > 160:
        return []
    try:
        response = requests.get(OPENALEX_API, params={"search": clean, "per-page": min(limit, 10)}, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        items = response.json().get("results", [])
    except (RequestException, ValueError):
        return []
    out: list[Evidence] = []
    for item in items:
        author_id = item.get("id", "")
        display_name = item.get("display_name", "")
        if not author_id or not display_name:
            continue
        works = item.get("works_count")
        cited = item.get("cited_by_count")
        orcid = item.get("orcid") or ""
        snippet = f"Public OpenAlex author: {display_name}; search seed: {query}"
        if works is not None:
            snippet += f"; works: {works}"
        if cited is not None:
            snippet += f"; cited by: {cited}"
        if orcid:
            snippet += f"; ORCID: {orcid}"
        out.append(Evidence("OpenAlex public author search", author_id, f"OpenAlex author: {display_name}", snippet, query, "openalex-author", "found mention"))
    return out


def search_sherlock(username: str, limit: int = 20, timeout: int = 15) -> list[Evidence]:
    """Use an installed Sherlock CLI to enumerate public username profiles."""
    executable = shutil.which("sherlock")
    clean = username.strip().lstrip("@")
    if not executable or not clean or clean.startswith("-") or any(ch.isspace() for ch in clean) or "@" in clean or clean.isdigit():
        return []
    try:
        completed = subprocess.run([executable, "--print-found", "--no-color", "--timeout", str(timeout), "--", clean], capture_output=True, text=True, timeout=max(timeout + 10, 30), check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    urls: list[str] = []
    for url in URL_RE.findall(completed.stdout):
        url = url.rstrip(".,);]")
        if url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return [Evidence("Sherlock public username search", url, f"Sherlock profile: {clean}", f"Public profile URL found for username @{clean}", username, "sherlock-profile", "found mention") for url in urls]
