from bs4 import BeautifulSoup
import requests
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
from .config import SETTINGS

HEADERS={"User-Agent":"RiskWatch/1.0 (+public-source-monitoring)"}


def _clean(url):
    try:
        p=urlparse(url)
        if p.netloc.endswith("duckduckgo.com") and p.path.startswith("/l/"):
            return unquote(parse_qs(p.query).get("uddg",[url])[0])
    except Exception:
        pass
    return url


def _site_targets(query):
    targets=[]
    for token in str(query).split():
        if token.lower().startswith("site:"):
            value=token[5:].strip().lower().strip('"')
            if value:
                targets.append(value.removeprefix("www."))
    return tuple(targets)


def _matches_site(url, targets):
    if not targets:
        return True
    try:
        domain=urlparse(url).netloc.lower().split(":")[0].removeprefix("www.")
    except ValueError:
        return False
    return any(domain == target or domain.endswith("." + target) for target in targets)


def search(query, limit=None):
    limit=limit or SETTINGS.max_results_per_query
    targets=_site_targets(query)
    endpoints=[("DuckDuckGo","https://html.duckduckgo.com/html/?q="+quote_plus(query)),("Bing","https://www.bing.com/search?q="+quote_plus(query))]
    for source,url in endpoints:
        try:
            r=requests.get(url,headers=HEADERS,timeout=SETTINGS.request_timeout); r.raise_for_status()
            soup=BeautifulSoup(r.text,"html.parser"); out=[]
            selector=".result" if source=="DuckDuckGo" else "li.b_algo"
            for node in soup.select(selector):
                a=node.select_one("a.result__a") if source=="DuckDuckGo" else node.select_one("h2 a")
                if not a: continue
                result_url=_clean(a.get("href",""))
                if not _matches_site(result_url, targets): continue
                sn=node.select_one(".result__snippet") if source=="DuckDuckGo" else node.select_one(".b_caption p")
                out.append({"source":source,"url":result_url,"title":a.get_text(" ",strip=True),"snippet":sn.get_text(" ",strip=True) if sn else "","query":query})
                if len(out)>=limit: break
            if out: return out
        except requests.RequestException:
            pass
    return []
