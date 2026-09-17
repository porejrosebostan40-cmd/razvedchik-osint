# scripts/test_site_query.py
# Изолированный диагностический тест одного site: запроса.
# НЕ влияет на production. НЕ трогает search.py.
# Запуск: python scripts/test_site_query.py

import sys
import json
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from riskwatch.config import SETTINGS
from riskwatch.search import (
    HEADERS,
    _extract_results,
    _site_targets,
    _matches_site,
)

QUERY = 'site:gov.ru ФСИН колония осужден'

ENDPOINTS = [
    ('DuckDuckGo', 'https://html.duckduckgo.com/html/?q=' + quote_plus(QUERY)),
    ('Bing',       'https://www.bing.com/search?q=' + quote_plus(QUERY)),
]

targets = _site_targets(QUERY)
print(f'[QUERY] {QUERY}', file=sys.stderr)
print(f'[TARGETS] {targets}', file=sys.stderr)
print(f'[TIMEOUT] {SETTINGS.request_timeout}', file=sys.stderr)
print('', file=sys.stderr)

results = {}

for source, url in ENDPOINTS:
    print(f'=== {source} ===', file=sys.stderr)
    print(f'[URL] {url}', file=sys.stderr)

    entry = {'source': source, 'url': url}

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=SETTINGS.request_timeout,
            allow_redirects=True,
        )
        html = r.text

        history = [
            {'url': h.url, 'status': h.status_code}
            for h in r.history
        ]
        content_type = r.headers.get('Content-Type', '')
        final_url = r.url

        print(f'[STATUS] {r.status_code}', file=sys.stderr)
        print(f'[FINAL_URL] {final_url}', file=sys.stderr)
        print(f'[CONTENT_TYPE] {content_type}', file=sys.stderr)
        print(f'[HISTORY] {history}', file=sys.stderr)
        print(f'[SIZE] {len(html)} bytes', file=sys.stderr)
        print(f'[HTML] gov.ru: {"gov.ru" in html}', file=sys.stderr)
        print(f'[HTML] фсин: {"фсин" in html.lower()}', file=sys.stderr)
        print(f'[HTML] колония: {"колония" in html.lower()}', file=sys.stderr)

        soup = BeautifulSoup(html, 'html.parser')
        out = _extract_results(soup, source, targets, 20)
        print(f'[EXTRACTED] total: {len(out)}', file=sys.stderr)

        samples = []
        for i, item in enumerate(list(out)[:10]):
            u = item.get('url', '')
            t = item.get('title', '')
            s = item.get('snippet', '')
            passed = _matches_site(u, targets) if targets else None
            print(f'  [{i}] site_match={passed} url={u}', file=sys.stderr)
            print(f'      title={t[:80]}', file=sys.stderr)
            samples.append({
                'url': u, 'title': t, 'snippet': s,
                'site_match': passed,
            })

        entry.update({
            'status': r.status_code,
            'final_url': final_url,
            'content_type': content_type,
            'history': history,
            'size': len(html),
            'html_has_gov_ru': 'gov.ru' in html,
            'html_has_fsin': 'фсин' in html.lower(),
            'html_has_koloniya': 'колония' in html.lower(),
            'extracted_count': len(out),
            'extracted': samples,
        })

        Path(f'/tmp/test_site_query_{source}.html').write_text(html, encoding='utf-8')

    except requests.RequestException as exc:
        print(f'[ERROR] {exc}', file=sys.stderr)
        entry.update({'error': str(exc)})

    results[source] = entry
    print('', file=sys.stderr)

Path('/tmp/test_site_query_result.json').write_text(
    json.dumps(
        {'query': QUERY, 'targets': targets, 'results': results},
        ensure_ascii=False, indent=2,
    ),
    encoding='utf-8',
)
print('[DONE] /tmp/test_site_query_result.json', file=sys.stderr)
