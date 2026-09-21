# Full text vs Exa snippet — RiskWatch benchmark

Date: 2026-09-21

## Dataset

15 unique URLs from three real RiskWatch Exa queries:
- prisoner mobilization / FSIN North Ossetia-Alania
- military commissariat North Ossetia-Alania / prisoners
- FSIN North Ossetia-Alania / Ministry of Defence / military registration

Firecrawl processed 15/15 URLs successfully in this run. Credits used: 15.

## Exact RiskWatch semantic functions

The comparison uses the existing production predicates from `forecast.py`:
- `_has_target()`
- `_has_direct_military_action()`
- `build_evidence_graph()`

No production code was changed.

## Results

| Metric | Exa snippet | Firecrawl full text |
|---|---:|---:|
| events | 15 | 15 |
| target_events | 9 | 10 |
| direct_action_events / root_events | 1 | 0 |
| evidence graph nodes | 9 | 10 |
| graph root nodes | 1 | 0 |
| source families | 9 | 10 |

Uplift:
- target: +1
- direct action/root: -1
- graph nodes: +1
- graph root nodes: -1

The single lost root event was:
`https://161.ru/text/world/2022/09/29/71694857/`

The cause is not lack of content. The full page introduces a negative/negation marker somewhere in the long text, so the current global `_is_negative()` check makes the whole event negative. The short Exa snippet does not contain that negative marker, so the same source remains a root event under the current predicate.

The single new target positive came from:
`https://xfirm.ru/company/1504033832`

This is a directory/company-profile page. It demonstrates the main risk of applying full-page text directly: additional text can increase lexical matches without necessarily increasing scenario evidence.

## Interpretation

The hypothesis "more text automatically produces more useful RiskWatch events" is false.

The full text produced more target coverage (+1) but reduced direct-action/root detection (-1) because the current predicates operate over the entire event text and treat a negative marker anywhere in that text as a negative signal.

Therefore Firecrawl remains valuable, but it should NOT be inserted as:

Exa snippet -> replace snippet with entire page -> existing predicates.

The correct next engineering step is a controlled semantic extraction layer between Firecrawl and the existing predicates:

Exa candidate
-> Firecrawl full text
-> extract relevant evidence passages / claims
-> construct a compact event snippet
-> existing RiskWatch predicates
-> evidence graph

This preserves Firecrawl's recall benefit while preventing page-wide navigation, disclaimers, unrelated sections, or contradictory passages from poisoning the event-level negative check.

Status: A/B benchmark complete. Production integration remains blocked until this normalization step is tested.
