import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.storage import uid,dumps
from app.retrieval import Retrieval,Semantic
from pathlib import Path
from .conftest import caption
from .test_phase2_capture import receive

def seed(store,project):
    sid=uid();meta=dict(id=sid,project_id=project['id'],generation=1,stale=False,title='Fixture',kind='text',path='fixture',line_start=1,line_end=1,indexed_at='2026-10-18T00:00:00Z',content_hash='fixture')
    with store.disk:
        store.disk.execute('INSERT INTO sources VALUES(?,?,?)',(sid,project['id'],dumps(meta)))
        store.disk.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?,?)',('chunk',sid,project['id'],1,'API-17 timeout is 15 seconds.',dumps(meta),json.dumps([1.,0.])))
    return sid,meta

async def test_async_cache_project_generation_and_own_thread_connection(store,project):
    sid,meta=seed(store,project);retrieval=Retrieval(store,Semantic(Path('.')))
    a=await retrieval.search_async(project['id'],'API-17');b=await retrieval.search_async(project['id'],'API-17');assert b['cache_hit'] and a['results']==b['results']
    other=store.create_project(dict(name='Other',description='',glossary={}))
    assert not (await retrieval.search_async(other['id'],'API-17'))['results']
    meta['generation']=2
    with store.disk:
        store.disk.execute('UPDATE sources SET payload=? WHERE id=?',(dumps(meta),sid));store.disk.execute('DELETE FROM chunks WHERE id=?',('chunk',));store.disk.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?,?)',('new',sid,project['id'],2,'API-17 timeout is 50 seconds.',dumps(meta),None))
    fresh=await retrieval.search_async(project['id'],'API-17');assert fresh['results'][0]['generation']==2 and '50' in fresh['results'][0]['content'];await retrieval.aclose()

def test_actual_websocket_ack_continues_during_slow_semantic_query(client):
    store=client.app.state.store;p=store.create_project(dict(name='Async',description='',glossary={}));sid,meta=seed(store,p)
    store.set_settings({'semantic_enabled':True});started=threading.Event();release=threading.Event();thread_ids=[]
    class SlowSemantic:
        ready=True
        def query(self,text):thread_ids.append(threading.get_ident());started.set();release.wait(2);return [1.,0.]
    client.app.state.retrieval.semantic=SlowSemantic()
    m=client.post('/api/v1/meetings',json=dict(project_id=p['id'],title='Concurrency',meeting_key='/async')).json()
    with client.websocket_connect('/api/v1/events',headers={'Host':'127.0.0.1:8765','Origin':'chrome-extension://'+'a'*32}) as ws:
        ws.send_json(dict(type='auth',protocol_version=1,token='test-pairing-token'));receive(ws,'auth.ok')
        ws.send_json(dict(type='session.bind',protocol_version=1,session_id=m['id'],payload=dict(tab_id=1,document_id='doc',meeting_key='/async')));receive(ws,'session.snapshot')
        with ThreadPoolExecutor(max_workers=1) as caller:
            job=caller.submit(client.post,f'/api/v1/projects/{p["id"]}/search',json={'query':'API-17'})
            assert started.wait(2)
            e=caption('Caption during retrieval',segment='s');began=time.perf_counter();ws.send_json(dict(type='caption.upsert',protocol_version=1,session_id=m['id'],event_id=e['event_id'],payload=e))
            try:
                ack=receive(ws,'caption.ack');elapsed=time.perf_counter()-began
                assert ack['applied'] and elapsed<.5
                # Index publication while read transaction is active must not mix generations.
                meta['generation']=2
                with store.disk:
                    store.disk.execute('UPDATE sources SET payload=? WHERE id=?',(dumps(meta),sid));store.disk.execute('DELETE FROM chunks WHERE id=?',('chunk',));store.disk.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?,?)',('new',sid,p['id'],2,'API-17 timeout is 50 seconds.',dumps(meta),json.dumps([1.,0.])))
            finally:release.set()
            result=job.result(timeout=3);assert result.status_code==200
            data=result.json();assert data['index_generation']=={sid:1} and data['results'][0]['generation']==1
        fresh=client.post(f'/api/v1/projects/{p["id"]}/search',json={'query':'API-17'}).json();assert fresh['index_generation']=={sid:2} and fresh['results'][0]['generation']==2
        snapshot=client.get('/api/v1/meetings/'+m['id']).json();assert snapshot['segments'][0]['text']=='Caption during retrieval'
