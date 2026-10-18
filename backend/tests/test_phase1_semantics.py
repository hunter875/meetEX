"""Regression oracles for supported claims, not a general meeting accuracy metric."""
import json
from pathlib import Path

import pytest
from app.errors import AppError
from app.llm import validate_report, validate_suggestion
from app.models import ReportPayload, SuggestionPayload
from .semantic_cases import CASES, exercise

ROOT = Path(__file__).resolve().parents[2]
PROBES = json.loads((ROOT/'docs/evidence/system-assessment-probes.json').read_text('utf-8'))['probes']

@pytest.mark.parametrize('probe', PROBES, ids=[p['name'] for p in PROBES])
def test_original_false_claim_is_rejected(probe):
    with pytest.raises(AppError):
        if 'snapshot' in probe:
            validate_suggestion(SuggestionPayload(**probe['payload']), probe['snapshot'])
        else:
            validate_report(ReportPayload(**probe['payload']), probe['segments'])

@pytest.mark.parametrize('case', CASES, ids=[c['name'] for c in CASES])
def test_semantic_variants_and_positive_controls(case):
    if case['accept']:
        exercise(case)
    else:
        with pytest.raises(AppError):
            exercise(case)

def test_ai_proposals_are_separate_from_confirmed_facts():
    segments=[dict(id='s',text='Timeout is 15 seconds.')]
    item=dict(id='p',text='We propose trying a timeout of 30 seconds.',origin='ai_proposal',confirmation='proposed',evidence_segment_ids=[])
    validate_report(ReportPayload(ai_proposals=[item]),segments)
    for patch in ({'confirmation':'confirmed'},{'owner':'Minh'},{'raw_due_text':'Friday'}):
        with pytest.raises(AppError):
            validate_report(ReportPayload(ai_proposals=[{**item,**patch}]),segments)
