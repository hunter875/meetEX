from __future__ import annotations
import json
import re
import time
import asyncio
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from types import SimpleNamespace
from pathlib import Path
from .config import E5_MODEL,E5_REVISION
from .errors import AppError

class Semantic:
    def __init__(self,cache_dir):self.model=None;self.status='not_loaded';self.error=None;self.cache_dir=cache_dir
    @property
    def ready(self):return self.model is not None
    def load(self):
        self.status='loading';self.error=None
        try:
            from sentence_transformers import SentenceTransformer
            self.model=SentenceTransformer(E5_MODEL,revision=E5_REVISION,device='cpu',cache_folder=str(self.cache_dir))
            self.status='ready'
        except Exception:
            self.model=None;self.status='unavailable';self.error='Install requirements-semantic.lock and check model download access. Keyword search remains available.'
            raise AppError('SEMANTIC_UNAVAILABLE',self.error,503)
    def split(self,text):
        tokenizer=self.model.tokenizer
        # Slice original text at tokenizer offsets, preserving exact source characters.
        tokens=tokenizer(text,add_special_tokens=False,return_offsets_mapping=True)
        offsets=tokens['offset_mapping'];parts=[]
        for n in range(0,len(offsets),380):
            span=offsets[n:n+410]
            if not span:continue
            piece=text[span[0][0]:span[-1][1]]
            if len(tokenizer('passage: '+piece,add_special_tokens=True)['input_ids'])>512:raise AppError('E5_TOKEN_LIMIT','Cannot safely fit passage in E5 tokenizer')
            parts.append(piece)
        return parts or [text]
    def embed_passage(self,text):
        if len(self.model.tokenizer('passage: '+text)['input_ids'])>512:raise AppError('E5_TOKEN_LIMIT','Passage exceeds 512 tokens')
        return self.model.encode('passage: '+text,normalize_embeddings=True).tolist()
    def query(self,text):
        if len(self.model.tokenizer('query: '+text)['input_ids'])>512:raise AppError('E5_QUERY_LIMIT','Shorten query to fit 512 E5 tokens')
        return self.model.encode('query: '+text,normalize_embeddings=True).tolist()

class Retrieval:
    def __init__(self,store,semantic):
        self.store=store;self.semantic=semantic;self.timings=[]
        self._executor=None;self._inflight={};self._cache=OrderedDict();self._vectors=OrderedDict();self._vector_lock=threading.RLock();self.cache_hits=0
    async def aclose(self):
        if self._executor:
            executor,self._executor=self._executor,None
            await asyncio.to_thread(executor.shutdown,wait=True,cancel_futures=True)
        self._cache.clear();self._vectors.clear()
    async def search_async(self,project_id,query,limit=5):
        began=time.perf_counter()
        # Read metadata on the owning loop. The worker owns a separate read-only SQLite connection.
        project=self.store.project(project_id);settings=self.store.settings()
        sources=self.store.sources(project_id)
        generation=tuple(sorted((s['id'],s['generation'],s.get('stale',False)) for s in sources))
        key=(project_id,query,limit,generation,json.dumps(project['glossary'],sort_keys=True),settings['semantic_enabled'],self.semantic.ready)
        if key in self._cache:
            self.cache_hits+=1;value=json.loads(json.dumps(self._cache[key]));value['cache_hit']=True;self._cache.move_to_end(key);value['worker_duration_ms']=value['duration_ms'];value['duration_ms']=(time.perf_counter()-began)*1000;self.timings.append(value['duration_ms']);self.timings=self.timings[-1000:];return value
        if key not in self._inflight:
            if len(self._inflight)>=8:raise AppError('RETRIEVAL_BUSY','Retrieval capacity reached; retry shortly',503,True)
            if self._executor is None:self._executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='meet-retrieval')
            path=self.store.disk.execute('PRAGMA database_list').fetchone()['file']
            def isolated():
                db=sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
                try:
                    db.execute('BEGIN')
                    source_rows={r['id']:json.loads(r['payload']) for r in db.execute('SELECT id,payload FROM sources WHERE project_id=?',(project_id,))}
                    current_project=dict(db.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone());current_project['glossary']=json.loads(current_project['glossary'])
                    view=SimpleNamespace(disk=db,project=lambda id:current_project,settings=lambda:settings,source=lambda id:source_rows[id])
                    worker=Retrieval(view,self.semantic);worker._vectors=self._vectors;worker._vector_lock=self._vector_lock
                    value=worker.search(project_id,query,limit);value['index_generation']={id:s['generation'] for id,s in source_rows.items()};return value
                finally:db.close()
            future=asyncio.get_running_loop().run_in_executor(self._executor,isolated)
            self._inflight[key]=future
            def completed(done):
                self._inflight.pop(key,None)
                if not done.cancelled() and done.exception() is None:
                    value=done.result()
                    if tuple(sorted(value['index_generation'].items()))==tuple(sorted((s['id'],s['generation']) for s in sources)):
                        self._cache[key]=value;self._cache.move_to_end(key)
                        while len(self._cache)>128:self._cache.popitem(last=False)
            future.add_done_callback(completed)
        result=json.loads(json.dumps(await asyncio.shield(self._inflight[key])));result['worker_duration_ms']=result['duration_ms'];result['duration_ms']=(time.perf_counter()-began)*1000;self.timings.append(result['duration_ms']);self.timings=self.timings[-1000:]
        return result
    def search(self,project_id,query,limit=5):
        began=time.perf_counter();project=self.store.project(project_id);expanded=query
        for word,meaning in project['glossary'].items():
            if word.casefold() in query.casefold():expanded+=' '+meaning
        terms=list(dict.fromkeys(re.findall(r'[\w]+',expanded,flags=re.UNICODE)))[:60]
        # Treat MATCH as an escaped list of terms, never user-supplied SQL/FTS syntax.
        match=' OR '.join('"'+term.replace('"','""')+'"' for term in terms)
        db=self.store.disk
        rows=list(db.execute('SELECT c.*,bm25(chunks_fts) AS rank FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.id JOIN sources s ON s.id=c.source_id WHERE chunks_fts MATCH ? AND c.project_id=? ORDER BY rank LIMIT 40',(match,project_id))) if match else []
        ids=[r['id'] for r in rows];rank={id:1/(60+n) for n,id in enumerate(ids,1)}
        all_rows={r['id']:dict(r) for r in rows}
        mode='keyword';warning='Semantic chưa bật; câu Việt không khớp nguồn Anh có thể thiếu kết quả.'
        if self.store.settings()['semantic_enabled'] and self.semantic.ready:
            import numpy as np
            q=np.array(self.semantic.query(expanded))
            generations=tuple((r['source_id'],r['generation'],r['n']) for r in db.execute('SELECT source_id,generation,count(*) n FROM chunks WHERE project_id=? AND vector IS NOT NULL GROUP BY source_id,generation ORDER BY source_id,generation',(project_id,)))
            vector_key=(project_id,generations)
            with self._vector_lock:
                cached=self._vectors.get(vector_key)
                if cached is None:
                    candidates=[];matrix=np.empty((sum(g[2] for g in generations),len(q)),dtype=np.float32)
                    for index,row in enumerate(db.execute('SELECT * FROM chunks WHERE project_id=? AND vector IS NOT NULL',(project_id,))):
                        candidate=dict(row);encoded=candidate.pop('vector')
                        # Index vectors are canonical numeric JSON arrays, written by ingestion.
                        # Parse directly into native memory instead of 384 Python float objects per row.
                        vector=np.fromstring(encoded.strip()[1:-1],sep=',',dtype=np.float32)
                        if len(vector)!=len(q) or not np.isfinite(vector).all():raise AppError('E5_VECTOR','Invalid indexed vector dimensions or values',503)
                        matrix[index]=vector;candidates.append(candidate)
                    cached=(candidates,matrix);self._vectors[vector_key]=cached
                    while len(self._vectors)>2:self._vectors.popitem(last=False)
                candidates,matrix=cached
                if candidates:
                    scores=matrix@q.astype(np.float32)
                    order=np.argsort(-scores,kind='stable')[:40]
                else:order=[]
                for n,index in enumerate(order,1):
                    r=candidates[int(index)];all_rows[r['id']]=r;rank[r['id']]=rank.get(r['id'],0)+1/(60+n)
            mode='hybrid';warning=None
        results=[]
        # Exact entity IDs get a boost without assuming their deployment status.
        entities=re.findall(r'\b[A-Za-z]+-\d+\b',query)
        for id in rank:
            rank[id]+=sum(.15 for entity in entities if entity.casefold() in all_rows[id]['content'].casefold())
        for id in sorted(rank,key=rank.get,reverse=True)[:limit]:
            r=all_rows[id];s=self.store.source(r['source_id']);meta=json.loads(r['metadata'])
            results.append({**meta,'id':id,'source_id':r['source_id'],'project_id':project_id,'generation':r['generation'],'content':r['content'],'score':rank[id],'stale':s['stale']})
        elapsed=(time.perf_counter()-began)*1000;self.timings.append(elapsed);self.timings=self.timings[-1000:]
        return dict(results=results,mode=mode,warning=warning,duration_ms=elapsed)
