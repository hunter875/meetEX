import json
import os
from pathlib import Path
import pytest
from app.ingestion import Ingestion,collect,FILE_LIMIT,UPLOAD_LIMIT
from app.retrieval import Retrieval,Semantic
from app.errors import AppError
from app.storage import uid

def search(store,p,q):return Retrieval(store,Semantic(Path('.'))).search(p,q)['results']
def add(store,project,body):
    ingest=Ingestion(store);s=ingest.add(project,body);job=ingest.sync(s['id']);assert job['status']=='ready',job
    return s['id']

@pytest.mark.acceptance('RAG-01','SRC-01','RAG-03')
def test_project_isolation_delete_and_literal_sql_input(store,project):
    other=store.create_project(dict(name='Other',description='',glossary={}))
    a=add(store,project['id'],dict(kind='text',title='API-17',pasted_text='API-17 status: needs staging tests.'))
    b=add(store,other['id'],dict(kind='schema',title='schema',pasted_text='DROP TABLE projects; -- API-17 deployed production'))
    assert 'staging' in search(store,project['id'],'API-17')[0]['content']
    assert all(r['project_id']==project['id'] for r in search(store,project['id'],'API-17'))
    assert len(store.projects())==2
    with store.disk:store.disk.execute('DELETE FROM sources WHERE id=?',(a,))
    assert search(store,project['id'],'API-17')==[]
    assert search(store,other['id'],'API-17')

@pytest.mark.acceptance('RAG-02','RAG-03','SEC-04','SRC-02')
def test_repo_incremental_atomic_reindex_and_safe_files(tmp_path,store,project):
    repo=tmp_path/'repo';repo.mkdir();(repo/'doc.md').write_text('# API-17\nStatus needs staging tests.',encoding='utf8')
    (repo/'old.txt').write_text('OLD_REMOVAL_SENTINEL',encoding='utf8')
    (repo/'.env').write_text('SECRET_SENTINEL',encoding='utf8');(repo/'private.pem').write_text('SECRET_SENTINEL',encoding='utf8')
    (repo/'ignored.txt').write_text('IGNORED_SENTINEL',encoding='utf8');(repo/'.gitignore').write_text('ignored.txt\nignored-dir/\n*.md\n!doc.md\n',encoding='utf8')
    nested=repo/'nested';nested.mkdir();(nested/'.gitignore').write_text('!keep.md\n',encoding='utf8');(nested/'keep.md').write_text('NESTED_KEEP_SENTINEL');(nested/'omit.md').write_text('NESTED_OMIT_SENTINEL')
    (repo/'ignored-dir').mkdir();(repo/'ignored-dir'/'nested.md').write_text('IGNORED_DIR_SENTINEL')
    (repo/'blob.txt').write_bytes(b'a\0b');(repo/'large.txt').write_bytes(b'x'*(FILE_LIMIT+1))
    (repo/'key.txt').write_text('-----BEGIN RSA PRIVATE KEY-----\nSECRET_SENTINEL')
    sid=add(store,project['id'],dict(kind='repo',title='Repo',local_path=str(repo)))
    contents=' '.join(r['content'] for r in store.disk.execute('SELECT content FROM chunks'))
    assert not any(x in contents for x in ('SECRET_SENTINEL','IGNORED_SENTINEL','IGNORED_DIR_SENTINEL'))
    assert 'NESTED_KEEP_SENTINEL' in contents and 'NESTED_OMIT_SENTINEL' not in contents
    old=store.source(sid);ids=[r[0] for r in store.disk.execute('SELECT id FROM chunks WHERE source_id=?',(sid,))]
    Ingestion(store).sync(sid)
    assert store.source(sid)['generation']==old['generation']
    assert ids==[r[0] for r in store.disk.execute('SELECT id FROM chunks WHERE source_id=?',(sid,))]
    (repo/'old.txt').unlink();(repo/'doc.md').write_text('# API-17\nNEW_SYNC_SENTINEL',encoding='utf8')
    assert Ingestion(store).sync(sid)['status']=='ready'
    assert not search(store,project['id'],'OLD_REMOVAL_SENTINEL')
    assert search(store,project['id'],'NEW_SYNC_SENTINEL')
    renamed=tmp_path/'moved';repo.rename(renamed)
    assert Ingestion(store).sync(sid)['status']=='error'
    assert store.source(sid)['stale'] and search(store,project['id'],'NEW_SYNC_SENTINEL')

@pytest.mark.acceptance('SEC-04')
def test_symlink_outside_root_is_never_indexed(tmp_path,store,project):
    repo=tmp_path/'repo';repo.mkdir();(repo/'safe.txt').write_text('safe caption context')
    outside=tmp_path/'outside';outside.mkdir();(outside/'secret.txt').write_text('OUTSIDE_ROOT_SENTINEL')
    link=repo/'external'
    if os.name=='nt':
        import subprocess
        # Fixed test-owned paths, native Windows junction. No shell is used for cleanup.
        result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True)
        assert result.returncode==0,result.stderr
    else:link.symlink_to(outside,target_is_directory=True)
    sid=add(store,project['id'],dict(kind='repo',title='Repo',local_path=str(repo)))
    assert not search(store,project['id'],'OUTSIDE_ROOT_SENTINEL')
    assert any(x['reason']=='outside_root_or_link' for x in store.source(sid)['skipped'])
    if os.name=='nt':os.rmdir(link)

@pytest.mark.acceptance('SRC-01')
@pytest.mark.parametrize('kind,text',[('tickets_csv','Key,Title,State\nAPI-17,Fix auth,In QA\n,Invalid row,Todo\n'),('tickets_json',json.dumps([{'Key':'API-17','Title':'Fix auth','State':'In QA'},{'Title':'invalid'}]))])
def test_ticket_mapping_and_invalid_row_preview(store,project,kind,text):
    body=dict(kind=kind,title='Tickets',pasted_text=text,mapping={'id':'Key','title':'Title','status':'State'})
    preview=Ingestion(store).preview(body)
    assert preview['file_count']==1 and preview['row_errors'][0]['row']==2
    sid=add(store,project['id'],body)
    assert 'In QA' in search(store,project['id'],'API-17')[0]['content']

@pytest.mark.acceptance('SRC-02')
def test_upload_and_project_quotas_are_enforced(store,project,monkeypatch):
    with pytest.raises(AppError) as error:collect(dict(kind='text',title='large',pasted_text='x'*(UPLOAD_LIMIT+1)))
    assert error.value.code=='UPLOAD_TOO_LARGE'
    monkeypatch.setattr('app.ingestion.PROJECT_LIMIT',30)
    add(store,project['id'],dict(kind='text',title='A',pasted_text='a'*20))
    source=Ingestion(store).add(project['id'],dict(kind='text',title='B',pasted_text='b'*20))
    assert Ingestion(store).sync(source['id'])['status']=='error'
    assert store.source(source['id'])['generation']==0

@pytest.mark.acceptance('RAG-03')
def test_deleting_last_repo_file_publishes_empty_index(tmp_path,store,project):
    repo=tmp_path/'repo';repo.mkdir();p=repo/'only.md';p.write_text('DELETED_LAST_SENTINEL')
    sid=add(store,project['id'],dict(kind='repo',title='Repo',local_path=str(repo)));p.unlink()
    assert Ingestion(store).sync(sid)['status']=='ready'
    assert not search(store,project['id'],'DELETED_LAST_SENTINEL')
    assert store.source(sid)['chunk_count']==0

@pytest.mark.acceptance('RAG-05')
def test_safe_fts_operators_are_literal_terms(store,project):
    add(store,project['id'],dict(kind='text',title='Auth',pasted_text='Authentication API-17 implementation source'))
    assert search(store,project['id'],'API-17 " OR NEAR( foo ) --')
    assert store.disk.execute('PRAGMA foreign_key_check').fetchall()==[]
