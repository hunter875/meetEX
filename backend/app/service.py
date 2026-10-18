from __future__ import annotations
import asyncio
import hashlib
import json
import time
from collections import defaultdict,deque
from datetime import datetime,timezone
from .errors import AppError
from .storage import uid,now,dumps
from .llm import SuggestionPayload,ReportPayload,validate_suggestion,validate_report,demo_suggestion,demo_report,SECTIONS
from .routing import classify
from .evidence import VALIDATION_POLICY

class Service:
    def __init__(self,store,retrieval,provider):
        self.store,self.retrieval,self.provider=store,retrieval,provider
        self.listeners=set();self.active={};self.queued={};self.auto_timers={};self.rate=defaultdict(deque);self.tasks=set();self.report_jobs={};self.report_tasks={};self.timings=[];self.stable_times={};self.stable_to_request=[];self.stable_to_ready=[]
        self.routing_timings=[]
    async def emit(self,type,id=None,**payload):
        revision=self.store.meeting(id)['transcript_revision'] if id else 0
        event=dict(type=type,protocol_version=1,session_id=id,server_revision=revision,payload=payload)
        for callback in list(self.listeners):
            try:await callback(event)
            except Exception:self.listeners.discard(callback)
    def task(self,coro):
        task=asyncio.create_task(coro);self.tasks.add(task)
        def done(finished):
            self.tasks.discard(finished)
            if not finished.cancelled():finished.exception()  # Consume task errors; public job state is the error channel.
        task.add_done_callback(done);return task
    def save_request(self,id,r):
        db=self.store.db_for(id)
        with db:db.execute('INSERT INTO ai_requests VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(r['id'],id,dumps(r)))
    def find_suggestion(self,id,sid):
        for s in self.store.objects(id,'suggestions'):
            if s['id']==sid:return s
        raise AppError('NOT_FOUND','Suggestion is not part of this meeting',404)
    def prepare(self,id,body):
        m=self.store.meeting(id)
        if m['status']!='active':raise AppError('INVALID_STATE','Live suggestions require an active meeting',409)
        if body.get('base_suggestion_id'):
            base=self.find_suggestion(id,body['base_suggestion_id'])
            snapshot=json.loads(dumps(base['snapshot']))
        else:
            segments=self.store.transcript(id)
            selected=body.get('selected_segment_ids') or []
            if selected:
                allowed={s['id'] for s in segments}
                if any(s not in allowed for s in selected):raise AppError('SEGMENT_SCOPE','Selected segment does not belong to this meeting')
                segments=[s for s in segments if s['id'] in selected]
            elif segments:
                # Recent window, retain at least the latest segment. No report uses this truncation.
                cutoff=datetime.fromisoformat(segments[-1]['observed_to'].replace('Z','+00:00')).timestamp()-180
                segments=[s for s in segments if datetime.fromisoformat(s['observed_to'].replace('Z','+00:00')).timestamp()>=cutoff]
                budget=self.store.settings()['input_chars']//2;kept=[]
                for s in reversed(segments):
                    if kept and sum(len(x['text']) for x in kept)+len(s['text'])>budget:break
                    kept.insert(0,s)
                segments=kept
            if not segments:raise AppError('NO_TRANSCRIPT','Wait for captions or select a captured segment',422)
            query=(body.get('question') or '')+' '+segments[-1]['text']
            sources=self.retrieval.search(m['project_id'],query)['results']
            confirmed=[s for s in self.store.transcript(id) if s['id'] in m.get('confirmed_segment_ids',[])]
            memory=[];memory_budget=3000
            for candidate in reversed(confirmed):
                if len(dumps(candidate))<=memory_budget and len(memory)<8:memory.insert(0,candidate);memory_budget-=len(dumps(candidate))
            glossary=self.store.project(m['project_id'])['glossary']
            remaining=self.store.settings()['input_chars']-len(dumps(segments))-len(dumps(memory))-len(dumps(glossary))-len(body.get('question',''))-1500;fitted=[]
            for source in sources:
                if len(dumps(source))>remaining:continue
                fitted.append(source);remaining-=len(dumps(source))
            snapshot=dict(meeting_id=id,project_id=m['project_id'],transcript_revision=m['transcript_revision'],context_revision=m.get('context_revision',0),index_generation={s['id']:s['generation'] for s in self.store.sources(m['project_id'])},segments=segments,memory=memory,memory_omitted_count=len(confirmed)-len(memory),sources=fitted,glossary=glossary,self_speaker=m['self_speaker'])
        snapshot['action']=body['action'];snapshot['question']=body.get('question','');snapshot['sentence_limit']=self.store.settings()['sentence_limit']
        snapshot['routing']=classify(snapshot,body.get('response_mode','auto'))
        self.routing_timings.append(snapshot['routing']['classifier_ms']);self.routing_timings=self.routing_timings[-1000:]
        snapshot['provider_config']={key:self.store.settings()[key] for key in ('provider_url','model')}
        snapshot.pop('input_hash',None)
        if len(dumps(snapshot))>self.store.settings()['input_chars']:raise AppError('CONTEXT_BUDGET','Selected transcript/context is too large. Select fewer segments or shorten the question.',422)
        # Timing is observational, not part of the semantic cache identity.
        hash_input={**snapshot,'routing':{k:v for k,v in snapshot['routing'].items() if k!='classifier_ms'}}
        hash_input['validation_policy'] = VALIDATION_POLICY
        snapshot['input_hash']=hashlib.sha256(dumps(hash_input).encode()).hexdigest()
        return snapshot
    def schedule(self,id,body):
        m=self.store.meeting(id);auto=body['action']=='auto'
        if auto and not m['auto_mode']:raise AppError('AUTO_DISABLED','Auto mode is disabled; manual suggestions remain available',409)
        if auto and id in self.queued and self.queued[id]['action']!='auto':return self.queued[id]['id']
        snapshot=self.prepare(id,body)
        if auto and snapshot['routing']['route']=='listen':
            r=dict(id=uid(),action='auto',status='skipped',created_at=now(),snapshot=snapshot,error=None,started_at=None,duration_ms=0)
            self.save_request(id,r)
            # Do not consume quota, create a provider job or cancel a manual request.
            self.task(self.emit('suggestion.skipped',id,request_id=r['id'],routing=snapshot['routing']))
            return r['id']
        if auto:
            recent=self.rate[id];current=time.monotonic()
            while recent and recent[0]<current-60:recent.popleft()
            if len(recent)>=self.store.settings()['auto_per_minute']:raise AppError('AUTO_QUOTA','Auto quota reached; capture continues and manual suggestions remain available',429)
        for cached in reversed(self.store.objects(id,'suggestions')):
            if not cached['stale'] and cached['snapshot']['input_hash']==snapshot['input_hash'] and snapshot['transcript_revision']==m['transcript_revision']:
                return cached['request_id']
        r=dict(id=uid(),action=body['action'],status='queued',created_at=now(),snapshot=snapshot,error=None,started_at=None,duration_ms=None)
        self.save_request(id,r)
        db=self.store.db_for(id)
        with db:m['latest_request']=r['id'];self.store.save_meeting(db,m)
        if id in self.queued:
            previous=self.queued.pop(id);previous['status']='superseded';self.save_request(id,previous)
        self.queued[id]=r
        if id in self.active:
            if not auto:self.active[id].cancel()
        else:self.start_runner(id)
        return r['id']
    def start_runner(self,id):
        task=self.task(self.run_live(id));self.active[id]=task
        def done(finished):
            if self.active.get(id) is finished:self.active.pop(id,None)
            if id in self.queued and id not in self.active:self.start_runner(id)
        task.add_done_callback(done)
    async def generate_suggestion(self, snapshot):
        context = snapshot
        repairable = {
            'AI_CITATION', 'AI_EVIDENCE', 'AI_REVISION', 'AI_ROLE_UNSET',
            'AI_COMMITMENT', 'AI_NEGATION', 'AI_ROUTING', 'AI_NUMERIC',
            'AI_CLAIM', 'AI_UNVERIFIED',
        }
        instructions = {
            'AI_ROLE_UNSET': 'Return one neutral clarification QUESTION ONLY about the latest turn. No introduction, acknowledgement, action offer or policy explanation. Preserve its meaning; do not mistake QA observations for an instruction attack.',
            'AI_COMMITMENT': 'Match this exact action, task/object and environment to explicit acceptance by the named user. Cite the acceptance turn. Another task or another participant does not authorize a promise. Otherwise ask who should own it.',
            'AI_NEGATION': 'Preserve the explicit deployment negation. Do not turn a question, prohibition or tentative date into a commitment. Ask for clarification.',
            'AI_REVISION': 'Copy transcript_revision exactly into input_revision. Regenerate the same scoped answer without inventing facts.',
            'AI_ROUTING': 'Return a neutral clarification QUESTION ONLY for the missing approval/fact/commitment. No declarative readiness confirmation, offer or promise. Routing is not permission.',
            'AI_NUMERIC': 'Match numeric facts to the SAME attribute/entity, units, range and condition in original evidence. Do not borrow a TTL value for a timeout. Remove unsupported findings and ask; genuinely new proposals must be explicitly labeled and never approved facts.',
            'AI_CLAIM': 'Confirmation belongs to its exact proposition, task and environment. Staging approval is not production approval. Use only original evidence or ask a neutral question.',
            'AI_UNVERIFIED': 'The qualitative finding cannot be verified in the supported scope. Remove it or explicitly label the result partial; never claim supported merely from a valid citation ID.',
        }
        for attempt in range(2):
            try:
                output = await self.provider.complete(context, SuggestionPayload)
                validate_suggestion(output, snapshot)
                return output
            except AppError as error:
                if attempt or error.code not in repairable:
                    raise
                # All original evidence remains unchanged; feedback is the only addition.
                context = {
                    **snapshot,
                    'validation_feedback': dict(
                        code=error.code, message=error.message,
                        instruction=instructions.get(error.code,
                            'Regenerate from the SAME transcript and project excerpts. Findings contain only project facts with nonempty sources[i].id citations, never source_id or transcript IDs. Remove unsupported findings rather than attaching unrelated citations. Preserve conflicts, uncertainty and input_revision. Do not invent commitments.')),
                }
    async def run_live(self,id):
        try:
            while id in self.queued:
                r=self.queued.pop(id);began=time.perf_counter();r.update(status='running',started_at=now());self.save_request(id,r)
                stable=self.stable_times.get(id)
                if stable and stable['revision']==r['snapshot']['transcript_revision']:
                    r['stable_to_request_ms']=(began-stable['at'])*1000;self.stable_to_request.append(r['stable_to_request_ms']);self.stable_to_request=self.stable_to_request[-1000:]
                if r['action']=='auto':self.rate[id].append(time.monotonic())
                await self.emit('suggestion.started',id,request_id=r['id'])
                try:
                    m=self.store.meeting(id)
                    output=demo_suggestion(r['snapshot']) if m['demo'] else await self.generate_suggestion(r['snapshot'])
                    validate_suggestion(output,r['snapshot'])
                    m=self.store.meeting(id)
                    generations={s['id']:s['generation'] for s in self.store.sources(m['project_id'])}
                    content_stale=any(current['text']!=original['text'] for original in r['snapshot']['segments']+r['snapshot'].get('memory',[]) for current in self.store.transcript(id) if current['id']==original['id'])
                    stale=m['latest_request']!=r['id'] or generations!=r['snapshot']['index_generation'] or content_stale or m['transcript_revision']!=r['snapshot']['transcript_revision'] or m['self_speaker']!=r['snapshot'].get('self_speaker') or m.get('context_revision',0)!=r['snapshot'].get('context_revision',0) or self.store.project(m['project_id'])['glossary']!=r['snapshot'].get('glossary',{})
                    stale=stale or r['snapshot'].get('provider_config')!={key:self.store.settings()[key] for key in ('provider_url','model')}
                    # Explicit card actions may use an older immutable snapshot. Keep that fact visible.
                    s=dict(id=uid(),request_id=r['id'],created_at=now(),mode='demo' if m['demo'] else 'real',payload=output.model_dump(),snapshot=r['snapshot'],stale=stale,automatic=r['action']=='auto',duration_ms=(time.perf_counter()-began)*1000)
                    db=self.store.db_for(id)
                    with db:db.execute('INSERT INTO suggestions VALUES(?,?,?,?)',(s['id'],id,r['id'],dumps(s)))
                    r['status']='stale' if stale else 'ready'
                    if stable and stable['revision']==r['snapshot']['transcript_revision']:
                        s['stable_to_validated_ms']=(time.perf_counter()-stable['at'])*1000;self.stable_to_ready.append(s['stable_to_validated_ms']);self.stable_to_ready=self.stable_to_ready[-1000:]
                    await self.emit('suggestion.stale' if stale else 'suggestion.ready',id,suggestion=s)
                except asyncio.CancelledError:
                    r['status']='cancelled';self.save_request(id,r);raise
                except Exception as e:
                    error=e.payload(r['id']) if isinstance(e,AppError) else AppError('AI_INTERNAL','Suggestion failed; no validated result was published',500).payload(r['id'])
                    r.update(status='error',error=error)
                    await self.emit('suggestion.error',id,request_id=r['id'],error=error)
                finally:
                    r['duration_ms']=(time.perf_counter()-began)*1000
                    try:self.save_request(id,r)
                    except AppError:pass
        finally:
            pass  # The done callback also handles cancellation before the coroutine first starts.
    def cancel(self,id):
        if id in self.active:self.active[id].cancel()
        if id in self.queued:
            r=self.queued.pop(id);r['status']='cancelled';self.save_request(id,r)
        if id in self.auto_timers:self.auto_timers.pop(id).cancel()
    def auto(self,id,event):
        m=self.store.meeting(id)
        if event['stable']:self.stable_times[id]=dict(revision=m['transcript_revision'],at=time.perf_counter())
        if not (m['status']=='active' and m['auto_mode'] and event['stable']):return
        if not m['self_speaker'] or not event['speaker_label'] or event['speaker_label']==m['self_speaker']:return
        if id in self.auto_timers:self.auto_timers[id].cancel()
        async def later():
            try:
                await asyncio.sleep(self.store.settings()['auto_spacing_s'])
                self.schedule(id,dict(action='auto'))
            except asyncio.CancelledError:pass
            except AppError as e:await self.emit('suggestion.error',id,error=e.payload())
            finally:
                if self.auto_timers.get(id) is asyncio.current_task():self.auto_timers.pop(id,None)
        self.auto_timers[id]=self.task(later())
    def invalidate_suggestions(self,id):
        db=self.store.db_for(id)
        with db:
            for s in self.store.objects(id,'suggestions'):
                s['stale']=True;db.execute('UPDATE suggestions SET payload=? WHERE id=?',(dumps(s),s['id']))
    def source_changed(self,project_id):
        for m in self.store.meetings():
            if m['project_id']!=project_id:continue
            self.invalidate_suggestions(m['id'])
    def report_chunks(self,segments,budget=16000):
        chunks=[];current=[];size=0
        for s in segments:
            # Split oversized turns into pieces carrying the same evidence ID; never drop the tail.
            pieces=[{**s,'text':s['text'][n:n+budget//2]} for n in range(0,len(s['text']),budget//2)]
            for piece in pieces:
                n=len(dumps(piece))
                if current and size+n>budget:
                    chunks.append(current);current=current[-1:] if len(dumps(current[-1]))<budget//3 else [];size=len(dumps(current))
                current.append(piece);size+=n
        if current:chunks.append(current)
        return chunks
    def report(self,id,revision):
        m=self.store.meeting(id)
        if m['status'] in ('active','paused'):raise AppError('INVALID_STATE','End the meeting before generating its final report',409)
        if revision!=m['transcript_revision']:raise AppError('REVISION_CONFLICT','Reload the final transcript snapshot',409)
        for j in self.report_jobs.values():
            if j['meeting_id']==id and j['status'] in ('queued','running'):return j
        job=dict(id=uid(),meeting_id=id,status='queued',error=None,progress=0,report_id=None)
        self.report_jobs[job['id']]=job;self.report_tasks[job['id']]=self.task(self.run_report(id,job,self.store.transcript(id),revision));return job
    async def generate_report_part(self,context):
        original=context
        for attempt in range(2):
            result=await self.provider.complete(context,ReportPayload,True)
            try:
                validate_report(result,original['segments']);return result
            except AppError as failure:
                if attempt:raise
                # One bounded correction with the SAME speech evidence. Never silently
                # strip unsupported fields or publish the rejected intermediate output.
                issues=[dict(code=failure.code,message=failure.message,**failure.extra)]
                for section in SECTIONS:
                    for item in getattr(result,section):
                        try:validate_report(ReportPayload(**{section:[item]}),original['segments'],check_coverage=False)
                        except AppError as error:issues.append(dict(section=section,item_id=item.id,code=error.code,message=error.message))
                context={**original,'validation_feedback':dict(
                    instruction='Previous output was rejected. Generate a corrected complete report from the original speech only. All unconfirmed/proposed and open-question deadline fields must be null. Mixed tentative segments cannot support confirmed decisions. Do not add facts or weaken evidence requirements.',
                    issues=issues[:20])}
    async def run_report(self,id,job,segments,revision):
        began=time.perf_counter();job['status']='running'
        try:
            m=self.store.meeting(id);parts=self.report_chunks(segments);payload=ReportPayload()
            for n,part in enumerate(parts):
                context=dict(segments=part,timezone=m['timezone'],meeting_started_at=m['started_at'],transcript_revision=revision,task='report map; preserve each requirement/decision/action/open question, with evidence. Summarize only supplied observations.')
                result=demo_report(part) if m['demo'] else await self.generate_report_part(context)
                validate_report(result,part)
                if result.summary_vi.strip():payload.summary_vi='\n'.join(filter(None,(payload.summary_vi,result.summary_vi)))
                if result.summary_en.strip():payload.summary_en='\n'.join(filter(None,(payload.summary_en,result.summary_en)))
                payload.summary_segment_ids=list(dict.fromkeys(payload.summary_segment_ids+result.summary_segment_ids))
                for section in SECTIONS:
                    existing={(item.text.casefold(),tuple(sorted(item.evidence_segment_ids))) for item in getattr(payload,section)}
                    for item in getattr(result,section):
                        key=(item.text.casefold(),tuple(sorted(item.evidence_segment_ids)))
                        if key not in existing:
                            item.id=uid()  # Model-local IDs can repeat across maps or sections.
                            getattr(payload,section).append(item);existing.add(key)
                payload.capture_warnings.extend(result.capture_warnings);job['progress']=round((n+1)*100/max(len(parts),1))
                await self.emit('job.progress',id,job=job)
            # Empty sessions can be exported without paying for a fabricated summary.
            if not parts:payload.capture_warnings.append('Không có phụ đề được quan sát; không thể suy nội dung cuộc họp.')
            payload.capture_warnings.extend(f'{g["reason"]}: {g["from_at"]} → {g["to_at"] or "chưa xác định"} ({g["certainty"]})' for g in self.store.gaps(id))
            payload.capture_warnings.append('Báo cáo chỉ bao phủ phụ đề đã quan sát; hãy kiểm tra nghĩa và bằng chứng trước khi gửi.')
            if not m['self_speaker']:payload.capture_warnings.append('Chưa xác định participant là Tôi; tên người nói chỉ là nhãn caption.')
            if not self.store.sources(m['project_id']):payload.capture_warnings.append('Chưa có nguồn dự án để đối chiếu.')
            if m['demo']:payload.capture_warnings.append('DEMO — không phải kết quả provider thật.')
            validate_report(payload,segments)
            report=self.save_report(id,payload,revision,mode='demo' if m['demo'] else 'real')
            job.update(status='ready',progress=100,report_id=report['id']);await self.emit('report.ready',id,report=report)
        except asyncio.CancelledError:job['status']='cancelled';raise
        except Exception as e:job.update(status='error',error=e.payload() if isinstance(e,AppError) else AppError('REPORT_ERROR','Report failed; previous versions were preserved',500).payload())
        finally:
            job['duration_ms']=(time.perf_counter()-began)*1000
            self.report_tasks.pop(job['id'],None)
    def save_report(self,id,payload,revision,mode='real',user_edits=False,reviewed=False,parent=None):
        db=self.store.db_for(id)
        with db:
            row=db.execute('SELECT MAX(version) FROM reports WHERE meeting_id=?',(id,)).fetchone()
            version=(row[0] or 0)+1
            report=dict(id=uid(),meeting_id=id,version=version,transcript_revision=revision,payload=payload.model_dump(),user_edits=user_edits,reviewed_at=now() if reviewed else None,mode=mode,created_at=now(),parent_id=parent)
            db.execute('INSERT INTO reports VALUES(?,?,?,?)',(report['id'],id,version,dumps(report)))
        return report
    def get_report(self,rid):
        for db in (self.store.ram,self.store.disk):
            row=db.execute('SELECT payload FROM reports WHERE id=?',(rid,)).fetchone()
            if row:return json.loads(row[0])
        raise AppError('NOT_FOUND','Report not found',404)
    def edit_report(self,rid,body):
        old=self.get_report(rid);reports=self.store.objects(old['meeting_id'],'reports');current=reports[-1]
        if body.expected_version!=current['version']:raise AppError('VERSION_CONFLICT','Report changed. Your local edit is kept; reload or save against the current version.',409,current_version=current['version'])
        validate_report(body.payload,self.store.transcript(old['meeting_id']),user_edit=True)
        # Editable transcript fields are explicitly marked user edits when changed.
        for section in SECTIONS:
            originals={x['id']:x for x in old['payload'][section]}
            for item in getattr(body.payload,section):
                if item.model_dump()!=originals.get(item.id) and section!='ai_proposals':item.origin='user_edit'
        return self.save_report(old['meeting_id'],body.payload,old['transcript_revision'],old['mode'],True,body.reviewed,rid)
    async def shutdown(self):
        for task in list(self.tasks):task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        for m in self.store.meetings():
            if m['status'] in ('active','paused'):self.store.control(m['id'],dict(action='interrupt',idempotency_key=uid(),reason='backend_shutdown'))
    def forget(self,id):
        self.cancel(id);self.rate.pop(id,None);self.stable_times.pop(id,None)
        for key,job in list(self.report_jobs.items()):
            if job['meeting_id']==id and key in self.report_tasks:self.report_tasks.pop(key).cancel()
        self.report_jobs={k:v for k,v in self.report_jobs.items() if v['meeting_id']!=id}
