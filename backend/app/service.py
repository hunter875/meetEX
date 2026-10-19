from __future__ import annotations
import asyncio
import hashlib
import json
import time
from collections import Counter
from collections import defaultdict,deque
from datetime import datetime,timezone
from .errors import AppError
from .storage import uid,now,dumps
from .llm import provider_context,SuggestionPayload,ReportPayload,validate_suggestion,validate_report,demo_suggestion,demo_report,SECTIONS
from .routing import classify
from .evidence import VALIDATION_POLICY
from . import meeting_memory
from .orchestration import TriggerPolicy,decide,meaning_key,card_key,retrieval_query,freshness_safe_smalltalk,POLICY_VERSION,PROMPT_VERSION

class Service:
    POLICY_VERSION=POLICY_VERSION
    def __init__(self,store,retrieval,provider):
        self.store,self.retrieval,self.provider=store,retrieval,provider
        self.listeners=set();self.active={};self.queued={};self.auto_timers={};self.rate=defaultdict(deque);self.tasks=set();self.report_jobs={};self.report_tasks={};self.timings=[];self.stable_times={};self.stable_to_request=[];self.stable_to_ready=[]
        self.routing_timings=[]
        self.latency_records=[];self.request_clocks={}
        self.policy=TriggerPolicy();self.trigger_metrics=deque(maxlen=1000);self.auto_batches={};self.seen_stable={};self.running_requests={};self.preparing={};self.scheduler_states={};self.auto_deadlines={}
        self.preparation_locks={}
        self.orchestration_counts=Counter()
        self.change_log={}
        self.preparation_jobs={}
    def equivalent_changes_only(self,id,snapshot):
        current=self.store.meeting(id);delta=current['transcript_revision']-snapshot['transcript_revision']
        changes=[c for c in self.change_log.get(id,[]) if c['revision']>snapshot['transcript_revision']]
        if delta<=0 or len(changes)!=delta or [c['revision'] for c in changes]!=list(range(snapshot['transcript_revision']+1,current['transcript_revision']+1)):return False
        originals={s['id']:s for s in snapshot['segments']+snapshot.get('memory',[])}
        latest={s['id']:s for s in self.store.transcript(id)}
        cursor=snapshot.get('capture_cursor')
        appended={r['id'] for r in self.store.db_for(id).execute('SELECT id FROM caption_segments WHERE meeting_id=? AND rowid>?',(id,cursor))} if cursor is not None else set()
        for change in changes:
            sid=change['id']
            if sid in originals:
                a,b=originals[sid],latest.get(sid)
                if not b or a.get('speaker')!=b.get('speaker') or meaning_key(a['text'])!=meaning_key(b['text']):return False
            elif sid not in appended or not change['smalltalk']:return False
        return True
    def mark(self,r,stage):
        r['timing']['marks'].append(dict(stage=stage,offset_ms=(time.perf_counter()-self.request_clocks[r['id']])*1000))
    def finish_timing(self,r):
        if r['id'] not in self.request_clocks:return
        attempts=[a for a in getattr(self.provider,'metrics',[]) if a.get('logical_request_id')==r['id']]
        r['timing'].update(http_attempts=len(attempts),repair_attempts=sum(a.get('generation_attempt',1)>1 for a in attempts),usage_unknown_attempts=sum(a.get('usage') is None for a in attempts),wire_input_chars_total=sum(a.get('wire_input_chars',0) for a in attempts))
        r['timing']['outcome']=r['status'];self.mark(r,'request_completed')
        self.latency_records.append(dict(request_id=r['id'],**json.loads(dumps(r['timing']))));self.latency_records=self.latency_records[-1000:]
        self.request_clocks.pop(r['id'],None)
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
    def prepare(self,id,body,retrieval_result=None):
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
            focus=body.get('_focus_segment_ids') or [segments[-1]['id']] if segments else []
            selected_ids=set(focus)
            if not selected and not body.get('base_suggestion_id'):
                # Whole turns only; keep the latest context, all focus turns and their immediate predecessors.
                for n,segment in enumerate(segments):
                    if segment['id'] in focus:selected_ids.update(s['id'] for s in segments[max(0,n-3):n+1])
                selected_ids.update(s['id'] for s in segments[-self.policy.recent_turns:])
                total_turns=len(segments);segments=[s for s in segments if s['id'] in selected_ids]
            else:total_turns=len(segments)
            if not segments:raise AppError('NO_TRANSCRIPT','Wait for captions or select a captured segment',422)
            query=retrieval_query(segments,body.get('question',''),focus)
            retrieval_result=retrieval_result if retrieval_result is not None else self.retrieval.search(m['project_id'],query)
            sources=retrieval_result['results']
            confirmed=[s for s in self.store.transcript(id) if s['id'] in m.get('confirmed_segment_ids',[])]
            all_ledger=self.store.memory(id)
            inactive={e['segment_id'] for item in all_ledger if item['kind'] in ('decision','action_item') and (not meeting_memory.current(item) or item['status'] in ('cancelled','disputed','invalidated')) for e in item['evidence']}
            memory=[];memory_budget=3000
            for candidate in reversed([s for s in confirmed if s['id'] not in inactive]):
                if len(dumps(candidate))<=memory_budget and len(memory)<8:memory.insert(0,candidate);memory_budget-=len(dumps(candidate))
            confirmed_kept=len(memory)
            relevance=query+' '+' '.join(s['text'] for s in memory+segments[-3:])
            ledger,ledger_omitted=meeting_memory.select(all_ledger,relevance)
            fitted_ledger=[]
            for item in ledger:
                needed=[]
                for ref in item['evidence']:
                    candidate=self.store.evidence_revision(id,ref['segment_id'],ref['revision'])
                    if not any(s['id']==candidate['id'] and s['revision']==candidate['revision'] for s in segments+memory+needed):needed.append(candidate)
                size=sum(len(dumps(s)) for s in needed)
                if size<=memory_budget and len(memory)+len(needed)<=8:
                    memory.extend(needed);memory_budget-=size;fitted_ledger.append(item)
                else:ledger_omitted+=1
            glossary=self.store.project(m['project_id'])['glossary']
            remaining=self.store.settings()['input_chars']-len(dumps(segments))-len(dumps(memory))-len(dumps(fitted_ledger))-len(dumps(glossary))-len(body.get('question',''))-1500;fitted=[]
            seen_excerpts=set()
            for source in sources:
                identity=(source['content'],source.get('stale',False),source.get('conflicting',False))
                if identity in seen_excerpts:continue
                if len(dumps(source))>remaining:continue
                seen_excerpts.add(identity)
                fitted.append(source);remaining-=len(dumps(source))
            snapshot=dict(meeting_id=id,project_id=m['project_id'],transcript_revision=m['transcript_revision'],context_revision=m.get('context_revision',0),index_generation={s['id']:s['generation'] for s in self.store.sources(m['project_id'])},segments=segments,memory=memory,memory_omitted_count=len(confirmed)-confirmed_kept,sources=fitted,glossary=glossary,self_speaker=m['self_speaker'],focus_segment_ids=focus,context_omitted_count=total_turns-len(segments),source_omitted_count=len(sources)-len(fitted))
            snapshot.update(structured_memory=fitted_ledger,memory_revision=m.get('memory_revision',0),ledger_omitted_count=ledger_omitted)
        return self.finalize_snapshot(snapshot,body)
    def finalize_snapshot(self,snapshot,body):
        snapshot['action']=body['action'];snapshot['question']=body.get('question','');snapshot['sentence_limit']=self.store.settings()['sentence_limit']
        focus=set(snapshot.get('focus_segment_ids',[]))
        routing_snapshot={**snapshot,'segments':[s for s in snapshot['segments'] if s['id'] not in focus]+[s for s in snapshot['segments'] if s['id'] in focus]} if focus else snapshot
        snapshot['routing']=classify(routing_snapshot,body.get('response_mode','auto'))
        self.routing_timings.append(snapshot['routing']['classifier_ms']);self.routing_timings=self.routing_timings[-1000:]
        snapshot['provider_config']={key:self.store.settings()[key] for key in ('provider_url','model','output_tokens','input_chars','live_timeout_s')}
        snapshot['response_mode']=body.get('response_mode','auto')
        snapshot['orchestration_policy']=POLICY_VERSION
        snapshot['prompt_version']=PROMPT_VERSION
        if 'capture_cursor' not in snapshot:
            snapshot['capture_cursor']=self.store.db_for(snapshot['meeting_id']).execute('SELECT coalesce(max(rowid),0) FROM caption_segments WHERE meeting_id=?',(snapshot['meeting_id'],)).fetchone()[0]
        snapshot.pop('input_hash',None)
        if len(dumps(snapshot))>self.store.settings()['input_chars']:raise AppError('CONTEXT_BUDGET','Selected transcript/context is too large. Select fewer segments or shorten the question.',422)
        # Timing is observational, not part of the semantic cache identity.
        hash_input={**snapshot,'routing':{k:v for k,v in snapshot['routing'].items() if k!='classifier_ms'}}
        hash_input.pop('retrieval_ms',None)
        hash_input['validation_policy'] = VALIDATION_POLICY
        snapshot['input_hash']=hashlib.sha256(dumps(hash_input).encode()).hexdigest()
        return snapshot
    async def prepare_async(self,id,body):
        if body.get('base_suggestion_id'):return self.prepare(id,body)
        snapshot=self.prepare(id,body,{'results':[]})
        query=retrieval_query(snapshot['segments'],body.get('question',''),snapshot.get('focus_segment_ids',[]))
        if hasattr(self.retrieval,'search_async'):
            try:
                async with asyncio.timeout(min(self.policy.retrieval_timeout_s,self.store.settings()['live_timeout_s'])):
                    result=await self.retrieval.search_async(snapshot['project_id'],query)
            except TimeoutError:raise AppError('RETRIEVAL_TIMEOUT','Retrieval timed out; no provider generation was started',503,True)
        else:result=self.retrieval.search(snapshot['project_id'],query)
        sources=[];seen=set();budget=self.store.settings()['input_chars']-len(dumps(snapshot))+100
        for source in result['results']:
            identity=(source['content'],source.get('stale',False),source.get('conflicting',False))
            if identity in seen or len(dumps(source))>budget:continue
            seen.add(identity);sources.append(source);budget-=len(dumps(source))
        snapshot['sources']=sources;snapshot['source_omitted_count']=len(result['results'])-len(sources)
        if 'index_generation' in result:snapshot['index_generation']=result['index_generation']
        snapshot['retrieval_ms']=result['duration_ms']
        return self.finalize_snapshot(snapshot,body)
    async def schedule_async(self,id,body):
        meeting=self.store.meeting(id)
        identity=dumps([body,meeting['transcript_revision'],meeting.get('context_revision',0),meeting.get('memory_revision',0),meeting['self_speaker'],self.store.settings(),[(s['id'],s['generation'],s.get('stale',False)) for s in self.store.sources(meeting['project_id'])]])
        previous=self.preparation_jobs.get(id)
        if previous and not previous['task'].done() and (previous['identity']==identity or (body['action']=='auto' and not previous['automatic'])):
            work=previous['task'];self.orchestration_counts['preparation_coalesced']+=1
        else:
            if previous and not previous['task'].done():previous['task'].cancel()
            work=self.task(self.prepare_and_schedule(id,body))
            self.preparation_jobs[id]=dict(identity=identity,task=work,automatic=body['action']=='auto')
        try:
            return await asyncio.shield(work)
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():raise
            raise AppError('PREPARATION_SUPERSEDED','A newer request or session control replaced this request',409)
    async def prepare_and_schedule(self,id,body):
        self.preparing[id]=self.preparing.get(id,0)+1
        try:
            self.trigger_state(id,'processing','context_retrieval')
            snapshot=await self.prepare_async(id,body)
            return self.schedule(id,body,snapshot)
        except AppError as error:
            if self.preparation_jobs.get(id,{}).get('task') is asyncio.current_task():self.trigger_state(id,'quota' if error.code=='AUTO_QUOTA' else 'error',error.code)
            raise
        finally:
            self.preparing[id]-=1
            if not self.preparing[id]:
                self.preparing.pop(id,None)
                if id in self.auto_batches and id not in self.active:self.arm_auto(id)
            if self.preparation_jobs.get(id,{}).get('task') is asyncio.current_task():self.preparation_jobs.pop(id,None)
    def trigger_state(self,id,state,reason,**extra):
        record=dict(meeting_id=id,state=state,reason=reason,policy_version=POLICY_VERSION,**extra)
        self.trigger_metrics.append(record);self.scheduler_states[id]=dict(state=state,reason=reason,policy_version=POLICY_VERSION)
        if state in ('listening','waiting','coalesced') and (id in self.running_requests or self.preparing.get(id)):
            self.scheduler_states[id]=dict(state='processing',reason='provider_generation',policy_version=POLICY_VERSION)
        self.orchestration_counts[reason]+=1
        self.task(self.emit('suggestion.scheduler',id,**self.scheduler_states[id]))
    def schedule(self,id,body,snapshot=None):
        m=self.store.meeting(id);auto=body['action']=='auto'
        if m['status']!='active':raise AppError('INVALID_STATE','Live suggestions require an active meeting',409)
        if auto and not m['auto_mode']:raise AppError('AUTO_DISABLED','Auto mode is disabled; manual suggestions remain available',409)
        if auto and id in self.queued and self.queued[id]['action']!='auto':return self.queued[id]['id']
        snapshot=snapshot or self.prepare(id,body)
        for candidate in (self.running_requests.get(id),self.queued.get(id)):
            if candidate and candidate['snapshot']['input_hash']==snapshot['input_hash']:
                self.trigger_state(id,'coalesced','same_request',request_id=candidate['id']);return candidate['id']
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
                self.trigger_state(id,'cached','cache_hit',request_id=cached['request_id']);return cached['request_id']
        r=dict(id=uid(),action=body['action'],status='queued',created_at=now(),snapshot=snapshot,error=None,started_at=None,duration_ms=None)
        self.orchestration_counts['logical_request']+=1
        self.request_clocks[r['id']]=time.perf_counter()
        r['timing']=dict(policy_version=POLICY_VERSION,trigger='auto' if auto else 'manual',temperature='warm' if getattr(self.provider,'_client',None) is not None else 'cold',retrieval='semantic' if self.store.settings()['semantic_enabled'] and self.retrieval.semantic.ready else 'keyword',provider_mode='demo' if m['demo'] else 'real',outcome='queued',marks=[dict(stage='suggestion_scheduled',offset_ms=0)],provider_ms=0,validation_ms=0)
        stable=self.stable_times.get(id)
        if stable and stable['revision']==snapshot['transcript_revision']:r['timing']['stable_to_scheduled_ms']=(self.request_clocks[r['id']]-stable['at'])*1000
        self.task(self.emit('suggestion.scheduled',id,request_id=r['id'],segments=[dict(id=s['id'],revision=s['revision'],capture_epoch=s['capture_epoch']) for s in snapshot['segments']],automatic=auto))
        self.save_request(id,r)
        db=self.store.db_for(id)
        with db:m['latest_request']=r['id'];self.store.save_meeting(db,m)
        if id in self.queued:
            previous=self.queued.pop(id);previous['status']='superseded';self.finish_timing(previous);self.save_request(id,previous)
        self.queued[id]=r
        self.trigger_state(id,'queued','manual_priority' if not auto else 'auto_ready',request_id=r['id'],route=snapshot['routing']['route'])
        if id in self.active:
            if not auto:self.active[id].cancel()
        else:self.start_runner(id)
        return r['id']
    def start_runner(self,id):
        task=self.task(self.run_live(id));self.active[id]=task
        def done(finished):
            if self.active.get(id) is finished:self.active.pop(id,None)
            if id in self.queued and id not in self.active:self.start_runner(id)
            elif id in self.auto_batches and id not in self.active:self.arm_auto(id)
        task.add_done_callback(done)
    async def generate_suggestion(self, snapshot, request=None):
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
                if request:self.mark(request,'provider_started')
                started=time.perf_counter()
                correlation=provider_context.set(dict(request_id=request['id'] if request else None,automatic=request['action']=='auto' if request else None,generation_attempt=attempt+1,repair=attempt>0))
                try:output = await self.provider.complete(context, SuggestionPayload)
                finally:
                    provider_context.reset(correlation)
                    if request:
                        request['timing']['provider_ms']+=(time.perf_counter()-started)*1000
                        self.mark(request,'provider_completed')
                started=time.perf_counter()
                try:validate_suggestion(output, snapshot)
                finally:
                    if request:
                        request['timing']['validation_ms']+=(time.perf_counter()-started)*1000
                        self.mark(request,'validation_completed')
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
                r=self.queued.pop(id);self.running_requests[id]=r;began=time.perf_counter();r.update(status='running',started_at=now());self.save_request(id,r)
                stable=self.stable_times.get(id)
                if stable and stable['revision']==r['snapshot']['transcript_revision']:
                    r['stable_to_request_ms']=(began-stable['at'])*1000;self.stable_to_request.append(r['stable_to_request_ms']);self.stable_to_request=self.stable_to_request[-1000:]
                r['timing']['scheduler_wait_ms']=(began-self.request_clocks[r['id']])*1000
                r['timing']['retrieval_ms']=r['snapshot'].get('retrieval_ms')
                if r['action']=='auto':self.rate[id].append(time.monotonic())
                self.trigger_state(id,'processing','provider_generation',request_id=r['id'])
                await self.emit('suggestion.started',id,request_id=r['id'])
                try:
                    m=self.store.meeting(id)
                    try:
                        async with asyncio.timeout(self.store.settings()['live_timeout_s']):
                            output=demo_suggestion(r['snapshot']) if m['demo'] else await self.generate_suggestion(r['snapshot'],r)
                    except TimeoutError:raise AppError('PROVIDER_TIMEOUT','Live generation, including retry/repair, exceeded its total deadline',504,True)
                    if asyncio.current_task().cancelling():raise asyncio.CancelledError()
                    if self.store.meeting(id)['status']!='active':raise asyncio.CancelledError()
                    validation_started=time.perf_counter()
                    try:validate_suggestion(output,r['snapshot'])
                    finally:
                        r['timing']['validation_ms']+=(time.perf_counter()-validation_started)*1000;self.mark(r,'validation_completed')
                    m=self.store.meeting(id)
                    generations={s['id']:s['generation'] for s in self.store.sources(m['project_id'])}
                    content_stale=any(current['text']!=original['text'] for original in r['snapshot']['segments']+r['snapshot'].get('memory',[]) for current in self.store.transcript(id) if current['id']==original['id'])
                    equivalent=self.equivalent_changes_only(id,r['snapshot']) if m['transcript_revision']!=r['snapshot']['transcript_revision'] else False
                    stale=m['latest_request']!=r['id'] or generations!=r['snapshot']['index_generation'] or (content_stale and not equivalent) or (m['transcript_revision']!=r['snapshot']['transcript_revision'] and not equivalent) or m['self_speaker']!=r['snapshot'].get('self_speaker') or m.get('context_revision',0)!=r['snapshot'].get('context_revision',0) or self.store.project(m['project_id'])['glossary']!=r['snapshot'].get('glossary',{})
                    if equivalent:r['timing']['freshness_reason']='cosmetic_or_new_smalltalk_only'
                    stale=stale or m.get('memory_revision',0)!=r['snapshot'].get('memory_revision',0)
                    stale=stale or r['snapshot'].get('provider_config')!={key:self.store.settings()[key] for key in ('provider_url','model','output_tokens','input_chars','live_timeout_s')}
                    if r['action']=='auto' and not stale:
                        fingerprint=card_key(output,r['snapshot'])
                        duplicate=next((old for old in reversed(self.store.objects(id,'suggestions')[-8:]) if not old['stale'] and card_key(SuggestionPayload.model_validate(old['payload']),old['snapshot'])==fingerprint),None)
                        if duplicate:
                            r['status']='duplicate';r['reused_suggestion_id']=duplicate['id']
                            self.trigger_state(id,'cached','duplicate_card',request_id=r['id']);continue
                    # Explicit card actions may use an older immutable snapshot. Keep that fact visible.
                    r['timing']['outcome']='stale' if stale else 'ready'
                    s=dict(id=uid(),request_id=r['id'],created_at=now(),mode='demo' if m['demo'] else 'real',payload=output.model_dump(),snapshot=r['snapshot'],stale=stale,automatic=r['action']=='auto',duration_ms=(time.perf_counter()-began)*1000,timing=r['timing'])
                    db=self.store.db_for(id)
                    with db:db.execute('INSERT INTO suggestions VALUES(?,?,?,?)',(s['id'],id,r['id'],dumps(s)))
                    r['status']='stale' if stale else 'ready'
                    if stable and stable['revision']==r['snapshot']['transcript_revision']:
                        s['stable_to_validated_ms']=(time.perf_counter()-stable['at'])*1000;self.stable_to_ready.append(s['stable_to_validated_ms']);self.stable_to_ready=self.stable_to_ready[-1000:]
                    await self.emit('suggestion.stale' if stale else 'suggestion.ready',id,suggestion=s)
                    self.trigger_state(id,'stale' if stale else 'ready','validated_result',request_id=r['id'])
                except asyncio.CancelledError:
                    r['status']='cancelled';self.save_request(id,r)
                    await self.emit('suggestion.cancelled',id,request_id=r['id']);raise
                except Exception as e:
                    error=e.payload(r['id']) if isinstance(e,AppError) else AppError('AI_INTERNAL','Suggestion failed; no validated result was published',500).payload(r['id'])
                    r.update(status='error',error=error)
                    if self.store.meeting(id)['latest_request']==r['id']:self.trigger_state(id,'error',error['code'],request_id=r['id'])
                    await self.emit('suggestion.error',id,request_id=r['id'],error=error)
                finally:
                    r['duration_ms']=(time.perf_counter()-began)*1000
                    self.finish_timing(r)
                    self.running_requests.pop(id,None)
                    try:self.save_request(id,r)
                    except AppError:pass
        finally:
            pass  # The done callback also handles cancellation before the coroutine first starts.
    def cancel(self,id):
        if id in self.preparation_jobs:self.preparation_jobs.pop(id)['task'].cancel()
        if id in self.active:self.active[id].cancel()
        if id in self.queued:
            r=self.queued.pop(id);r['status']='cancelled';self.finish_timing(r);self.save_request(id,r)
        if id in self.auto_timers:self.auto_timers.pop(id).cancel()
        self.auto_batches.pop(id,None)
        self.seen_stable.pop(id,None)
        self.scheduler_states[id]=dict(state='listening',reason='session_control',policy_version=POLICY_VERSION)
    def auto(self,id,event):
        m=self.store.meeting(id)
        if event['stable']:self.stable_times[id]=dict(revision=m['transcript_revision'],at=time.perf_counter())
        prior=self.seen_stable.setdefault(id,{})
        participants={s['speaker'] for s in self.store.transcript(id) if s.get('speaker')}
        action,reason=decide(m,event,prior.get(event['segment_id']),participants)
        self.change_log.setdefault(id,deque(maxlen=128)).append(dict(revision=m['transcript_revision'],id=event['segment_id'],smalltalk=reason=='small_talk' and freshness_safe_smalltalk(event['text'])))
        if event['stable']:
            prior[event['segment_id']]=(event.get('speaker_label'),meaning_key(event['text']))
            while len(prior)>512:prior.pop(next(iter(prior)))
        if action in ('skip','wait'):
            if reason=='own_turn' and id in self.auto_batches:
                self.auto_batches.pop(id,None)
                if id in self.auto_timers:self.auto_timers.pop(id).cancel()
            if reason=='speaker_unfinished' and id in self.auto_batches:
                self.auto_batches[id]['blocked']=True
                if id in self.auto_timers:self.auto_timers.pop(id).cancel()
            self.trigger_state(id,'listening' if action=='skip' else 'waiting',reason);return
        current=time.monotonic();batch=self.auto_batches.get(id)
        delay=self.policy.question_wait_s if reason=='direct_question' else self.policy.information_wait_s
        if not batch:
            batch=dict(first=current,deadline=current+delay,focus=[]);self.auto_batches[id]=batch
            running=self.running_requests.get(id)
            if running and running['action']=='auto':batch['focus'].extend(running['snapshot'].get('focus_segment_ids',[]))
        batch['blocked']=False
        if event['segment_id'] not in batch['focus']:
            if len(batch['focus'])>=self.policy.max_focus:
                self.auto_batches.pop(id,None)
                if id in self.auto_timers:self.auto_timers.pop(id).cancel()
                self.trigger_state(id,'error','context_capacity');return
            batch['focus'].append(event['segment_id'])
        if reason=='meaningful_correction':batch['deadline']=min(current+delay,batch['first']+self.policy.max_batch_wait_s)
        else:batch['deadline']=min(batch['deadline'],current+delay,batch['first']+self.policy.max_batch_wait_s)
        if len(batch['focus'])>self.policy.max_focus:
            self.trigger_state(id,'waiting','context_capacity');batch['deadline']=current
        else:self.trigger_state(id,'coalesced' if len(batch['focus'])>1 else 'waiting',reason)
        self.arm_auto(id)
    def arm_auto(self,id):
        if id not in self.auto_batches or self.auto_batches[id].get('blocked'):return
        if id in self.auto_timers and not self.auto_timers[id].done():
            if abs(self.auto_batches[id]['deadline']-self.auto_deadlines.get(id,float('inf')))<.000001:return
            self.auto_timers.pop(id).cancel()
        self.auto_deadlines[id]=self.auto_batches[id]['deadline']
        async def later():
            try:
                batch=self.auto_batches.get(id)
                if not batch:return
                await asyncio.sleep(max(0,batch['deadline']-time.monotonic()))
                if self.preparing.get(id) or self.running_requests.get(id,{}).get('action') not in (None,'auto') or self.queued.get(id,{}).get('action') not in (None,'auto'):
                    self.trigger_state(id,'queued','behind_manual');return
                batch=self.auto_batches.pop(id,None)
                if batch:
                    body=dict(action='auto',_focus_segment_ids=batch['focus'])
                    if hasattr(self.retrieval,'search_async'):await self.schedule_async(id,body)
                    else:self.schedule(id,body)
            except asyncio.CancelledError:pass
            except AppError as error:
                self.trigger_state(id,'quota' if error.code=='AUTO_QUOTA' else 'error',error.code)
                await self.emit('suggestion.error',id,error=error.payload())
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
            correlation=provider_context.set(dict(request_id=original.get('report_job_id'),automatic=False,generation_attempt=attempt+1,repair=attempt>0,accounting=self.report_jobs.get(original.get('report_job_id'))))
            try:result=await self.provider.complete({k:v for k,v in context.items() if k!='report_job_id'},ReportPayload,True)
            finally:provider_context.reset(correlation)
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
            if len(parts)>64:raise AppError('REPORT_CAPACITY','Report exceeds 64 maps; no silent truncation',422)
            ledger=self.store.memory(id);memory_revision=m.get('memory_revision',0)
            for n,part in enumerate(parts):
                context=dict(segments=part,timezone=m['timezone'],meeting_started_at=m['started_at'],transcript_revision=revision,task='report map; preserve each requirement/decision/action/open question, with evidence. Summarize only supplied observations.')
                context['report_job_id']=job['id']
                async with asyncio.timeout(self.store.settings()['report_timeout_s']):
                    result=demo_report(part) if m['demo'] else await self.generate_report_part(context)
                validate_report(result,part)
                if any(len('\n'.join(filter(None,(getattr(payload,key),getattr(result,key)))))>15000 for key in ('summary_vi','summary_en')):
                    raise AppError('REPORT_SUMMARY_BUDGET','Combined map summaries exceed budget; no truncated summary was published. Previous versions are preserved.',422)
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
            from .report_ledger import reconcile_report
            payload,history,reconciliation=reconcile_report(payload,ledger,segments)
            if self.store.meeting(id).get('memory_revision',0)!=memory_revision:raise AppError('REVISION_CONFLICT','Memory changed during report; previous versions preserved',409)
            report=self.save_report(id,payload,revision,mode='demo' if m['demo'] else 'real',metadata=dict(memory_snapshot=ledger,memory_revision=memory_revision,historical_payload=history.model_dump(),reconciliation=reconciliation))
            job.update(status='ready',progress=100,report_id=report['id']);await self.emit('report.ready',id,report=report)
        except asyncio.CancelledError:job['status']='cancelled';raise
        except Exception as e:job.update(status='error',error=e.payload() if isinstance(e,AppError) else AppError('REPORT_ERROR','Report failed; previous versions were preserved',500).payload())
        finally:
            job['duration_ms']=(time.perf_counter()-began)*1000
            attempts=[r for r in getattr(self.provider,'metrics',[]) if r.get('logical_request_id')==job['id']]
            job['maps']=len(locals().get('parts',[]))
            for key in ('http_attempts','repair_attempts','transient_retry_attempts','usage_unknown_attempts'):job.setdefault(key,0)
            self.report_tasks.pop(job['id'],None)
    def save_report(self,id,payload,revision,mode='real',user_edits=False,reviewed=False,parent=None,metadata=None):
        db=self.store.db_for(id)
        with db:
            row=db.execute('SELECT MAX(version) FROM reports WHERE meeting_id=?',(id,)).fetchone()
            version=(row[0] or 0)+1
            report=dict(id=uid(),meeting_id=id,version=version,transcript_revision=revision,payload=payload.model_dump(),user_edits=user_edits,reviewed_at=now() if reviewed else None,mode=mode,created_at=now(),parent_id=parent)
            report.update(metadata or {});report.setdefault('evidence_snapshot',self.store.transcript(id))
            db.execute('INSERT INTO reports VALUES(?,?,?,?)',(report['id'],id,version,dumps(report)))
        return report
    def get_report(self,rid):
        for db in (self.store.ram,self.store.disk):
            row=db.execute('SELECT payload FROM reports WHERE id=?',(rid,)).fetchone()
            if row:return self.store.report_view(json.loads(row[0]))
        raise AppError('NOT_FOUND','Report not found',404)
    def edit_report(self,rid,body):
        old=self.get_report(rid);reports=self.store.objects(old['meeting_id'],'reports');current=reports[-1]
        if body.expected_version!=current['version']:raise AppError('VERSION_CONFLICT','Report changed. Your local edit is kept; reload or save against the current version.',409,current_version=current['version'])
        validate_report(body.payload,self.store.transcript(old['meeting_id']),user_edit=True)
        # Editable transcript fields are explicitly marked user edits when changed.
        for section in SECTIONS:
            originals={x['id']:x for x in old['payload'][section]}
            for item in getattr(body.payload,section):
                if item.model_dump()!=originals.get(item.id):item.origin='user_edit'
        metadata={k:old[k] for k in ('evidence_snapshot','memory_snapshot','memory_revision','historical_payload','reconciliation') if k in old}
        metadata['edit_provenance']=dict(actor='local_user',parent_id=rid,summary_changed=body.payload.summary_vi!=old['payload']['summary_vi'] or body.payload.summary_en!=old['payload']['summary_en'],changed_item_ids=[item.id for section in SECTIONS for item in getattr(body.payload,section) if item.origin=='user_edit'])
        return self.save_report(old['meeting_id'],body.payload,old['transcript_revision'],old['mode'],True,body.reviewed,rid,metadata)
    async def shutdown(self):
        for task in list(self.tasks):task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        for m in self.store.meetings():
            if m['status'] in ('active','paused'):self.store.control(m['id'],dict(action='interrupt',idempotency_key=uid(),reason='backend_shutdown'))
    def forget(self,id):
        self.cancel(id);self.rate.pop(id,None);self.stable_times.pop(id,None)
        if hasattr(self.retrieval,'forget_queries'):self.retrieval.forget_queries()
        self.scheduler_states.pop(id,None);self.seen_stable.pop(id,None);self.preparation_locks.pop(id,None);self.auto_deadlines.pop(id,None)
        self.change_log.pop(id,None)
        for key,job in list(self.report_jobs.items()):
            if job['meeting_id']==id and key in self.report_tasks:self.report_tasks.pop(key).cancel()
        self.report_jobs={k:v for k,v in self.report_jobs.items() if v['meeting_id']!=id}
