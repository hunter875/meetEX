from __future__ import annotations
import argparse,json,os,platform,statistics,sys,tempfile,time
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'backend'))
from app.storage import Storage
from app.ingestion import Ingestion
from app.retrieval import Retrieval,Semantic
from app.config import E5_MODEL,E5_REVISION
parser=argparse.ArgumentParser();parser.add_argument('--semantic',action='store_true');args=parser.parse_args()
corpus=json.loads((root/'fixtures/demo-project.json').read_text('utf8'))
with tempfile.TemporaryDirectory(prefix='meet-benchmark-') as tmp:
    store=Storage(Path(tmp));semantic=Semantic(root/'.local/models')
    if args.semantic:semantic.load();store.set_settings({'semantic_enabled':True})
    p=store.create_project({k:corpus[k] for k in ('name','description','glossary')});mapping={}
    for source in corpus['sources']:
        s=Ingestion(store,semantic).add(p['id'],{k:v for k,v in source.items() if k!='key'});job=Ingestion(store,semantic).sync(s['id'])
        assert job['status']=='ready',job;mapping[source['key']]=s['id']
    retrieval=Retrieval(store,semantic);rows=[];durations=[]
    for case in corpus['queries']:
        result=retrieval.search(p['id'],case['query'])
        expected=mapping[case['expected_source_key']]
        rows.append(dict(**case,expected_source_id=expected,hit_top5=expected in [r['source_id'] for r in result['results']],actual_source_ids=[r['source_id'] for r in result['results']],actual_titles=[r['title'] for r in result['results']],mode=result['mode']))
    for _ in range(30):
        for case in corpus['queries']:durations.append(retrieval.search(p['id'],case['query'])['duration_ms'])
    durations.sort();report=dict(mode='hybrid' if args.semantic else 'keyword',corpus='fixtures/demo-project.json',source_count=len(corpus['sources']),chunk_count=store.disk.execute('SELECT count(*) FROM chunks').fetchone()[0],machine=platform.platform(),python=platform.python_version(),cpu=platform.processor(),logical_cpus=os.cpu_count(),model=E5_MODEL if args.semantic else None,model_revision=E5_REVISION if args.semantic else None,n=len(durations),median_ms=statistics.median(durations),p95_ms=durations[int(.95*(len(durations)-1))],hit_top5=sum(r['hit_top5'] for r in rows),query_count=len(rows),queries=rows,note='Small synthetic corpus benchmark, not general accuracy or an SLA.')
    destination=root/'docs/evidence'/('retrieval-hybrid.json' if args.semantic else 'retrieval-keyword.json');destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='queries'},ensure_ascii=False));store.close()
    if report['hit_top5']<8:raise SystemExit('Retrieval fixture target failed')
