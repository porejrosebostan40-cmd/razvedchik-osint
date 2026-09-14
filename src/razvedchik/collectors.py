import re
import shutil
import subprocess

import requests
from requests import RequestException
from .models import Evidence


API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "Razvedchik/0.2"}
URL_RE = re.compile(r"https?://[^\s<>\"']+")


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


def search_sherlock(username: str, limit: int = 20, timeout: int = 15) -> list[Evidence]:
    """Use an installed Sherlock CLI to enumerate public username profiles."""
    executable = shutil.which("sherlock")
    clean = username.strip().lstrip("@")
    if not executable or not clean or any(ch.isspace() for ch in clean) or "@" in clean:
        return []
    try:
        completed = subprocess.run(
            [executable, clean, "--print-found", "--no-color", "--timeout", str(timeout)],
            capture_output=True,
            text=True,
            timeout=max(timeout + 10, 30),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    urls: list[str] = []
    for url in URL_RE.findall(completed.stdout):
        url = url.rstrip(".,);]")
        if url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break

    return [
        Evidence(
            source="Sherlock public username search",
            url=url,
            title=f"Sherlock profile: {clean}",
            snippet=f"Public profile URL found for username {clean}",
            query=username,
            kind="sherlock-profile",
            confidence="found mention",
        )
        for url in urls
    ]
