import json, os, time
from pathlib import Path
import requests

QUERIES = [
("Президент России",'site:kremlin.ru ("мобилизация" OR "призыв" OR "контракт" OR "осужденные" OR "ФСИН" OR "военная служба")'),
("Правительство России",'site:government.ru ("мобилизация" OR "призыв" OR "контракт" OR "осужденные" OR "ФСИН" OR "военная служба")'),
("Минобороны России",'site:mil.ru ("мобилизация" OR "призыв" OR "контракт" OR "осужденные" OR "ФСИН" OR "военная служба")'),
("ФСИН России",'site:fsin.gov.ru ("мобилизация" OR "призыв" OR "контракт" OR "осужденные" OR "ФСИН" OR "военная служба")'),
("Минюст России",'site:minjust.gov.ru ("мобилизация" OR "призыв" OR "контракт" OR "осужденные" OR "ФСИН" OR "военная служба")'),
("Генеральная прокуратура",'site:epp.genproc.gov.ru ("мобилизация" OR "призыв" OR "контракт" OR "осужденные" OR "ФСИН" OR "военная служба")'),
("Госдума",'site:duma.gov.ru ("мобилизация" OR "призыв" OR "контракт" OR "осужденные" OR "ФСИН" OR "военная служба")'),
("Совет Федерации",'site:council.gov.ru ("мобилизация" OR "призыв" OR "контракт" OR "осужденные" OR "ФСИН" OR "военная служба")'),
("ТАСС",'site:tass.ru ("мобилизация" OR "призыв" OR "контракт" OR "осужденные" OR "ФСИН" OR "военная служба")'),
("РИА Новости",'site:ria.ru ("мобилизация" OR "призыв" OR "контракт" OR "осужденные" OR "ФСИН" OR "военная служба")'),
("Северная Осетия",'site:fsin.gov.ru "УФСИН" "Северная Осетия — Алания"'),
("Северная Осетия СМИ",'"Северная Осетия — Алания" колония мобилизация'),
("Северная Осетия Telegram",'site:t.me "Северная Осетия — Алания"'),
("Дагестан",'site:fsin.gov.ru "УФСИН" "Дагестан"'),
("Москва",'site:fsin.gov.ru "УФСИН" "Москва"'),
("Краснодарский край",'site:fsin.gov.ru "УФСИН" "Краснодарский край"'),
]

def exa(q):
    key=os.environ["EXA_API_KEY"]
    t=time.perf_counter()
    r=requests.post("https://api.exa.ai/search",headers={"x-api-key":key,"Content-Type":"application/json"},
        json={"query":q,"type":"auto","numResults":10,"contents":{"highlights":{"maxCharacters":1200}}},timeout=60)
    ms=round((time.perf_counter()-t)*1000)
    r.raise_for_status()
    data=r.json()
    items=data.get("results",[]) or []
    return ms,[{"url":x.get("url",""),"title":x.get("title",""),"snippet":" ".join(x.get("highlights",[]) or [])[:1200],
                 "publishedDate":x.get("publishedDate"),"author":x.get("author")} for x in items]

def firecrawl(q):
    key=os.environ["FIRECRAWL_API_KEY"]
    t=time.perf_counter()
    r=requests.post("https://api.firecrawl.dev/v1/search",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
        json={"q":q,"limit":10,"country":"ru","lang":"ru","scrapeOptions":{"formats":["markdown"]}},timeout=90)
    ms=round((time.perf_counter()-t)*1000)
    r.raise_for_status()
    data=r.json()
    items=(data.get("data") or data.get("web") or [])
    if isinstance(items,dict): items=items.get("web") or items.get("results") or []
    return ms,[{"url":x.get("url",""),"title":x.get("title",""),"snippet":x.get("description","") or x.get("markdown","")[:1200],
                 "publishedDate":(x.get("metadata") or {}).get("publishedDate"),"author":(x.get("metadata") or {}).get("author")} for x in items]

def metrics(items):
    urls=[x["url"] for x in items if x.get("url")]
    unique=list(dict.fromkeys(urls))
    domains=[]
    from urllib.parse import urlparse
    for u in unique:
        h=urlparse(u).netloc.lower().removeprefix("www.")
        if h and h not in domains: domains.append(h)
    gov=sum(".gov.ru" in u.lower() for u in unique)
    rich=sum(bool(x.get("snippet")) for x in items)
    dated=sum(bool(x.get("publishedDate")) for x in items)
    return {"results":len(items),"unique_urls":len(unique),"unique_domains":len(domains),"gov_urls":gov,
            "nonempty_snippets":rich,"published_dates":dated,"domains":domains[:20]}

out={"queries":{},"meta":{"query_count":len(QUERIES),"limit":10}}
for label,q in QUERIES:
    row={"query":q}
    for name,fn in (("exa",exa),("firecrawl",firecrawl)):
        try:
            ms,items=fn(q)
            row[name]={"latency_ms":ms,"metrics":metrics(items),"items":items}
        except Exception as e:
            row[name]={"error":f"{type(e).__name__}: {e}"}
    out["queries"][label]=row
Path("/tmp/firecrawl_vs_exa.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")

# Compact summary for workflow logs
for label,row in out["queries"].items():
    print(label)
    for name in ("exa","firecrawl"):
        x=row.get(name,{})
        print(name, "ERROR" if "error" in x else x["metrics"], "latency_ms=", x.get("latency_ms"))
