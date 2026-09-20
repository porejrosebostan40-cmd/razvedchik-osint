import os
from urllib.parse import urlparse

import requests

from .search import SearchResult


EXA_SEARCH_URL = "https://api.exa.ai/search"
DEFAULT_NUM_RESULTS = 10


def _normalize_result(item, query):
    if not isinstance(item, dict):
        return None

    url = str(item.get("url") or "").strip()
    if not url:
        return None

    title = str(item.get("title") or "").strip()
    highlights = item.get("highlights")
    if isinstance(highlights, list):
        snippet = " ".join(str(x).strip() for x in highlights if str(x).strip())
    else:
        snippet = str(item.get("text") or item.get("snippet") or "").strip()

    result = {
        "source": "Exa",
        "url": url,
        "title": title,
        "snippet": snippet,
        "query": query,
    }

    # Preserve useful Exa metadata without changing the SearchResult contract.
    for key in ("publishedDate", "author", "score", "id"):
        if key in item and item[key] not in (None, ""):
            result[key] = item[key]

    return result


def search(query, limit=DEFAULT_NUM_RESULTS, timeout=60):
    """
    Query Exa and return a RiskWatch-compatible SearchResult.

    Exa failures are deliberately contained: callers receive an empty
    SearchResult plus telemetry instead of an exception.
    """
    key = os.environ.get("EXA_API_KEY")
    telemetry = {
        "exa_raw": 0,
        "after_url_filter": 0,
        "reason": None,
    }

    if not key:
        telemetry["reason"] = "missing_api_key"
        return SearchResult([], telemetry)

    try:
        response = requests.post(
            EXA_SEARCH_URL,
            headers={
                "x-api-key": key,
                "Content-Type": "application/json",
            },
            json={
                "query": str(query),
                "type": "auto",
                "numResults": int(limit),
                "contents": {
                    "highlights": {"maxCharacters": 1200},
                },
            },
            timeout=timeout,
        )

        status = int(response.status_code)
        if status == 401:
            telemetry["reason"] = "http_401"
            return SearchResult([], telemetry)
        if status == 429:
            telemetry["reason"] = "http_429"
            return SearchResult([], telemetry)
        if status >= 500:
            telemetry["reason"] = f"http_{status}"
            return SearchResult([], telemetry)

        response.raise_for_status()
        payload = response.json()
        raw = payload.get("results") if isinstance(payload, dict) else []
        raw = raw if isinstance(raw, list) else []
        telemetry["exa_raw"] = len(raw)

        out = []
        seen = set()
        for item in raw:
            normalized = _normalize_result(item, str(query))
            if normalized is None:
                continue
            parsed = urlparse(normalized["url"])
            if not parsed.scheme or not parsed.netloc:
                continue
            telemetry["after_url_filter"] += 1
            if normalized["url"] in seen:
                continue
            seen.add(normalized["url"])
            out.append(normalized)
            if len(out) >= int(limit):
                break

        telemetry["after_dedup"] = len(out)
        return SearchResult(out, telemetry)

    except requests.Timeout:
        telemetry["reason"] = "timeout"
        return SearchResult([], telemetry)
    except requests.RequestException as exc:
        telemetry["reason"] = f"request_error:{type(exc).__name__}"
        return SearchResult([], telemetry)
    except (ValueError, TypeError, KeyError):
        telemetry["reason"] = "invalid_response"
        return SearchResult([], telemetry)
    except Exception as exc:
        # Never let an Exa integration failure break the existing search layer.
        telemetry["reason"] = f"unexpected_error:{type(exc).__name__}"
        return SearchResult([], telemetry)
