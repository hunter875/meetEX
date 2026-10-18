from __future__ import annotations
import csv
import hashlib
import io
import json
import os
import re
from pathlib import Path
import pathspec
from .errors import AppError
from .storage import uid,now,dumps

FILE_LIMIT=2*1024*1024
UPLOAD_LIMIT=10*1024*1024
PROJECT_LIMIT=200*1024*1024
SKIP_DIRS={'.git','node_modules','.venv','venv','dist','build','target','__pycache__','.next','.local'}
TEXT_TYPES={'.md','.txt','.sql','.py','.ts','.tsx','.js','.jsx','.json','.csv','.yaml','.yml','.toml','.html','.css','.go','.rs','.java','.cs','.c','.cpp','.h','.sh','.ps1','.graphql','.prisma'}
SECRET_NAME=re.compile(r'(^\.env|id_rsa|id_ed25519|credentials|secrets?|\.pem$|\.key$|\.p12$|\.pfx$)',re.I)

def digest(text):return hashlib.sha256(text.encode('utf8')).hexdigest()
def read_text(path):
    if path.stat().st_size>FILE_LIMIT:raise AppError('FILE_TOO_LARGE','Text files are limited to 2 MiB')
    raw=path.read_bytes()
    if b'\0' in raw:raise AppError('BINARY_FILE','Binary input is excluded')
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:raise AppError('ENCODING','Use UTF-8 text input')
    if '-----BEGIN ' in text and 'PRIVATE KEY-----' in text:raise AppError('SECRET_FILE','Private key input is excluded')
    return text

def collect(body):
    files=[];skipped=[];errors=[];collected_bytes=0
    kind=body['kind'];locator=body.get('local_path')
    if kind=='repo':
        if not locator:raise AppError('PATH_REQUIRED','Choose an existing local repository folder')
        raw_root=Path(locator).expanduser()
        if not raw_root.is_absolute():raise AppError('PATH_REQUIRED','Use an absolute local path')
        root=raw_root.resolve(strict=True)
        if not root.is_dir() or root==Path(root.anchor):raise AppError('INVALID_ROOT','Choose a project folder, not a drive root')
        specs=[]
        def ignored(path,directory=False):
            decision=False
            for base,spec in specs:
                if not path.is_relative_to(base):continue
                relative=path.relative_to(base).as_posix()+('/' if directory else '')
                for pattern in spec.patterns:
                    if pattern.include is not None and pattern.match_file(relative):decision=bool(pattern.include)
            return decision
        for folder,dirs,names in os.walk(root,followlinks=False):
            current=Path(folder)
            ignore=current/'.gitignore'
            if ignore.exists() and ignore.resolve().is_relative_to(root) and not ignore.is_symlink():
                specs.append((current,pathspec.PathSpec.from_lines('gitwildmatch',read_text(ignore).splitlines())))
            kept=[]
            for d in dirs:
                candidate=current/d;reason=None
                if d in SKIP_DIRS or SECRET_NAME.search(d):reason='excluded_directory'
                elif candidate.is_symlink() or not candidate.resolve().is_relative_to(root):reason='outside_root_or_link'
                elif ignored(candidate,directory=True):reason='gitignore'
                if reason:skipped.append(dict(path=candidate.relative_to(root).as_posix(),reason=reason))
                else:kept.append(d)
            dirs[:]=kept
            for name in sorted(names):
                p=current/name;rel=p.relative_to(root).as_posix()
                reason=None
                if p.is_symlink() or not p.resolve().is_relative_to(root):reason='outside_root_or_link'
                elif SECRET_NAME.search(name):reason='secret_filename'
                elif p.suffix.lower() not in TEXT_TYPES:reason='unsupported_or_binary'
                elif ignored(p):reason='gitignore'
                if reason:skipped.append(dict(path=rel,reason=reason));continue
                try:
                    content=read_text(p);files.append(dict(path=rel,text=content,origin_updated_at=p.stat().st_mtime));collected_bytes+=len(content.encode('utf8'))
                except AppError as e:skipped.append(dict(path=rel,reason=e.code))
                if collected_bytes>PROJECT_LIMIT:raise AppError('PROJECT_QUOTA','Project text quota is 200 MiB')
        locator=str(root)
    else:
        if locator:
            p=Path(locator).expanduser()
            if not p.is_absolute():raise AppError('PATH_REQUIRED','Use an absolute local path')
            if p.is_symlink() or SECRET_NAME.search(p.name):raise AppError('SECRET_OR_LINK','Secret files and symlinks are excluded')
            p=p.resolve(strict=True)
            if p.suffix.lower() not in TEXT_TYPES:raise AppError('FILE_TYPE','Unsupported file type')
            text=read_text(p);locator=str(p);updated=p.stat().st_mtime
        else:text=body.get('pasted_text') or '';updated=None
        if len(text.encode('utf8'))>UPLOAD_LIMIT:raise AppError('UPLOAD_TOO_LARGE','Upload/paste limit is 10 MiB')
        if not text.strip():raise AppError('EMPTY_SOURCE','Source contains no text')
        if 'PRIVATE KEY-----' in text:raise AppError('SECRET_FILE','Private key input is excluded')
        if kind in ('tickets_csv','tickets_json','data_csv'):
            try:
                if kind=='tickets_json':
                    rows=json.loads(text)
                    if isinstance(rows,dict):rows=rows.get('tickets',[])
                    if not isinstance(rows,list):raise ValueError('Expected JSON array or {tickets: [...]}')
                else:rows=list(csv.DictReader(io.StringIO(text)))
            except (ValueError,csv.Error):raise AppError('INVALID_IMPORT','Input must be valid JSON tickets or CSV with a header')
            mapping=body.get('mapping',{})
            for n,row in enumerate(rows):
                if not isinstance(row,dict):errors.append(dict(row=n+1,reason='Row must be an object'));continue
                if kind=='data_csv':record={str(k):str(v) for k,v in row.items()}
                else:
                    record={k:row.get(mapping.get(k,k)) for k in ('id','title','description','status','updated_at','url')}
                    if not record['id'] or not record['title']:errors.append(dict(row=n+1,reason='Missing mapped ID or title'));continue
                content='\n'.join(f'{k}: {v}' for k,v in record.items() if v is not None)
                files.append(dict(path=f'{Path(locator).name if locator else body["title"]}#row-{n+1}',text=content,origin_updated_at=record.get('updated_at',updated)))
        else:files.append(dict(path=Path(locator).name if locator else body['title'],text=text,origin_updated_at=updated))
    if not files and kind!='repo':raise AppError('EMPTY_SOURCE','No eligible UTF-8 text or valid records were found',skipped=skipped[:100],row_errors=errors[:100])
    return dict(files=files,skipped=skipped,row_errors=errors,canonical_locator=locator,total_bytes=sum(len(f['text'].encode('utf8')) for f in files))

def chunks_for(file):
    # Line windows capped in characters so code with a giant single line is not dropped.
    lines=file['text'].splitlines();start=0
    while start<len(lines):
        end=min(start+24,len(lines));text='\n'.join(lines[start:end])
        section=next((line.lstrip('# ') for line in reversed(lines[:start+1]) if line.startswith('#')),'')
        for offset in range(0,len(text),1600):
            yield dict(content=text[offset:offset+1600],path=file['path'],line_start=start+1,line_end=end,section=section,origin_updated_at=file['origin_updated_at'])
        if end==len(lines):break
        start=end-3

class Ingestion:
    def __init__(self,store,semantic=None):self.store=store;self.semantic=semantic
    def preview(self,body):
        data=collect(body)
        return dict(file_count=len(data['files']),total_bytes=data['total_bytes'],files=[dict(path=f['path'],bytes=len(f['text'].encode('utf8'))) for f in data['files'][:100]],skipped=data['skipped'][:100],row_errors=data['row_errors'][:100],canonical_locator=data['canonical_locator'],sample=data['files'][0]['text'][:1200] if data['files'] else '')
    def add(self,project_id,body):
        self.store.project(project_id)
        s=dict(id=uid(),project_id=project_id,kind=body['kind'],title=body['title'],config=body,status='queued',generation=0,hash=None,indexed_at=None,error=None,stale=False,file_count=0,chunk_count=0,manifest=[],total_bytes=0)
        with self.store.disk:self.store.save_source(s)
        return s
    def sync(self,id):
        s=self.store.source(id);job=dict(id=uid(),source_id=id,status='indexing',progress=0,error=None)
        db=self.store.disk
        with db:
            db.execute('INSERT INTO indexing_jobs VALUES(?,?,?)',(job['id'],id,dumps(job)))
            s['status']='indexing';self.store.save_source(s)
        try:
            data=collect(s['config'])
            others=sum(x['total_bytes'] for x in self.store.sources(s['project_id']) if x['id']!=id)
            if data['total_bytes']+others>PROJECT_LIMIT:raise AppError('PROJECT_QUOTA','Project text quota is 200 MiB')
            file_hashes={f['path']:digest(f['text']) for f in data['files']}
            content_hash=digest(dumps(file_hashes))
            needs_vectors=self.semantic and self.semantic.ready and db.execute('SELECT 1 FROM chunks WHERE source_id=? AND vector IS NULL LIMIT 1',(id,)).fetchone()
            if content_hash==s['hash'] and not needs_vectors:
                s.update(status='ready',stale=False,error=None,indexed_at=now())
            else:
                generation=s['generation']+1;pending=[]
                old={json.loads(r['metadata'])['path']:[] for r in db.execute('SELECT metadata FROM chunks WHERE source_id=?',(id,))}
                for r in db.execute('SELECT * FROM chunks WHERE source_id=?',(id,)):
                    old[json.loads(r['metadata'])['path']].append(dict(r))
                old_hashes={f['path']:f['hash'] for f in s['manifest']}
                for f in data['files']:
                    semantic_rebuild=self.semantic and self.semantic.ready and any(not r['vector'] for r in old.get(f['path'],[]))
                    if old_hashes.get(f['path'])==file_hashes[f['path']] and old.get(f['path']) and not semantic_rebuild:
                        for r in old[f['path']]:pending.append((r['id'],r['content'],r['metadata'],r['vector']))
                    else:
                        for ch in chunks_for(f):
                            pieces=self.semantic.split(ch['content']) if self.semantic and self.semantic.ready else [ch['content']]
                            for content in pieces:
                                meta={k:v for k,v in ch.items() if k!='content'}
                                meta.update(source_id=id,title=s['title'],kind=s['kind'],content_hash=file_hashes[f['path']],indexed_at=now(),canonical_locator=data['canonical_locator'])
                                vec=self.semantic.embed_passage(content) if self.semantic and self.semantic.ready else None
                                if vec is not None:
                                    from .config import E5_MODEL,E5_REVISION
                                    meta.update(embedding_model=E5_MODEL,embedding_revision=E5_REVISION,embedding_dimension=len(vec))
                                pending.append((uid(),content,dumps(meta),dumps(vec) if vec is not None else None))
                # No awaits inside publication: old index survives every build/embedding failure.
                with db:
                    db.execute('DELETE FROM chunks WHERE source_id=?',(id,))
                    db.executemany('INSERT INTO chunks(id,source_id,project_id,generation,content,metadata,vector) VALUES(?,?,?,?,?,?,?)',[(cid,id,s['project_id'],generation,content,meta,vec) for cid,content,meta,vec in pending])
                    s.update(status='ready',generation=generation,hash=content_hash,indexed_at=now(),error=None,stale=False,file_count=len(data['files']),chunk_count=len(pending),total_bytes=data['total_bytes'],canonical_locator=data['canonical_locator'],manifest=[dict(path=f['path'],hash=file_hashes[f['path']]) for f in data['files']],skipped=data['skipped'][:100],row_errors=data['row_errors'][:100])
                    self.store.save_source(s)
            job.update(status='ready',progress=100)
        except Exception as e:
            s.update(status='error',stale=s['generation']>0,error=e.message if isinstance(e,AppError) else 'Cannot read/index source. Check path, permissions and optional semantic model.')
            job.update(status='error',error=s['error'])
        with db:
            self.store.save_source(s);db.execute('UPDATE indexing_jobs SET payload=? WHERE id=?',(dumps(job),job['id']))
        return job
