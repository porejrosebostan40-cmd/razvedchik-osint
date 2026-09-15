import json
from .runner import run

REPORT_KEYS = (
    'scenario_question', 'scenario_answer', 'probability', 'model_probability',
    'probability_calibration', 'risk', 'model_risk', 'confidence',
    'analysis_provider', 'reason', 'signals', 'missing_indicators',
    'next_event', 'horizon', 'pattern', 'calibration', 'forecast_basis'
)


def main():
    decision = run()
    report = {k: decision.get(k) for k in REPORT_KEYS if k in decision}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
