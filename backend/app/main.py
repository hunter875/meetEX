from __future__ import annotations
import asyncio
import copy
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime,timezone
from urllib.parse import urlparse
from fastapi import FastAPI,WebSocket,WebSocketDisconnect,Request,Query
from fastapi.responses import JSONResponse,PlainTextResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from .config import Config,DEFAULTS,E5_MODEL,E5_REVISION
from .models import ProjectCreate,ProjectPatch,SourceInput,SearchInput,MeetingCreate,MeetingPrefs,Control,Caption,SuggestInput,ReportGenerate,ReportEdit,SettingsPatch,Credential
from .errors import AppError
from .storage import Storage,now,uid,dumps
from .ingestion import Ingestion
from .retrieval import Semantic,Retrieval
from .llm import Provider,SuggestionPayload
from .service import Service,SECTIONS
from .models import ProjectDTO,MeetingDTO,SnapshotDTO,ReportDTO,CitationDTO,RoutingDecision

def markdown_report(report,language='vi'):
    p=report['payload'];lines=[f'# Meet Copilot · Report v{report["version"]}',f'Mode: {report["mode"]} · Draft/reviewed: {report["reviewed_at"] or "draft"}',p['summary_en' if language=='en' else 'summary_vi'],'Summary evidence: '+', '.join(p.get('summary_segment_ids',[]))]
    headings=dict(requirements='Yêu cầu',decisions='Quyết định đã xác nhận',action_items='Action items',open_questions='Câu hỏi bỏ ngỏ',ai_proposals='Đề xuất AI')
    for section in SECTIONS:
        lines+=['',f'## {headings[section]}']
        for item in p[section]:
            lines.append('- '+(item.get('text_en') or item['text'] if language=='en' else item['text'])+f' [{item["origin"]}; {item["confirmation"]}]')
            if section=='action_items':lines.append(f'  Owner: {item["owner"] or "Chưa xác nhận"}; Due: {item["normalized_due"] or item["raw_due_text"] or "Chưa xác nhận"}; Status: {item["status"]}')
            lines.append('  Evidence: '+', '.join(item['evidence_segment_ids']))
    lines+=['','## Cảnh báo']+['- '+w for w in p['capture_warnings']]
    return '\n'.join(lines)

def create_app(config=None):
    config=config or Config.load();store=Storage(config.data_dir);semantic=Semantic(config.data_dir/'models');retrieval=Retrieval(store,semantic)
    if config.provider_url!=DEFAULTS['provider_url'] or config.model!=DEFAULTS['model']:
        store.set_settings(dict(provider_url=config.provider_url,model=config.model))
    provider=Provider(config,store.settings);service=Service(store,retrieval,provider);ingestion=Ingestion(store,semantic)
    ack_timings=[];last_heartbeats={};capture_connections={}
    index_lock=asyncio.Lock()
    async def sync_source(id):
        def isolated():
            worker_store=copy.copy(store)
            worker_store.disk=Storage.connect(str(config.data_dir/'copilot.sqlite3'))
            try:return Ingestion(worker_store,semantic).sync(id)
            finally:worker_store.disk.close()
        async with index_lock:return await asyncio.to_thread(isolated)

    async def maintenance():
        while True:
            await asyncio.sleep(15)
            for m in store.meetings():
                if m['status']=='active' and m['binding'] and time.monotonic()-last_heartbeats.get(m['id'],time.monotonic())>50:
                    service.cancel(m['id']);store.control(m['id'],dict(action='interrupt',idempotency_key=uid(),reason='heartbeat_lost'))
                    await service.emit('session.snapshot',m['id'],snapshot=store.snapshot(m['id']))
            for m in store.meetings():
                at=datetime.now(timezone.utc);date=datetime.fromisoformat(m['ended_at'] or m['started_at'])
                if (at-date).total_seconds()>store.settings()['retention_days']*86400:service.forget(m['id'])
            removed=store.cleanup()
            for id in removed:await service.emit('meeting.deleted',meeting_id=id)

    @asynccontextmanager
    async def lifespan(app):
        worker=asyncio.create_task(maintenance())
        yield
        worker.cancel();await asyncio.gather(worker,return_exceptions=True);await service.shutdown();await provider.aclose();store.close()

    app=FastAPI(title='Meet Copilot local API',version='0.1.0',lifespan=lifespan)
    app.state.store=store;app.state.service=service;app.state.provider=provider;app.state.ingestion=ingestion;app.state.retrieval=retrieval
    app.add_middleware(CORSMiddleware,allow_origins=list(config.origins),allow_methods=['GET','POST','PATCH','DELETE','PUT'],allow_headers=['Authorization','Content-Type'])
    def valid_host(host):
        return host in ('127.0.0.1:8765','localhost:8765','127.0.0.1','localhost','[::1]:8765')
    def origin_allowed(origin):return not origin or origin in config.origins
    @app.middleware('http')
    async def guard(request:Request,call_next):
        rid=uid()
        if not valid_host(request.headers.get('host','')):return JSONResponse(AppError('HOST_DENIED','Backend accepts loopback Host only',403).payload(rid),status_code=403)
        if not origin_allowed(request.headers.get('origin')):return JSONResponse(AppError('ORIGIN_DENIED','Pair the exact extension ID, then restart backend',403).payload(rid),status_code=403)
        if request.url.path!='/health' and request.method!='OPTIONS':
            auth=request.headers.get('authorization','')
            if not secrets.compare_digest(auth,'Bearer '+config.token):return JSONResponse(AppError('AUTH_REQUIRED','Valid local pairing token required',401).payload(rid),status_code=401)
        try:response=await call_next(request)
        except Exception as error:
            logging.getLogger('meet_copilot').error('internal_failure request_id=%s error_type=%s',rid,type(error).__name__)
            return JSONResponse(AppError('INTERNAL_ERROR','Local operation failed. Check input and retry; sensitive details are not logged.',500).payload(rid),status_code=500)
        response.headers['X-Request-ID']=rid;return response
    @app.exception_handler(AppError)
    async def app_error(request,e):return JSONResponse(e.payload(uid()),status_code=e.status)
    @app.exception_handler(RequestValidationError)
    async def input_error(request,e):
        # Do not serialize validation input: it can contain a provider API key.
        fields=[dict(field='.'.join(map(str,x['loc'])),type=x['type']) for x in e.errors()]
        return JSONResponse(AppError('INVALID_INPUT','Request body failed validation',422,fields=fields).payload(uid()),status_code=422)

    @app.get('/health')
    def health():return dict(status='ok',protocol_version=1,fts5=True)
    @app.get('/api/v1/projects',response_model=list[ProjectDTO])
    async def projects():return store.projects()
    @app.post('/api/v1/projects',status_code=201,response_model=ProjectDTO)
    async def create_project(body:ProjectCreate):return store.create_project(body.model_dump())
    @app.get('/api/v1/projects/{id}',response_model=ProjectDTO)
    async def project(id:str):return store.project(id)
    @app.patch('/api/v1/projects/{id}',response_model=ProjectDTO)
    async def patch_project(id:str,body:ProjectPatch):
        previous=store.project(id);updated=store.patch_project(id,body.model_dump(exclude_unset=True,exclude_none=True))
        if updated['glossary']!=previous['glossary']:service.source_changed(id)
        return updated
    @app.delete('/api/v1/projects/{id}')
    async def delete_project(id:str):
        affected=[m['id'] for m in store.meetings() if m['project_id']==id]
        async with index_lock:
            for m in store.meetings():
                if m['project_id']==id:service.forget(m['id'])
            store.delete_project(id)
        for meeting_id in affected:await service.emit('meeting.deleted',meeting_id=meeting_id)
        return dict(deleted=True)
    @app.post('/api/v1/sources/preview')
    async def preview(body:SourceInput):
        try:return await asyncio.to_thread(ingestion.preview,body.model_dump())
        except (FileNotFoundError,OSError):raise AppError('PATH_UNAVAILABLE','Check local path and read permissions')
    @app.get('/api/v1/projects/{id}/sources')
    async def sources(id:str):
        return [{k:v for k,v in s.items() if k!='config'} for s in store.sources(id)]
    @app.post('/api/v1/projects/{id}/sources',status_code=201)
    async def add_source(id:str,body:SourceInput):
        s=ingestion.add(id,body.model_dump());job=await sync_source(s['id']);service.source_changed(id)
        return dict(source_id=s['id'],job_id=job['id'],job=job)
    @app.post('/api/v1/sources/{id}/reindex')
    async def reindex(id:str):
        before=store.source(id);job=await sync_source(id)
        if job['status']=='ready':service.source_changed(before['project_id'])
        return job
    @app.get('/api/v1/sources/{id}')
    async def source(id:str):
        s=store.source(id)
        return {k:v for k,v in s.items() if k!='config'}
    @app.get('/api/v1/sources/{id}/chunks',response_model=list[CitationDTO])
    async def source_chunks(id:str,limit:int=Query(20,ge=1,le=100)):
        store.source(id)
        return [dict(**json.loads(r['metadata']),id=r['id'],project_id=r['project_id'],content=r['content'],generation=r['generation']) for r in store.disk.execute('SELECT * FROM chunks WHERE source_id=? ORDER BY rowid LIMIT ?',(id,limit))]
    @app.delete('/api/v1/sources/{id}')
    async def delete_source(id:str):
        async with index_lock:
            s=store.source(id)
            with store.disk:store.disk.execute('DELETE FROM sources WHERE id=?',(id,))
        service.source_changed(s['project_id']);return dict(deleted=True,historical_excerpts_retained=True)
    @app.get('/api/v1/chunks/{id}')
    async def chunk(id:str):
        row=store.disk.execute('SELECT * FROM chunks WHERE id=?',(id,)).fetchone()
        if not row:raise AppError('NOT_FOUND','Source chunk is no longer in the current index',404)
        return dict(id=id,content=row['content'],generation=row['generation'],**json.loads(row['metadata']))
    @app.get('/api/v1/jobs/{id}')
    async def job(id:str):
        if id in service.report_jobs:return service.report_jobs[id]
        row=store.disk.execute('SELECT payload FROM indexing_jobs WHERE id=?',(id,)).fetchone()
        if row:return json.loads(row[0])
        raise AppError('NOT_FOUND','Job not found',404)
    @app.post('/api/v1/projects/{id}/search')
    async def search(id:str,body:SearchInput):return retrieval.search(id,body.query,body.limit)
    @app.get('/api/v1/meetings',response_model=list[MeetingDTO])
    async def meetings(project_id:str|None=None,query:str='',date_from:str|None=None,date_to:str|None=None):
        out=[]
        for m in store.meetings():
            if project_id and m['project_id']!=project_id:continue
            from zoneinfo import ZoneInfo
            local_date=datetime.fromisoformat(m['started_at']).astimezone(ZoneInfo(m['timezone'])).date().isoformat()
            if date_from and local_date<date_from:continue
            if date_to and local_date>date_to:continue
            if query and query.casefold() not in (m['title']+' '+' '.join(s['text'] for s in store.transcript(m['id']))).casefold():continue
            segments=store.transcript(m['id'])
            duration=max(0,(datetime.fromisoformat(segments[-1]['observed_to'].replace('Z','+00:00'))-datetime.fromisoformat(segments[0]['observed_from'].replace('Z','+00:00'))).total_seconds()) if segments else 0
            out.append(dict(**m,report_count=len(store.objects(m['id'],'reports')),gap_count=len(store.gaps(m['id'])),observed_duration_s=duration))
        return out
    @app.post('/api/v1/meetings',status_code=201,response_model=MeetingDTO)
    async def create_meeting(body:MeetingCreate):return store.create_meeting(body.model_dump())
    @app.get('/api/v1/meetings/{id}',response_model=SnapshotDTO)
    async def meeting(id:str):return store.snapshot(id)
    @app.patch('/api/v1/meetings/{id}')
    async def meeting_prefs(id:str,body:MeetingPrefs):
        m=store.meeting(id);patch=body.model_dump(exclude_unset=True)
        if 'auto_mode' in patch and patch['auto_mode'] is None:raise AppError('INVALID_INPUT','Auto mode requires true or false',422)
        if patch.get('self_speaker') and patch['self_speaker'] not in {s['speaker'] for s in store.transcript(id)}:raise AppError('UNKNOWN_SPEAKER','Choose a name observed in captions')
        if patch.get('confirmed_segment_ids') is not None and not set(patch['confirmed_segment_ids']).issubset({s['id'] for s in store.transcript(id)}):raise AppError('SEGMENT_SCOPE','Confirmed memory must reference segments in this meeting')
        patch={k:v for k,v in patch.items() if k!='confirmed_segment_ids' or v is not None}
        context_changed=any(k in patch and patch[k]!=m.get(k) for k in ('self_speaker','confirmed_segment_ids'))
        if context_changed:m['context_revision']=m.get('context_revision',0)+1
        m.update(patch);db=store.db_for(id)
        with db:store.save_meeting(db,m)
        if context_changed:service.invalidate_suggestions(id)
        return m
    @app.post('/api/v1/meetings/{id}/control')
    async def control(id:str,body:Control):
        if body.action!='resume':service.cancel(id)
        m=store.control(id,body.model_dump());await service.emit('session.snapshot',id,snapshot=store.snapshot(id));return m
    @app.get('/api/v1/meetings/{id}/transcript')
    async def transcript(id:str,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=1000),query:str=''):
        rows=[s for s in store.transcript(id) if not query or query.casefold() in s['text'].casefold()]
        return dict(total=len(rows),items=rows[offset:offset+limit],transcript_revision=store.meeting(id)['transcript_revision'])
    @app.delete('/api/v1/meetings/{id}')
    async def delete_meeting(id:str):
        service.forget(id);store.delete_meeting(id);await service.emit('meeting.deleted',meeting_id=id);return dict(deleted=True)
    @app.post('/api/v1/meetings/{id}/suggest',status_code=202)
    async def suggest(id:str,body:SuggestInput):return dict(request_id=service.schedule(id,body.model_dump()))
    @app.post('/api/v1/meetings/{id}/classify',response_model=RoutingDecision)
    async def classify_request(id:str,body:SuggestInput):
        # Preview the same scoped routing policy without scheduling or billing AI.
        return service.prepare(id,body.model_dump())['routing']
    @app.get('/api/v1/meetings/{id}/suggestions/{sid}/citations',response_model=list[CitationDTO])
    async def citations(id:str,sid:str):
        suggestion=service.find_suggestion(id,sid);out=[]
        for snap in suggestion['snapshot']['sources']:
            try:current=store.source(snap['source_id']);deleted=False;changed=current['generation']!=snap['generation']
            except AppError:deleted=True;changed=True
            out.append(dict(**snap,source_deleted=deleted,source_changed=changed))
        return out
    @app.post('/api/v1/meetings/{id}/demo-caption')
    async def demo_caption(id:str,body:Caption):
        if not store.meeting(id)['demo']:raise AppError('DEMO_ONLY','Synthetic captions are allowed only in explicitly labeled demo sessions',403)
        duplicate=store.db_for(id).execute('SELECT 1 FROM applied_events WHERE meeting_id=? AND event_id=?',(id,body.event_id)).fetchone()
        ack=store.apply_caption(id,body.model_dump())
        if ack['applied'] and not duplicate:service.auto(id,body.model_dump())
        return ack
    @app.post('/api/v1/meetings/{id}/reports',status_code=202)
    async def reports(id:str,body:ReportGenerate):return service.report(id,body.transcript_revision)
    @app.get('/api/v1/reports/{id}',response_model=ReportDTO)
    async def report(id:str):return service.get_report(id)
    @app.patch('/api/v1/reports/{id}',response_model=ReportDTO)
    async def edit_report(id:str,body:ReportEdit):return service.edit_report(id,body)
    @app.get('/api/v1/reports/{id}/export')
    async def export(id:str,format:str='markdown',language:str='vi'):
        r=service.get_report(id)
        if format=='json':return JSONResponse(r,headers={'Content-Disposition':f'attachment; filename="report-v{r["version"]}.json"'})
        return PlainTextResponse(markdown_report(r,language),headers={'Content-Disposition':f'attachment; filename="report-v{r["version"]}.md"'})
    def settings_payload():
        return dict(**store.settings(),has_key=bool(provider.key),semantic_status=semantic.status,semantic_error=semantic.error,semantic_model=E5_MODEL,semantic_revision=E5_REVISION,paired_origins=list(config.origins))
    @app.get('/api/v1/settings')
    async def settings():return settings_payload()
    @app.patch('/api/v1/settings')
    async def patch_settings(body:SettingsPatch):
        patch=body.model_dump(exclude_unset=True)
        if any(v is None and k not in ('price_input','price_output','price_date') for k,v in patch.items()):raise AppError('INVALID_INPUT','Setting cannot be null',422)
        store.set_settings(patch);return settings_payload()
    @app.put('/api/v1/provider/credential')
    async def credential(body:Credential):provider.key=body.api_key.get_secret_value();return dict(has_key=bool(provider.key))
    @app.delete('/api/v1/provider/credential')
    async def remove_credential():provider.key='';return dict(has_key=False)
    @app.post('/api/v1/provider/test')
    async def provider_test():
        # This is a real, small billed protocol/JSON request, regardless of demo sessions.
        from .llm import validate_suggestion
        context=dict(transcript_revision=1,segments=[dict(id='connection-test',text='Could you clarify?')],sources=[],action='connection test',sentence_limit=1)
        payload=await provider.complete(context,SuggestionPayload);validate_suggestion(payload,context)
        return dict(connected=True,mode='real',model=store.settings()['model'])
    @app.post('/api/v1/semantic/load')
    async def load_semantic():
        await asyncio.to_thread(semantic.load)
        # Re-split/rebuild every source atomically for tokenizer compatibility and vector metadata.
        for p in store.projects():
            for s in store.sources(p['id']):
                await sync_source(s['id'])
            service.source_changed(p['id'])
        store.set_settings(dict(semantic_enabled=True));return settings_payload()
    @app.get('/api/v1/metrics')
    async def metrics():
        def summary(samples):
            samples=sorted(samples)
            return dict(n=len(samples),median_ms=samples[len(samples)//2] if samples else None,p95_ms=samples[min(len(samples)-1,int(len(samples)*.95))] if samples else None,p95_note='Descriptive sample percentile; small n is not a reliable SLA.')
        records=provider.metrics;usage=[r['usage'] for r in records if r['usage']]
        known=dict(prompt_tokens=sum(x.get('prompt_tokens',0) for x in usage),completion_tokens=sum(x.get('completion_tokens',0) for x in usage))
        unknown=len(records)-len(usage);sett=store.settings();estimate=None
        if not unknown and records and sett['price_input'] is not None and sett['price_output'] is not None and sett['price_date']:
            estimate=(known['prompt_tokens']*sett['price_input']+known['completion_tokens']*sett['price_output'])/1e6
        return dict(latency_records=service.latency_records,classifier=summary(service.routing_timings),provider_by_route={route:summary([r['duration_ms'] for r in records if r.get('route')==route and r['duration_ms'] is not None]) for route in ('fast','explain','deep','clarify')},request_count=len(records),known_usage=known,unknown_usage_count=unknown,estimated_cost=estimate,price_date=sett['price_date'],cost_note='Estimate from configured per-million token prices, not a bill.',capture_apply=summary(ack_timings),retrieval=summary(retrieval.timings),provider=summary([r['duration_ms'] for r in records if r['duration_ms'] is not None]),provider_first_token=summary([r['first_token_ms'] for r in records if r['first_token_ms'] is not None]),backend_stable_to_request=summary(service.stable_to_request),backend_stable_to_validated=summary(service.stable_to_ready),report=summary([j['duration_ms'] for j in service.report_jobs.values() if j.get('duration_ms') is not None]),records=records)

    @app.websocket('/api/v1/events')
    async def events(ws:WebSocket):
        if not valid_host(ws.headers.get('host','')) or ws.headers.get('origin') not in config.origins:
            await ws.close(code=4403);return
        await ws.accept();bound=None;bound_scope=None;authenticated=False;send_lock=asyncio.Lock()
        async def send(event):
            async with send_lock:await ws.send_json(event)
        try:
            auth=await asyncio.wait_for(ws.receive_json(),5)
            if not isinstance(auth,dict):await ws.close(code=4401);return
            if auth.get('type')!='auth' or auth.get('protocol_version')!=1 or not secrets.compare_digest(str(auth.get('token','')),config.token):
                await send(dict(type='auth.error',payload=AppError('AUTH_REQUIRED','Invalid pairing token',401).payload()));await ws.close(code=4401);return
            authenticated=True;await send(dict(type='auth.ok',protocol_version=1));service.listeners.add(send)
            while True:
                envelope=await ws.receive_json()
                if not isinstance(envelope,dict):raise ValueError('Invalid envelope')
                if len(dumps(envelope))>65536:raise AppError('MESSAGE_LIMIT','WebSocket message is too large')
                try:
                    kind=envelope.get('type');payload=envelope.get('payload',{})
                    if envelope.get('protocol_version')!=1:raise AppError('PROTOCOL_VERSION','Unsupported protocol version')
                    if kind=='heartbeat':
                        if bound and capture_connections.get(bound) is not ws:raise AppError('BINDING_SCOPE','This socket is no longer the capture owner',403)
                        if bound:last_heartbeats[bound]=time.monotonic()
                        await send(dict(type='heartbeat',protocol_version=1));continue
                    if kind=='session.bind':
                        id=envelope.get('session_id');m=store.meeting(id)
                        if m['demo']:raise AppError('DEMO_BIND','Demo sessions cannot bind Meet captions')
                        if m['status']!='active':raise AppError('SESSION_INTERRUPTED','Resume the interrupted/paused session before binding',409)
                        tab=payload.get('tab_id');doc=payload.get('document_id');key=payload.get('meeting_key')
                        if not isinstance(tab,int) or not isinstance(doc,str) or not doc or key!=m['meeting_key']:raise AppError('BINDING_SCOPE','Tab/document/meeting identity mismatch',403)
                        old=m['binding'];db=store.db_for(id)
                        with db:
                            if old and old['tab_id']!=tab:raise AppError('BINDING_SCOPE','Session belongs to a different tab',403)
                            if old and old['document_id']!=doc:store.gap(db,id,'document_reloaded',certainty='possible')
                            if m.get('transport_gap_id'):
                                row=db.execute('SELECT payload FROM capture_gaps WHERE id=?',(m['transport_gap_id'],)).fetchone()
                                if row:
                                    g=json.loads(row[0]);g['to_at']=now();db.execute('UPDATE capture_gaps SET payload=? WHERE id=?',(dumps(g),g['id']))
                                m['transport_gap_id']=None
                            m['binding']=dict(tab_id=tab,document_id=doc,meeting_key=key);store.save_meeting(db,m)
                        bound=id;bound_scope=dict(m['binding']);capture_connections[id]=ws;last_heartbeats[id]=time.monotonic();await send(dict(type='session.snapshot',protocol_version=1,session_id=id,server_revision=m['transcript_revision'],payload={'snapshot':store.snapshot(id)}));continue
                    if not bound or envelope.get('session_id')!=bound:raise AppError('SESSION_SCOPE','Bind the owning tab before sending capture events',403)
                    m=store.meeting(bound)
                    if m['binding']!=bound_scope or capture_connections.get(bound) is not ws:raise AppError('BINDING_SCOPE','This socket belongs to an obsolete document/connection',403)
                    if kind=='caption.upsert':
                        e=Caption.model_validate(payload).model_dump();began=time.perf_counter()
                        duplicate=store.db_for(bound).execute('SELECT 1 FROM applied_events WHERE meeting_id=? AND event_id=?',(bound,e['event_id'])).fetchone()
                        ack=store.apply_caption(bound,e);ack['processing_ms']=(time.perf_counter()-began)*1000;ack['backend_applied']=ack['applied'];ack['segment_id']=e['segment_id'];ack['segment_revision']=e['revision'];ack_timings.append(ack['processing_ms']);ack_timings[:]=ack_timings[-1000:];await send(ack)
                        if ack['applied'] and not duplicate:
                            service.auto(bound,e);await service.emit('caption.updated',bound,segment_id=e['segment_id'])
                    elif kind=='capture.status':
                        if m['status']!='active':continue
                        status=payload.get('status')
                        if status not in ('starting','observing','waiting_for_caption','captions_off','unsupported_dom','paused','disconnected','meeting_left','unknown'):raise AppError('CAPTURE_STATUS','Unknown capture state')
                        db=store.db_for(bound)
                        with db:
                            if status in ('unsupported_dom','captions_off','unknown') and m['capture_status']!=status:
                                if not m.get('capture_gap_id'):m['capture_gap_id']=store.gap(db,bound,status,certainty='possible' if status in ('unknown','unsupported_dom') else 'certain')['id']
                            elif status in ('observing','waiting_for_caption') and m.get('capture_gap_id'):
                                g=json.loads(db.execute('SELECT payload FROM capture_gaps WHERE id=?',(m['capture_gap_id'],)).fetchone()[0]);g['to_at']=now();db.execute('UPDATE capture_gaps SET payload=? WHERE id=?',(dumps(g),g['id']));m['capture_gap_id']=None
                            m['capture_status']=status;store.save_meeting(db,m)
                        await service.emit('capture.status',bound,status=status)
                    elif kind=='capture.gap':
                        reason=payload.get('reason')
                        if reason not in ('outbox_overflow','end_flush_timeout','adapter_replaced','document_reloaded','interrupted_pending_discarded','adapter_heartbeat_lost','event_rejected'):raise AppError('GAP_REASON','Unknown transport gap')
                        db=store.db_for(bound)
                        event_id=payload.get('event_id')
                        if event_id is not None and (not isinstance(event_id,str) or not 1<=len(event_id)<=100):raise AppError('INVALID_EVENT','Invalid gap event ID')
                        with db:
                            prior=db.execute('SELECT ack FROM applied_events WHERE meeting_id=? AND event_id=?',(bound,event_id)).fetchone() if event_id else None
                            if not prior:
                                store.gap(db,bound,reason,certainty='possible')
                                if event_id:
                                    ack=dict(type='capture.gap.ack',protocol_version=1,session_id=bound,event_id=event_id,reason=reason)
                                    db.execute('INSERT INTO applied_events VALUES(?,?,?,?,?)',(bound,event_id,'diagnostic',0,dumps(ack)))
                        if event_id:await send(json.loads(prior[0]) if prior else ack)
                    else:raise AppError('UNKNOWN_EVENT','Unknown WebSocket event')
                except (ValidationError,AppError) as e:
                    error=e if isinstance(e,AppError) else AppError('INVALID_EVENT','Invalid capture event schema')
                    await send(dict(type='error',protocol_version=1,event_id=envelope.get('event_id'),payload=error.payload()))
        except (WebSocketDisconnect,TimeoutError,ValueError):pass
        finally:
            service.listeners.discard(send)
            if authenticated and bound:
                try:
                    m=store.meeting(bound)
                    if m['status']=='active' and m['binding']==bound_scope and capture_connections.get(bound) is ws and not m.get('transport_gap_id'):
                        db=store.db_for(bound)
                        with db:m['transport_gap_id']=store.gap(db,bound,'transport_disconnected',certainty='possible')['id'];m['capture_status']='disconnected';store.save_meeting(db,m)
                except AppError:pass
                if capture_connections.get(bound) is ws:capture_connections.pop(bound,None)
    # WS/extension-only output contracts share the generated component registry;
    # no fake HTTP route is required to expose their schema to TypeScript clients.
    from .models import CaptionAckDTO,CaptureGapAckDTO,CaptureDiagnosticsDTO
    base_openapi=app.openapi
    def protocol_openapi():
        schema=base_openapi()
        for dto in (CaptionAckDTO,CaptureGapAckDTO,CaptureDiagnosticsDTO):
            schema['components']['schemas'][dto.__name__]=dto.model_json_schema()
        return schema
    app.openapi=protocol_openapi
    return app

app=create_app()
