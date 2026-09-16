import inspect
from dataclasses import replace


def _fake_store():
    class FakeStore:
        def __init__(self):
            self.saved = []
        def get_meta(self, key, default=0):
            return 0
        def set_meta(self, key, value):
            pass
        def recent(self, limit=3000):
            return []
        def add_events(self, events):
            return 0
        def forecasts(self):
            return []
        def replace_forecasts(self, records):
            pass
        def ai_due(self):
            return False
        def last_decision(self):
            return None
        def mark_ai_attempt(self):
            pass
        def save_decision(self, decision):
            self.saved.append(decision)
        def save_forecast(self, forecast):
            pass
    return FakeStore


def test_build_forecast_called_exactly_once_in_no_evidence_run(monkeypatch):
    import riskwatch.runner as runner
    calls = []
    monkeypatch.setattr(runner, 'Store', _fake_store())
    monkeypatch.setattr(runner, '_queries_from_cursor', lambda cursor: ([('Federal', 'q')], 0, False))
    monkeypatch.setattr(runner, '_collect_one', lambda item: ([], False))
    monkeypatch.setattr(runner, 'build_evidence_graph', lambda events: {'nodes': []})
    monkeypatch.setattr(runner, 'compact_chain', lambda graph: {'metrics': {}})
    monkeypatch.setattr(runner, 'calibration_summary', lambda records: {})
    monkeypatch.setattr(runner, 'build_forecast', lambda events: calls.append(list(events)) or {'pattern_stage': 0, 'structure_score': 8, 'evidence_score': 0, 'next_event_horizon': '7-30d'})
    runner.run()
    assert len(calls) == 1


def test_stage_invariant_blocks_operational_stage_without_action():
    from riskwatch.forecast import build_forecast
    event = {'url': 'https://fsin.gov.ru/a', 'title': 'осужденный переведен', 'snippet': ''}
    f = build_forecast([event])
    assert f['evidence_metrics']['action_events'] == 0
    assert f['pattern_stage'] <= 1


def test_pattern_structure_score_equals_runner_signals(monkeypatch):
    import riskwatch.runner as runner
    class FakeStore:
        def get_meta(self, key, default=0): return 0
        def set_meta(self, key, value): pass
        def recent(self, limit=3000): return [{'url': 'https://fsin.gov.ru/a', 'title': 'ФСИН порядок для заключенных', 'snippet': 'порядок'}]
        def add_events(self, events): return 0
        def forecasts(self): return []
        def replace_forecasts(self, records): pass
        def ai_due(self): return True
        def mark_ai_attempt(self): pass
        def last_decision(self, decision=None): return None
        def save_decision(self, decision): self.decision = decision
        def save_forecast(self, forecast): pass
    store = FakeStore()
    monkeypatch.setattr(runner, 'Store', lambda: store)
    monkeypatch.setattr(runner, '_queries_from_cursor', lambda cursor: ([('Federal', 'q')], 0, False))
    event = {'url': 'https://fsin.gov.ru/a', 'title': 'ФСИН порядок для заключенных', 'snippet': 'порядок'}
    monkeypatch.setattr(runner, '_collect_one', lambda item: ([dict(event)], False))
    monkeypatch.setattr(runner, 'build_evidence_graph', lambda events: {'nodes': {'x': {}}})
    monkeypatch.setattr(runner, 'compact_chain', lambda graph: {'metrics': {}})
    monkeypatch.setattr(runner, 'calibration_summary', lambda records: {})
    monkeypatch.setattr(runner, 'calibrate_probability', lambda p, records, horizon=None: {'probability': None, 'status': 'insufficient_history'})
    monkeypatch.setattr(runner, 'render_context', lambda pattern, calibration: 'x')
    monkeypatch.setattr(runner, '_episode_duplicate', lambda *args: True)
    monkeypatch.setattr(runner, 'analyze', lambda events, forecast, graph: {'analysis_provider': 'fallback', 'probability': 0, 'risk': 0, 'confidence': 0, 'scenario_answer': 'UNKNOWN', 'reason': 'gate'})
    monkeypatch.setattr(runner, 'build_forecast', lambda events: {'pattern_stage': 1, 'structure_score': 16, 'evidence_score': 0, 'next_event_horizon': '7-30d', 'next_stage': 'administrative_preparation', 'evidence_metrics': {'action_events': 0}})
    decision = runner.run()
    assert decision['pattern']['structure_score'] == 16
    assert 'structure_score=16' in decision['signals']


def test_ai_called_retains_usage_on_gate_rejection(monkeypatch):
    import riskwatch.ai as ai
    class Response:
        def json(self):
            return {'usage': {'input_tokens': 12, 'output_tokens': 8, 'total_tokens': 20}, 'output_text': '{"probability":90,"confidence":90,"risk":90,"facts":[],"inferences":[],"scenario_answer":"YES"}'}
        def raise_for_status(self): pass
    monkeypatch.setattr(ai, 'SETTINGS', replace(ai.SETTINGS, openai_api_key='test-key'))
    monkeypatch.setattr(ai.requests, 'post', lambda *args, **kwargs: Response())
    events = [{'url': 'https://fsin.gov.ru/a', 'title': 'ФСИН порядок для заключенных', 'snippet': 'порядок'}]
    forecast = {'pattern_stage': 1, 'structure_score': 16}
    result = ai.analyze(events, forecast, {'nodes': []})
    assert result['analysis_provider'] == 'fallback'
    assert result['reason'] == 'AI claims failed semantic evidence gate; rejected'
    assert result['usage']['total_tokens'] == 20
    assert 'build_forecast' not in inspect.getsource(ai)


def test_valid_unknown_passes_gate_and_is_analytically_ok():
    import riskwatch.ai as ai
    import riskwatch.runner as runner
    event = {'url': 'https://fsin.gov.ru/a', 'title': 'ФСИН порядок для заключенных', 'snippet': 'порядок'}
    result = ai._validate({'verdict': 'undetermined', 'facts': [], 'inferences': []}, [event], {'pattern_stage': 0, 'structure_score': 8})
    assert result['hallucination_guard'] == 'passed_evidence_gate_valid_unknown'
    assert result['analysis_provider'] == 'openai'
    assert result['scenario_answer'] == 'UNKNOWN'
    assert result['probability'] is None
    assert result['confidence'] == 0
    assert runner._analytical_status(result) == 'OK'


def test_indeterminate_passes_gate_and_is_analytically_ok():
    import riskwatch.ai as ai
    import riskwatch.runner as runner
    event = {'url': 'https://fsin.gov.ru/a', 'title': 'ФСИН порядок для заключенных', 'snippet': 'порядок'}
    result = ai._validate({'verdict': 'indeterminate', 'facts': [], 'inferences': []}, [event], {'pattern_stage': 0, 'structure_score': 8})
    assert result['hallucination_guard'] == 'passed_evidence_gate_valid_unknown'
    assert result['analysis_provider'] == 'openai'
    assert result['scenario_answer'] == 'UNKNOWN'
    assert result['probability'] is None
    assert result['confidence'] == 0
    assert runner._analytical_status(result) == 'OK'
