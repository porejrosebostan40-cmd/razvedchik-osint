import json
from riskwatch.ai import analyze_region_web_search

REGION = "Северная Осетия — Алания"

result = analyze_region_web_search(REGION)

print("=== WEB SEARCH ANALYZE TEST ===")
print(f"region={REGION}")
print(f"scenario_answer={result.get('scenario_answer')}")
print(f"probability={result.get('probability')}")
print(f"confidence={result.get('confidence')}")
print(f"risk={result.get('risk')}")
print(f"analysis_provider={result.get('analysis_provider')}")
print(f"web_search_call={result.get('web_search_call')}")
print(f"citations={len(result.get('citations') or [])}")
print(f"reason={result.get('reason')}")
print("=== RESULT JSON ===")
print(json.dumps(result, ensure_ascii=False, indent=2))
