from bs4 import BeautifulSoup
import base64
import os
import requests
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
from .config import SETTINGS

HEADERS={"User-Agent":"RiskWatch/1.0 (+public-source-monitoring)"}
SEARCH_ENGINE_DOMAINS=("duckduckgo.com","bing.com","google.com","yandex.ru","yandex.com")

class SearchResult(list):
    def __init__(self, values=(), telemetry=None):
        super().__init__(values)
        self.telemetry=telemetry or {}


def _clean(url):
    try:
        p=urlparse(url)
        host=p.netloc.lower().split(":")[0]
        if host.endswith("duckduckgo.com") and p.path.startswith("/l/"):
            return unquote(parse_qs(p.query).get("uddg",[url])[0])
        if host.endswith("bing.com") and p.path.startswith("/ck/a"):
            value=parse_qs(p.query).get("u",[""])[0]
            if value.startswith("a1"):
                try:
                    return base64.b64decode(value[2:] + "===").decode("utf-8",errors="ignore") or url
                except Exception:
                    pass
            if value.startswith("http"):
                return unquote(value)
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


def _domain(url):
    try:
        return urlparse(url).netloc.lower().split(":")[0].removeprefix("www.")
    except ValueError:
        return ""


def _matches_site(url, targets):
    if not targets:
        return True
    domain=_domain(url)
    return bool(domain) and any(domain == target or domain.endswith("." + target) for target in targets)


def _usable_result_url(url, targets):
    url=_clean(url)
    domain=_domain(url)
    if not domain or domain in SEARCH_ENGINE_DOMAINS or any(domain.endswith("."+x) for x in SEARCH_ENGINE_DOMAINS):
        return False
    return _matches_site(url, targets)


def _extract_results(soup, source, targets, limit):
    selectors=(".result a.result__a","li.b_algo h2 a","h2 a") if source=="Bing" else (".result a.result__a",".result h2 a")
    raw=[]
    seen_raw=set()
    for selector in selectors:
        for a in soup.select(selector):
            href=str(a.get("href", ""))
            key=(href,a.get_text(" ",strip=True))
            if key in seen_raw:
                continue
            seen_raw.add(key)
            raw.append(a)
    raw_results=len(raw)
    after_search_filter=0
    after_site_filter=0
    anchors=[]
    seen=set()
    for a in raw:
        href=_clean(a.get("href", ""))
        domain=_domain(href)
        if not domain or domain in SEARCH_ENGINE_DOMAINS or any(domain.endswith("."+x) for x in SEARCH_ENGINE_DOMAINS):
            continue
        after_search_filter += 1
        if not _matches_site(href, targets):
            continue
        after_site_filter += 1
        if href in seen:
            continue
        seen.add(href)
        anchors.append(a)
        if len(anchors)>=limit:
            break
    telemetry={
        "raw_results":raw_results,
        "after_search_url_filter":after_search_filter,
        "after_site_filter":after_site_filter,
        "after_dedup":len(anchors),
    }
    out=[]
    for a in anchors:
        node=a.find_parent(class_="result") if source=="DuckDuckGo" else a.find_parent("li",class_="b_algo")
        if node is None: node=a.parent
        title=a.get_text(" ",strip=True)
        snippet=""
        if source=="DuckDuckGo":
            sn=node.select_one(".result__snippet") if node else None
        else:
            sn=node.select_one(".b_caption p") if node else None
        if sn: snippet=sn.get_text(" ",strip=True)
        out.append({"source":source,"url":_clean(a.get("href","")),"title":title,"snippet":snippet,"query":""})
    return SearchResult(out,telemetry)


def _write_raw_debug(source, query, html):
    path=os.getenv("RISKWATCH_DEBUG_HTML")
    if not path:
        return
    try:
        with open(path,"w",encoding="utf-8") as f:
            f.write("<!-- source: "+source+" -->\n<!-- query: "+query.replace("--","-")+" -->\n")
            f.write(html[:1_500_000])
    except OSError:
        pass


def search(query, limit=None):
    limit=limit or SETTINGS.max_results_per_query
    targets=_site_targets(query)
    endpoints=[("DuckDuckGo","https://html.duckduckgo.com/html/?q="+quote_plus(query)),("Bing","https://www.bing.com/search?q="+quote_plus(query))]
    aggregate={"raw_results":0,"after_search_url_filter":0,"after_site_filter":0,"after_dedup":0}
    for source,url in endpoints:
        try:
            r=requests.get(url,headers=HEADERS,timeout=SETTINGS.request_timeout); r.raise_for_status()
            if os.getenv("RISKWATCH_DEBUG_HTML") and not os.path.exists(os.getenv("RISKWATCH_DEBUG_HTML")):
                _write_raw_debug(source,query,r.text)
            soup=BeautifulSoup(r.text,"html.parser")
            out=_extract_results(soup,source,targets,limit)
            for key,value in out.telemetry.items():
                aggregate[key]+=value
            if out:
                for item in out: item["query"]=query
                out.telemetry=aggregate
                return out
        except requests.RequestException:
            pass
    return SearchResult([],aggregate)
