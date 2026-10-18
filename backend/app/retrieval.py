from __future__ import annotations
import json
import re
import time
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
    def __init__(self,store,semantic):self.store=store;self.semantic=semantic;self.timings=[]
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
            candidates=list(db.execute('SELECT * FROM chunks WHERE project_id=? AND vector IS NOT NULL',(project_id,)))
            candidates.sort(key=lambda r:float(np.dot(q,json.loads(r['vector']))),reverse=True)
            for n,r in enumerate(candidates[:40],1):
                all_rows[r['id']]=dict(r);rank[r['id']]=rank.get(r['id'],0)+1/(60+n)
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
