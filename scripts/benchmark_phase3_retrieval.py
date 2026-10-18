"""Reproducible scaling/concurrency benchmark; controlled vectors, optional real E5."""
import argparse,asyncio,json,math,platform,statistics,sys,tempfile,time,tracemalloc
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.storage import Storage,uid,now,dumps
from app.retrieval import Retrieval,Semantic
from app.config import E5_MODEL,E5_REVISION
import numpy as np

def summary(values):
    values=sorted(values);return dict(n=len(values),median_ms=statistics.median(values),p95_ms=values[math.ceil(.95*len(values))-1],max_ms=max(values))
class ControlledSemantic:
    ready=True
    def query(self,text):
        vector=np.zeros(384,dtype=np.float32);vector[int(text.split('-')[-1])%384]=1
        return vector.tolist()

async def run(output,real_e5):
    rows=[]
    with tempfile.TemporaryDirectory(prefix='meet-retrieval-phase3-') as tmp:
      for size in (100,1000,10000):
        store=Storage(Path(tmp)/str(size));p=store.create_project(dict(name='Scope A',description='',glossary={}))
        other=store.create_project(dict(name='Scope B',description='',glossary={}))
        source=uid();meta=dict(title='Synthetic scaling',kind='text',path='synthetic',line_start=1,line_end=1,indexed_at=now(),content_hash='fixture')
        with store.disk:
            store.disk.execute('INSERT INTO sources VALUES(?,?,?)',(source,p['id'],dumps(dict(id=source,project_id=p['id'],generation=1,stale=False,**meta))))
            for n in range(size):
                vector=np.zeros(384,dtype=np.float32);vector[n%384]=1
                store.disk.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?,?)',(f'chunk-{n}',source,p['id'],1,f'API-{n} timeout configuration; the cache is a separate property.',dumps(meta),json.dumps(vector.tolist())))
        for hybrid in (False,True):
            store.set_settings({'semantic_enabled':hybrid});retrieval=Retrieval(store,ControlledSemantic());durations=[];hits=0;cache_hits=0;misses=[];queries=[f'API-{n}' for n in (1,size//2,size-1)]
            tracemalloc.start();cold=None
            for repeat in range(4):
                for query in queries:
                    began=time.perf_counter()
                    result=await retrieval.search_async(p['id'],query) if hasattr(retrieval,'search_async') else retrieval.search(p['id'],query)
                    elapsed=(time.perf_counter()-began)*1000
                    if cold is None:cold=elapsed
                    else:durations.append(elapsed)
                    cache_hits+=bool(result.get('cache_hit'))
                    if not result.get('cache_hit'):misses.append(elapsed)
                    expected='chunk-'+query.split('-')[-1];hits+=expected in [r['id'] for r in result['results']]
                    assert all(r['project_id']==p['id'] for r in result['results'])
            _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            # Heartbeat loop latency while a cold retrieval executes in the same event loop.
            gaps=[];done=False
            async def ping():
                last=time.perf_counter()
                while not done:
                    await asyncio.sleep(.001);current=time.perf_counter();gaps.append((current-last)*1000);last=current
            task=asyncio.create_task(ping());await asyncio.sleep(.002)
            if hasattr(retrieval,'search_async'):await retrieval.search_async(p['id'],f'API-{size-2}')
            else:retrieval.search(p['id'],f'API-{size-2}')
            await asyncio.sleep(.002);done=True;await task
            rows.append(dict(chunks=size,mode='hybrid-controlled-vectors' if hybrid else 'keyword',cold_ms=cold,warm=summary(durations),uncached=summary(misses),cache_hits=cache_hits,python_peak_bytes=peak,query_n=12,hit_top5=hits,event_loop_tick=summary(gaps),scope_violations=0))
            if hasattr(retrieval,'aclose'):await retrieval.aclose()
        store.close()
      if real_e5:
        from app.ingestion import Ingestion
        store=Storage(Path(tmp)/'e5');semantic=Semantic(ROOT/'.local/models');began=time.perf_counter();await asyncio.to_thread(semantic.load);load_ms=(time.perf_counter()-began)*1000
        store.set_settings({'semantic_enabled':True});corpus=json.loads((ROOT/'fixtures/demo-project.json').read_text('utf-8'));p=store.create_project({k:corpus[k] for k in ('name','description','glossary')});mapping={}
        for source in corpus['sources']:
            s=Ingestion(store,semantic).add(p['id'],{k:v for k,v in source.items() if k!='key'});job=Ingestion(store,semantic).sync(s['id']);assert job['status']=='ready';mapping[source['key']]=s['id']
        retrieval=Retrieval(store,semantic);durations=[];hits=0
        for case in corpus['queries']:
            began=time.perf_counter();result=await retrieval.search_async(p['id'],case['query']) if hasattr(retrieval,'search_async') else retrieval.search(p['id'],case['query']);durations.append((time.perf_counter()-began)*1000);hits+=mapping[case['expected_source_key']] in [r['source_id'] for r in result['results']]
        rows.append(dict(mode='real-E5-hybrid-CPU',model=E5_MODEL,revision=E5_REVISION,load_ms=load_ms,queries=len(durations),hit_top5=hits,timing=summary(durations),corpus='fixtures/demo-project.json'))
        if hasattr(retrieval,'aclose'):await retrieval.aclose()
        store.close()
    record=dict(platform=platform.platform(),provenance='Synthetic SQL chunks and controlled orthogonal 384-D vectors for 100/1000/10000 scaling; optional separately labelled genuine E5 on existing demo corpus',real_provider_calls=0,rows=rows,limitations='Controlled-vector ranking is a scaling fixture, not semantic accuracy. Python tracemalloc excludes native/model RSS. Timing samples are small and include cache hits; cold and warm separated.')
    (ROOT/output).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');print(json.dumps(rows))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--real-e5',action='store_true');args=parser.parse_args();asyncio.run(run(args.output,args.real_e5))
