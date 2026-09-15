import json
from .runner import run

REPORT_KEYS = (
    'scenario_question', 'scenario_answer', 'probability', 'model_probability',
    'probability_calibration', 'risk', 'model_risk', 'confidence',
    'analysis_provider', 'reason', 'signals', 'missing_indicators',
    'next_event', 'horizon', 'pattern', 'calibration', 'evidence_chain', 'forecast_basis'
)
PATTERN_KEYS = (
    'scenario_id', 'pattern_stage', 'pattern_stage_name', 'observed_stages',
    'next_stage', 'next_event_horizon', 'independent_domains', 'source_families',
    'regions_with_signals', 'negative_indicators', 'acceleration', 'structure_score',
    'evidence_score', 'evidence_metrics', 'interpretation', 'evidence_chain'
)


def _compact_pattern(pattern):
    if not isinstance(pattern, dict):
        return {}
    return {k: pattern[k] for k in PATTERN_KEYS if k in pattern}


def main():
    decision = run()
    report = {k: decision.get(k) for k in REPORT_KEYS if k in decision}
    if 'pattern' in report:
        report['pattern'] = _compact_pattern(report['pattern'])
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
