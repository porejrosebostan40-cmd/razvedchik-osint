# Firecrawl vs Exa benchmark — manual run

Date: 2026-09-21

## Scope

RiskWatch prisoner-mobilization retrieval. Firecrawl was tested as a second-stage page extractor on URLs returned by Exa, without changing production retrieval code.

## Batch 1 — mixed Exa results

10 URLs submitted to Firecrawl Batch Scrape.

- 8/10 scraped successfully: 80%.
- 2/10 failed.
- Both failures were DNS resolution errors:
  - etpfsin.ru
  - 15.fsin.gov.ru
- Credits used: 8.
- All 8 successful pages returned HTTP 200 and markdown.
- Markdown sizes: 5.4 KB–21.2 KB.
- Structured publication metadata was present on 5/8 pages.
- Structured author metadata was present on 2/8 pages.
- RiskWatch target-term match in full text: 8/8.
- RiskWatch action-term match in full text: 8/8.

## Batch 2 — fresh 2026 regional sources

7 URLs returned by Exa for current 2026 UFSIN/Russian North Ossetia queries.

- 7/7 scraped successfully: 100%.
- Credits used: 7.
- All 7 returned HTTP 200 and markdown.
- Markdown sizes: 6.3 KB–19.7 KB.
- Structured publication metadata was present on 2/7 pages.
- Structured author metadata was present on 2/7 pages.
- RiskWatch target-term match in full text: 7/7.
- RiskWatch action-term match in full text: 7/7.

## Combined

- 17 URLs submitted.
- 15 successful scrapes.
- 2 failures, both DNS-related.
- Success rate: 88.2%.
- Firecrawl credits used: 15.
- Successful pages consistently produced substantially more text than a search snippet and exposed page metadata when the source supplied it.

## Engineering conclusion

Firecrawl is effective as an enrichment layer after search, not as a replacement for Exa.

Recommended architecture remains:

Exa -> candidate discovery/ranking -> Firecrawl scrape -> full-text semantic extraction -> RiskWatch evidence graph.

Keep the existing legacy search path for explicit `site:` queries and as a fallback.

The benchmark does not justify replacing Exa with Firecrawl for discovery. It does justify using Firecrawl to recover evidence that is not present in short search snippets, especially on current regional pages.
