"""Offline phase-1 probes; counts false accepts/rejects separately. Never calls AI."""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
from app.errors import AppError
from app.evidence import VALIDATION_POLICY
from app.llm import validate_report, validate_suggestion
from app.models import ReportPayload, SuggestionPayload
from tests.semantic_cases import CASES, exercise


def git(*args):
    try:return subprocess.check_output(['git',*args],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):
        metadata=json.loads((ROOT/'BUILD_SOURCE.json').read_text('utf8'))
        if args==('branch','--show-current'):return 'source-archive'
        if args==('rev-parse','HEAD'):return metadata['source_commit']
        raise


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='docs/evidence/phase1/semantic-review.json')
    parser.add_argument('--base-commit',default='cd6b79f876a6d3e00f26801dacfebb10bb87cbfb')
    parser.add_argument('--starting-branch',default='main')
    args=parser.parse_args()
    results=[]
    for case in CASES:
        error=None
        try:
            exercise(case)
            accepted=True
        except AppError as failure:
            accepted=False
            error=failure.code
        results.append(dict(name=case['name'],group=case['group'],expected_accept=case['accept'],
                            accepted=accepted,error=error,passed=accepted==case['accept']))
    groups={}
    for group in sorted({case['group'] for case in CASES}):
        rows=[row for row in results if row['group']==group]
        groups[group]=dict(
            valid_cases=sum(row['expected_accept'] for row in rows),
            invalid_cases=sum(not row['expected_accept'] for row in rows),
            false_accepts=sum(row['accepted'] and not row['expected_accept'] for row in rows),
            false_rejects=sum(not row['accepted'] and row['expected_accept'] for row in rows))
    probes=[]
    historical=json.loads((ROOT/'docs/evidence/system-assessment-probes.json').read_text('utf-8'))
    for probe in historical['probes']:
        code=None
        try:
            if 'snapshot' in probe:
                validate_suggestion(SuggestionPayload(**probe['payload']),probe['snapshot'])
            else:
                validate_report(ReportPayload(**probe['payload']),probe['segments'])
        except AppError as failure:
            code=failure.code
        probes.append(dict(name=probe['name'],blocked=code is not None,error=code))
    paths=['backend/app/storage.py','backend/app/evidence.py','backend/app/llm.py',
           'backend/app/service.py','fixtures/phase1-semantic-cases.json']
    record=dict(
        created_at=datetime.now(timezone.utc).isoformat(),client_timezone='America/Los_Angeles',
        base_commit=args.base_commit,starting_branch=args.starting_branch,starting_working_tree='clean',
        branch=git('branch','--show-current'),head_at_evaluation=git('rev-parse','HEAD'),
        environment=dict(platform=platform.platform(),python=sys.version,executable=sys.executable),
        command=f'.venv/Scripts/python.exe scripts/evaluate_phase1.py --output {args.output} --base-commit {args.base_commit} --starting-branch {args.starting_branch}',
        mode='Offline deterministic validation, synthetic evidence, no provider or real meeting',
        validation_policy=VALIDATION_POLICY,hash_format='utf8-lf',
        source_hashes={path:hashlib.sha256((ROOT/path).read_text('utf-8').encode('utf-8')).hexdigest() for path in paths},
        groups=groups,cases=results,original_probes=probes,
        result='PASS' if all(row['passed'] for row in results) and all(row['blocked'] for row in probes) else 'FAIL',
        limitations='Fixture false accepts/rejects are not real-meeting accuracy. Bounded aliases and grammar; no general semantic entailment or real provider latency claim.')
    output=ROOT/args.output
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:record[key] for key in ('groups','original_probes','result')},ensure_ascii=False))
    return 0 if record['result']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
