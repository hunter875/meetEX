"""Offline bilingual routing fixture evaluation. No credentials or provider calls."""
import hashlib
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.routing import classify

def snapshot(case):
    segments = [dict(id=f'p{i}', speaker=p, text='Earlier participant turn.', stable=True)
                for i, p in enumerate(case.get('participants', []))]
    segments.append(dict(id='s1', speaker=case.get('speaker', 'Client'),
                         text=case['text'], stable=case.get('stable', True)))
    return dict(action=case.get('action', 'suggest'), question=case.get('question', ''),
                self_speaker='Minh', segments=segments, sources=case.get('sources', []))

def main():
    fixture=ROOT/'fixtures/routing-scenarios.json'
    cases=json.loads(fixture.read_text('utf-8'))
    results=[]
    for case in cases:
        decision=classify(snapshot(case),case.get('response_mode','auto'))
        passed=decision['route']==case['expected'] and (not case.get('verification') or decision['requires_verification'])
        results.append(dict(name=case['name'],expected=case['expected'],passed=passed,decision=decision))
    # Warm local rule timing only; excludes retrieval, API, debounce, provider and UI.
    timings=[classify(snapshot(cases[i%len(cases)]))['classifier_ms'] for i in range(1000)]
    timings.sort()
    result=dict(created_at=datetime.now(timezone.utc).isoformat(),mode='local rules, synthetic fixtures, no provider',
                hash_format='utf8-lf',
                classifier_sha256=hashlib.sha256((ROOT/'backend/app/routing.py').read_text('utf-8').encode('utf-8')).hexdigest(),
                fixture_sha256=hashlib.sha256(fixture.read_text('utf-8').encode('utf-8')).hexdigest(),
                passed=sum(r['passed'] for r in results),total=len(results),cases=results,
                timing=dict(n=len(timings),median_ms=statistics.median(timings),p95_ms=timings[949],max_ms=max(timings)),
                limitation='Fixture coverage is not general classification accuracy; time targets are unbenchmarked product goals.')
    (ROOT/'docs/evidence/routing-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('passed','total','timing','limitation')}))
    return 0 if all(r['passed'] for r in results) else 1

if __name__=='__main__':raise SystemExit(main())
