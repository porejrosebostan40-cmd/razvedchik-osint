# scripts/test_bing_decode.py
# Изолированный тест распаковки Bing ck/a ссылок.
# Не трогает search.py. Читает уже сохранённый HTML.

import base64
import json
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

from riskwatch.search import _clean, _matches_site

HTML_PATH = '/tmp/test_site_query_Bing.html'
TARGETS = ('gov.ru',)

html = Path(HTML_PATH).read_text(encoding='utf-8')
soup = BeautifulSoup(html, 'html.parser')

anchors = soup.select('li.b_algo h2 a')
print(f'[ANCHORS] total: {len(anchors)}', file=sys.stderr)

results = []

for i, a in enumerate(anchors):
    href = a.get('href', '')
    title = a.get_text(strip=True)
    node = a.find_parent('li', class_='b_algo')
    snippet_node = node.select_one('.b_caption p') if node else None
    snippet = snippet_node.get_text(' ', strip=True) if snippet_node else ''

    print(f'--- [{i}] ---', file=sys.stderr)
    print(f'[RAW] {href[:200]}', file=sys.stderr)

    raw_clean = _clean(href)
    print(f'[CLEAN] {raw_clean[:200]}', file=sys.stderr)

    final_url = None
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    u_values = qs.get('u') or qs.get('url') or []

    if u_values:
        u = u_values[0]
        candidate = u[2:] if u.startswith('a1') else u
        candidate += '=' * (-len(candidate) % 4)
        try:
            decoded = base64.urlsafe_b64decode(candidate).decode('utf-8', errors='replace')
            print(f'[DECODE_U] {decoded}', file=sys.stderr)
            final_url = decoded
        except Exception as exc:
            print(f'[DECODE_U_ERROR] {exc}', file=sys.stderr)
    else:
        print('[DECODE_U] no u/url parameter', file=sys.stderr)

    head_final = None
    try:
        r = requests.head(href, allow_redirects=True, timeout=10)
        head_final = r.url
        print(f'[HEAD_FINAL] {head_final}', file=sys.stderr)
    except Exception as exc:
        print(f'[HEAD_ERROR] {exc}', file=sys.stderr)

    passed = None
    for candidate in (final_url, head_final, raw_clean):
        if candidate:
            passed = _matches_site(candidate, TARGETS)
            print(f'[SITE_MATCH] {passed} for {candidate[:120]}', file=sys.stderr)
            break

    results.append({
        'raw': href,
        'clean': raw_clean,
        'decoded_u': final_url,
        'head_final': head_final,
        'site_match': passed,
        'title': title,
        'snippet': snippet,
    })

Path('/tmp/test_bing_decode_result.json').write_text(
    json.dumps({'targets': TARGETS, 'anchors': results}, ensure_ascii=False, indent=2),
    encoding='utf-8',
)
print('[DONE] /tmp/test_bing_decode_result.json', file=sys.stderr)
