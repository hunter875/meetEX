import {useEffect,useReducer,useState} from 'react';
import {Play,Pause,Square,Pin,Copy,ArrowRight,Sparkles,MessageSquare,ChevronRight,Settings2,Radio,ScanLine,FileText,Send} from 'lucide-react';
import {useApp,useLoad,runtime,inExtension,navigate} from './api';
import {Action,Button,ErrorBox,Loading,Pill,Modal,Drawer,SourceDetails,dateTime} from './shared';
import {readingReducer,emptyReading} from './card-reducer';
import {MeetingMemory} from './memory';
import type {Project,Meeting,Snapshot,Settings,Suggestion,Segment,Citation,RoutingDecision} from './types';
type ResponseMode='auto'|'fast'|'explain'|'deep'|'clarify';
const routeLabels:Record<RoutingDecision['route'],string>={fast:'Trả lời nhanh',explain:'Giải thích',deep:'Phân tích sâu',clarify:'Hỏi lại / xác minh',listen:'Tiếp tục nghe'};
function RoutingInfo({decision,preview=false}:{decision:RoutingDecision;preview?:boolean}){
  return <div className="routing-info small" data-testid={preview?'routing-preview':'routing-result'}>
    <div className="row wrap"><Pill tone={decision.requires_verification?'amber':'green'}>{routeLabels[decision.route]}</Pill><span className="muted">{preview?'Dự kiến · chưa gọi AI':decision.source==='manual'?'Chế độ bạn chọn':'Tự phân loại'}</span></div>
    {decision.route!=='listen'&&<p className="muted">Mục tiêu xử lý: {decision.target_min_s}–{decision.target_max_s}s · chưa phải thời gian được bảo đảm</p>}
    <details><summary>Vì sao chọn luồng này?</summary>{decision.reasons.map((reason,i)=><p key={i}>{reason}</p>)}</details>
    {decision.requires_verification&&<p className="warning">Cần xác minh trước khi chốt hoặc cam kết.</p>}
  </div>;
}
const statusLabels:Record<string,string>={starting:'Đang nhận diện',observing:'Đang quan sát phụ đề',waiting_for_caption:'Đang chờ phụ đề',captions_off:'Phụ đề đang tắt',unsupported_dom:'Chưa có vùng phụ đề phù hợp',paused:'Đang tạm dừng',disconnected:'Capture mất kết nối',meeting_left:'Đã kết thúc',unknown:'Chưa xác định trạng thái phụ đề'};
const schedulerLabels:Record<string,string>={waiting:'Đang gom nội dung mới.',processing:'Đang xử lý.',listening:'Tiếp tục nghe.',coalesced:'Đang gom nội dung mới.',queued:'Đã ghi nhận, đang chờ xử lý.',cached:'Đã có gợi ý cho nội dung này.',quota:'Đã chạm giới hạn tự động; bạn vẫn có thể tạo gợi ý thủ công.',ready:'Đã có gợi ý mới.',stale:'Kết quả cũ không còn phù hợp.',error:'Chưa xử lý được; bạn có thể thử thủ công.'};
export function Live({sidepanel=false}:{sidepanel?:boolean}){
  const {api,state,refresh,toast,revision}=useApp();const projects=useLoad<Project[]>('/api/v1/projects');const meetings=useLoad<Meeting[]>('/api/v1/meetings');const settings=useLoad<Settings>('/api/v1/settings');
  const [selectedSession,setSelectedSession]=useState<string|null>(sessionStorage.getItem('meet-ui-session'));const [forceNew,setForceNew]=useState(false);
  const sessionId=forceNew?null:selectedSession||state?.binding?.session_id||meetings.data?.find(m=>['active','paused','interrupted'].includes(m.status))?.id||null;
  const meeting=useLoad<Snapshot>(sessionId?'/api/v1/meetings/'+sessionId:null);const snapshot=meeting.data;
  const [projectId,setProjectId]=useState('');const [title,setTitle]=useState('Cuộc họp dự án');const [demo,setDemo]=useState(false);const [memory,setMemory]=useState(false);
  const [transcript,setTranscript]=useState(false);const [selectedSegments,setSelectedSegments]=useState<string[]>([]);const [question,setQuestion]=useState('');const [demoText,setDemoText]=useState('We will NOT deploy on Friday. Maybe Monday, but we need to confirm.');const [drawer,setDrawer]=useState<Citation[]|null>(null);const [transcriptQuery,setTranscriptQuery]=useState('');
  const [reading,dispatch]=useReducer(readingReducer,emptyReading);const [restored,setRestored]=useState(false);
  const [snapshotEvidence,setSnapshotEvidence]=useState<Segment[]|null>(null);
  const [responseMode,setResponseMode]=useState<ResponseMode>('auto');const [routePreview,setRoutePreview]=useState<RoutingDecision|null>(null);const [routeError,setRouteError]=useState('');
  useEffect(()=>{
    const card=reading.current;
    if(!inExtension||!card||!sessionId)return;
    let second=0;
    const first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>void runtime({type:'ui.card_rendered',meeting_id:sessionId,payload:{request_id:card.request_id,automatic:card.automatic,stale:card.stale,segments:card.snapshot.segments.map(s=>({id:s.id,revision:s.revision,capture_epoch:s.capture_epoch}))}}).catch(()=>{}));});
    return ()=>{cancelAnimationFrame(first);cancelAnimationFrame(second);};
  },[reading.current?.id,sessionId]);
  useEffect(()=>{setResponseMode('auto');setQuestion('');setSelectedSegments([]);},[sessionId]);
  useEffect(()=>{
    setRoutePreview(null);setRouteError('');
    if(!sessionId||snapshot?.status!=='active'||!snapshot.segments.length)return;
    let alive=true;
    const timer=setTimeout(()=>{void api<RoutingDecision>('/api/v1/meetings/'+sessionId+'/classify','POST',{
      action:question.trim()||responseMode!=='auto'?'suggest':'auto',question,response_mode:responseMode,selected_segment_ids:selectedSegments,
    }).then(value=>{if(alive)setRoutePreview(value);}).catch(error=>{if(alive)setRouteError((error as Error).message);});},350);
    return ()=>{alive=false;clearTimeout(timer);};
  },[sessionId,snapshot?.status,snapshot?.transcript_revision,snapshot?.self_speaker,question,responseMode,selectedSegments,api,revision]);
  useEffect(()=>{setRestored(false);dispatch({type:'restore',state:emptyReading});if(!sessionId){setRestored(true);return;}
    let alive=true;const key='reading_'+sessionId;
    const load=inExtension?chrome.storage.session.get(key).then(r=>r[key]):Promise.resolve(JSON.parse(sessionStorage.getItem(key)||'null'));
    load.then(r=>{if(alive){if(r)dispatch({type:'restore',state:r});setRestored(true);}});return ()=>{alive=false;};
  },[sessionId]);
  useEffect(()=>{if(restored&&sessionId){const key='reading_'+sessionId;if(inExtension)void chrome.storage.session.set({[key]:{...reading,saved_at:Date.now()}}).then(async()=>{const values=await chrome.storage.session.get(null);const old=Object.keys(values).filter(k=>k.startsWith('reading_')&&k!==key).sort((a,b)=>(values[b].saved_at||0)-(values[a].saved_at||0)).slice(4);if(old.length)await chrome.storage.session.remove(old);}).catch(()=>{});else sessionStorage.setItem(key,JSON.stringify(reading));}},[reading,restored,sessionId]);
  useEffect(()=>{
    for(const request of snapshot?.requests||[])if(['error','cancelled','superseded','duplicate'].includes(request.status))dispatch({type:'finished',request_id:request.id});
  },[snapshot?.requests]);
  useEffect(()=>{if(restored)for(const suggestion of snapshot?.suggestions||[])dispatch({type:'offer',suggestion});},[snapshot?.suggestions,restored]);
  useEffect(()=>{if(!sessionId)return;const timer=setInterval(()=>api<Snapshot>('/api/v1/meetings/'+sessionId).then(meeting.setData).catch(()=>{}),2000);return ()=>clearInterval(timer);},[sessionId,api]);
  useEffect(()=>{if(settings.data)setMemory(settings.data.persistence_mode==='memory');},[settings.data?.persistence_mode]);
  const current=reading.current;const currentServer=snapshot?.suggestions.find(s=>s.id===current?.id);const latest=snapshot?.segments.at(-1);const lastRequest=snapshot?.requests.at(-1);const processing=snapshot?.requests.some(r=>['running','queued'].includes(r.status));
  async function start(){
    const pid=projectId||projects.data?.[0]?.id;if(!pid)throw new Error('Tạo hoặc chọn dự án trước');
    let key:string|null=null;if(!demo){if(!sidepanel)throw new Error('Mở side panel ở tab Google Meet để bắt đầu capture thật');key=(await runtime({type:'ui.meet-tab'})).meeting_key;}
    const result=await api<Meeting>('/api/v1/meetings','POST',{project_id:pid,title,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,persistence_mode:memory?'memory':'local',demo,meeting_key:key});
    if(inExtension){try{await runtime({type:'ui.bind',session_id:result.id});}catch(error){await api('/api/v1/meetings/'+result.id+'/control','POST',{action:'interrupt',idempotency_key:crypto.randomUUID(),reason:'binding_failed'});throw error;}}
    setForceNew(false);setSelectedSession(result.id);sessionStorage.setItem('meet-ui-session',result.id);refresh();
  }
  async function control(action:string){
    if(!snapshot)return;
    if(inExtension&&state?.binding?.session_id===snapshot.id)await runtime({type:'ui.control',action,idempotency_key:crypto.randomUUID()});
    else {await api('/api/v1/meetings/'+snapshot.id+'/control','POST',{action,idempotency_key:crypto.randomUUID()});if(inExtension&&action==='resume'&&!snapshot.demo)await runtime({type:'ui.bind',session_id:snapshot.id});}
    refresh();
  }
  async function suggest(action='suggest',base?:Suggestion,mode:ResponseMode=responseMode){
    if(!snapshot)return;
    const payload={action,question,base_suggestion_id:base?.id,selected_segment_ids:base?[]:selectedSegments,response_mode:mode};
    const result=await api('/api/v1/meetings/'+snapshot.id+'/suggest','POST',payload);dispatch({type:'manual',request_id:result.request_id});refresh();
  }
  async function openCitations(){if(!current||!snapshot)return;setDrawer(await api('/api/v1/meetings/'+snapshot.id+'/suggestions/'+current.id+'/citations'));}
  const goReport=()=>{const route='/meetings/'+snapshot?.id+'/report';if(sidepanel&&inExtension)void runtime({type:'ui.dashboard',route});else navigate(route);};
  return <div className={'live-view '+(sidepanel?'compact':'')}>
    {!sidepanel&&<div className="page-title"><div><div className="eyebrow">TRỢ LÝ CUỘC HỌP</div><h1>Đang họp</h1><p>Hiểu ý bằng tiếng Việt. Trả lời bằng tiếng Anh đơn giản.</p></div><Pill tone="green"><Radio size={12}/> Captions → local → AI</Pill></div>}
    {sidepanel&&<header className="panel-brand"><div className="brand-mark"><MessageSquare size={19}/></div><strong>meet<span>copilot</span></strong><Button variant="ghost" aria-label="Mở dashboard" onClick={()=>void runtime({type:'ui.dashboard'})}><Settings2 size={17}/></Button></header>}
    <ErrorBox error={meeting.error||projects.error}/>
    {!snapshot?<section className="panel start-panel"><div className="live-symbol"><Radio size={26}/></div><h2>Sẵn sàng cho cuộc họp</h2><p className="muted">Bật phụ đề tiếng Anh trong Google Meet, chọn dự án và bắt đầu.</p>
      <label>Dự án<select aria-label="Dự án cho phiên" value={projectId||projects.data?.[0]?.id||''} onChange={e=>setProjectId(e.target.value)}>{!projects.data?.length&&<option value="">Chưa có dự án</option>}{projects.data?.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label>Tên phiên<input value={title} onChange={e=>setTitle(e.target.value)}/></label>
      <label className="check-label"><input type="checkbox" checked={memory} onChange={e=>setMemory(e.target.checked)}/> Chỉ lưu RAM cho phiên này</label><p className="small muted">{memory?'Phụ đề, gợi ý và báo cáo sẽ mất khi backend/Chrome khởi động lại.':'Lưu local trên máy; mặc định giữ '+(settings.data?.retention_days||30)+' ngày.'}</p>
      <label className="check-label"><input type="checkbox" checked={demo} onChange={e=>setDemo(e.target.checked)}/> Chế độ demo có nhãn (không cần Meet/API key)</label>
      {!sidepanel&&!demo&&<div className="info-strip small">Capture thật chạy trong side panel. Mở Meet rồi nhấn biểu tượng extension.</div>}
      <Action variant="primary" disabled={!projects.data?.length||!title.trim()} run={start}><Play size={16}/> {demo?'Bắt đầu demo':'Bắt đầu phiên'}</Action>
      {!projects.data?.length&&<Button variant="ghost" onClick={()=>sidepanel?void runtime({type:'ui.dashboard',route:'/projects'}):navigate('/projects')}>Tạo dự án trước <ArrowRight size={14}/></Button>}
      {sidepanel&&<Action run={async()=>{await runtime({type:'ui.calibrate'});toast('Đã lưu profile từ DOM vừa chọn. Kiểm tra phụ đề trước khi dùng.');}}><ScanLine size={16}/> Chọn vùng phụ đề Meet</Action>}
    </section>:<>
      {snapshot.demo&&<div className="demo-banner"><Sparkles size={15}/> DEMO · Caption thử và controlled provider; chưa kiểm chứng Meet/AI thật.</div>}
      {snapshot.status==='active'&&snapshot.scheduler&&<div className="info-strip small" data-testid="scheduler-state">{snapshot.scheduler.reason==='speaker_unfinished'?'Đang chờ người nói kết thúc.':schedulerLabels[snapshot.scheduler.state]||'Tiếp tục nghe.'}</div>}
      {snapshot.persistence_mode==='memory'&&<div className="subtle-banner">Phiên chỉ lưu RAM · mất khi backend/Chrome khởi động lại</div>}
      <section className="session-header"><div className="session-project"><span className="eyebrow">{projects.data?.find(p=>p.id===snapshot.project_id)?.name||'DỰ ÁN ĐÃ KHÓA'}</span><h2>{snapshot.title}</h2></div><div className="status-grid"><span><i className={'dot '+(state?.connected||!inExtension?'green':'red')}/>{inExtension?(state?.connected?'Backend kết nối':'Backend mất kết nối'):'Backend REST'}</span><span><i className={'dot '+((state?.capture_diagnostics?.adapter_status||snapshot.capture_status)==='observing'?'green':'amber')}/>{snapshot.demo?'Phụ đề demo':statusLabels[state?.capture_diagnostics?.adapter_status||snapshot.capture_status]||snapshot.capture_status}</span></div><div className="small muted">Caption gần nhất: {dateTime(snapshot.last_caption_at)}</div>
        {state?.capture_diagnostics&&<p className="small muted" data-testid="capture-diagnostics">Content script: {state.capture_diagnostics.content_alive?'còn sống':'chưa xác nhận'} · Adapter: {statusLabels[state.capture_diagnostics.adapter_status]} · Chờ ACK: {state.pending}{state.capture_diagnostics.pending_gap?' · Có nguy cơ thiếu dữ liệu':''}</p>}<div className="row wrap controls">{snapshot.status==='active'?<Action run={()=>control('pause')}><Pause size={14}/> Tạm dừng</Action>:['paused','interrupted'].includes(snapshot.status)?<Action variant="primary" run={()=>control('resume')}><Play size={14}/> Tiếp tục</Action>:null}{snapshot.status!=='ended'?<Action run={async()=>{await control('end');}}><Square size={14}/> Kết thúc</Action>:<><Button onClick={goReport}><FileText size={14}/> Mở báo cáo</Button><Button onClick={()=>{setForceNew(true);setSelectedSession(null);sessionStorage.removeItem('meet-ui-session');}}>Phiên mới</Button></>}
          {!snapshot.demo&&sidepanel&&<Action run={async()=>{await runtime({type:'ui.calibrate'});toast('Đã chọn vùng caption. Hãy thử nói và đối chiếu.');}}><ScanLine size={14}/> Chọn DOM</Action>}
        </div>{snapshot.status==='interrupted'&&<p className="text-error small">Phiên bị gián đoạn. Chủ động tiếp tục tại đúng tab hoặc kết thúc với phần đã thu.</p>}
      </section>
      {!!snapshot.confirmed_segment_ids?.length&&<div className="subtle-banner">{snapshot.confirmed_segment_ids.length} đoạn được bạn chọn làm ngữ cảnh đã xác nhận <Action variant="ghost" run={async()=>{await api('/api/v1/meetings/'+snapshot.id,'PATCH',{confirmed_segment_ids:[]});refresh();}}>Bỏ chọn ngữ cảnh</Action></div>}
      {Number(snapshot.memory_revision_warnings)>0&&<div className="subtle-banner">Caption đã sửa ngữ cảnh từng được xác nhận; đoạn bị sửa đã được bỏ khỏi memory. Hãy xem lại transcript.</div>}
      {!snapshot.demo&&snapshot.capture_status==='unsupported_dom'&&<div className="info-strip small">Chọn vùng phụ đề đang hiển thị bằng “Chọn DOM”. Adapter chưa được kiểm chứng với Meet thật trên máy này.</div>}
      <div className="live-columns"><div className="understanding-column"><section className="panel caption-card"><div className="section-title"><span className="eyebrow">01 / ĐOẠN VỪA NÓI</span><Button variant="ghost" onClick={()=>setTranscript(true)}>Transcript <ChevronRight size={13}/></Button></div>
        {latest?<><div className="row small"><span className="speaker-dot"/>{latest.speaker||'Chưa rõ người nói'}{!latest.stable&&<Pill tone="amber">Đang thay đổi</Pill>}</div><p className="caption-text">{latest.text}</p></>:<p className="muted">Chưa có phụ đề. Capture chỉ thu phần quan sát sau khi bắt đầu.</p>}
        {snapshot.segments.length>0&&<label className="small inline-label">Tôi là<select aria-label="Participant là Tôi" value={snapshot.self_speaker||''} onChange={async e=>{try{await api('/api/v1/meetings/'+snapshot.id,'PATCH',{self_speaker:e.target.value||null});refresh();}catch(e){toast((e as Error).message);}}}><option value="">Chưa xác định</option>{Array.from(new Set(snapshot.segments.map(s=>s.speaker).filter(Boolean))).map(s=><option key={s!} value={s!}>{s}</option>)}</select></label>}
        {!snapshot.self_speaker&&<p className="muted small">Chưa biết ai là bạn. Auto chờ chọn “Tôi”; tạo thủ công vẫn dùng được.</p>}
      </section>
      <section className="panel meaning-card"><div className="section-title"><span className="eyebrow">02 / HIỂU Ý & ĐỐI CHIẾU</span><Sparkles size={16}/></div>{current?<><p className="meaning-text">{current.payload.meaning_vi}</p>{current.payload.findings.map((f,i)=><div className="finding" key={i}><p>{f.text_vi}</p><Button variant="ghost" onClick={()=>void openCitations()}>Xem {f.source_ids.length} căn cứ <ChevronRight size={12}/></Button></div>)}<div className="row wrap"><Pill tone={current.payload.evidence_status==='supported'?'green':'amber'}>{{supported:'Có căn cứ',partial:'Căn cứ một phần',missing:'Thiếu căn cứ dự án',conflicting:'Nguồn mâu thuẫn'}[current.payload.evidence_status]}</Pill><Button variant="ghost" onClick={()=>void openCitations()}>Mở nguồn</Button></div>{current.payload.uncertainties.map((u,i)=><p key={i} className="uncertainty small">↳ {u}</p>)}</>:<p className="muted">Gợi ý sẽ kèm nghĩa tiếng Việt và nguồn được truy xuất. Chưa có nguồn sẽ được ghi rõ.</p>}</section></div>
      <section className={'panel reply-card '+(reading.pinned?'pinned':'')}><div className="section-title"><span className="eyebrow">03 / CÂU TRẢ LỜI GỢI Ý</span><Button aria-pressed={reading.pinned} variant="ghost" onClick={()=>dispatch({type:'pin'})} disabled={!current}><Pin size={15}/>{reading.pinned?'Đang giữ':'Giữ câu'}</Button></div>
        {current?<><div className="reply-language"><Pill tone="green">EN · A2–B1</Pill><span className="muted small">{dateTime(current.created_at)}</span></div><p className="english-reply" data-testid="english-reply">{current.payload.reply_en}</p><p className="reply-translation">{current.payload.reply_vi}</p>{(currentServer?.stale||current.stale)&&<p className="small warning">Dùng snapshot cũ · kiểm tra lại với hội thoại/nguồn mới.</p>}<div className="reply-meta small muted">Snapshot r{current.snapshot.transcript_revision} · {current.payload.supporting_segment_ids.length} đoạn hội thoại · {(current.duration_ms/1000).toFixed(1)}s</div><div className="row wrap reply-actions"><Action disabled={snapshot.status!=='active'} run={()=>suggest('shorter',current,'fast')}>Ngắn hơn</Action><Action disabled={snapshot.status!=='active'} run={()=>suggest('explain',current,'explain')}>Giải thích</Action><Action disabled={snapshot.status!=='active'} run={()=>suggest('ask',current,'deep')}>Phân tích sâu</Action><Action disabled={snapshot.status!=='active'} run={()=>suggest('clarify',current,'clarify')}>Hỏi lại</Action><Action run={async()=>{await navigator.clipboard.writeText(current.payload.reply_en);toast('Đã copy câu tiếng Anh');}}><Copy size={14}/> Copy</Action></div>{current.payload.clarification_en&&<div className="clarification"><span className="small muted">Câu hỏi làm rõ</span><p>{current.payload.clarification_en}</p></div>}</>:<div className="reply-placeholder"><MessageSquare size={30}/><h3>Đợi một chút để hiểu đúng.</h3><p>Thu một đoạn phụ đề rồi tạo gợi ý. Câu trả lời sẽ xuất hiện ở đây.</p></div>}
        {reading.pending&&<Button className="new-suggestion" variant="primary" onClick={()=>dispatch({type:'next'})}>Có gợi ý mới <ArrowRight size={15}/></Button>}
        {current?.snapshot.routing&&<RoutingInfo decision={current.snapshot.routing}/>}
        {lastRequest?.status==='skipped'&&lastRequest.snapshot.routing&&<RoutingInfo decision={lastRequest.snapshot.routing}/>}
        {processing&&lastRequest?.snapshot.routing&&<p className="small muted">Đang chạy: {routeLabels[lastRequest.snapshot.routing.route]}</p>}
        {processing&&<p className="ai-processing" role="status">Đang xử lý AI · chỉ hiển thị khi JSON và nguồn hợp lệ…</p>}
        {lastRequest?.error&&<div role="alert" className="error small">{String(lastRequest.error.message||lastRequest.error.code)}</div>}
        <div className="manual-box"><label>Chế độ trả lời<select aria-label="Chế độ trả lời" value={responseMode} onChange={e=>setResponseMode(e.target.value as ResponseMode)}><option value="auto">Tự phân loại</option><option value="fast">Trả lời nhanh</option><option value="explain">Giải thích</option><option value="deep">Phân tích sâu · 2–3 hướng</option><option value="clarify">Hỏi lại / xác minh</option></select></label><p className="small muted">Lựa chọn áp dụng cho lần gửi thủ công. Auto vẫn tự phân loại.</p><label>Hỏi AI<textarea aria-label="Hỏi AI" value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Ví dụ: giải thích yêu cầu này, hoặc hỏi lại về môi trường…" rows={2}/></label>{routePreview&&<RoutingInfo decision={routePreview} preview/>}{routeError&&<p className="small text-error" role="alert">Không phân loại được: {routeError}</p>}<div className="row wrap"><Action variant="primary" disabled={snapshot.status!=='active'||!snapshot.segments.length} run={()=>suggest(question?'ask':'suggest')}><Send size={14}/> Tạo gợi ý{selectedSegments.length?` (${selectedSegments.length} đoạn)`:''}</Action><label className="check-label small"><input type="checkbox" checked={snapshot.auto_mode} onChange={async e=>{await api('/api/v1/meetings/'+snapshot.id,'PATCH',{auto_mode:e.target.checked});refresh();}}/> Auto</label></div></div>
      </section></div>
      <MeetingMemory meetingId={snapshot.id}/>
      {snapshot.demo&&snapshot.status==='active'&&<section className="panel demo-input"><div className="section-title"><h3>Phụ đề thử (demo)</h3><Pill tone="amber">Synthetic input</Pill></div><label>Nội dung demo<textarea aria-label="Phụ đề demo" value={demoText} onChange={e=>setDemoText(e.target.value)}/></label><Action run={async()=>{await api('/api/v1/meetings/'+snapshot.id+'/demo-caption','POST',{type:'caption.upsert',protocol_version:1,event_id:crypto.randomUUID(),capture_epoch:'demo-ui',segment_id:crypto.randomUUID(),revision:1,seq:snapshot.transcript_revision+1,speaker_label:'Demo Client',text:demoText,stable:true,observed_at:new Date().toISOString(),adapter_version:'demo-v1'});refresh();}}>Thêm đoạn demo</Action></section>}
      {snapshot.gaps.length>0&&<details className="gaps"><summary>{snapshot.gaps.length} khoảng capture thiếu / tạm dừng</summary>{snapshot.gaps.map((g,i)=><p className="small muted" key={i}>{String(g.reason)} · {String(g.from_at)} → {String(g.to_at||'Chưa xác định')} · {String(g.certainty)}</p>)}</details>}
    </>}
    {transcript&&snapshot&&<Modal title="Transcript đã quan sát" onClose={()=>setTranscript(false)}><input aria-label="Tìm transcript" placeholder="Tìm trong phụ đề…" value={transcriptQuery} onChange={e=>setTranscriptQuery(e.target.value)}/><div className="transcript-list">{snapshot.segments.filter(s=>s.text.toLowerCase().includes(transcriptQuery.toLowerCase())).map((s:Segment)=><label className="transcript-row" key={s.id}><input type="checkbox" checked={selectedSegments.includes(s.id)} onChange={e=>setSelectedSegments(prev=>e.target.checked?[...prev,s.id]:prev.filter(x=>x!==s.id))}/><div><span className="small muted">{s.speaker||'Chưa rõ người nói'} · r{s.revision} · {dateTime(s.observed_to)}</span><p>{s.text}</p></div></label>)}</div><div className="row wrap"><Button variant="primary" onClick={()=>setTranscript(false)}>Dùng {selectedSegments.length} đoạn đã chọn</Button><Action disabled={!selectedSegments.length} run={async()=>{await api('/api/v1/meetings/'+snapshot.id,'PATCH',{confirmed_segment_ids:Array.from(new Set([...(snapshot.confirmed_segment_ids||[]),...selectedSegments]))});refresh();toast('Đã chọn nguyên văn làm ngữ cảnh đã xác nhận. Prompt dùng tối đa 8 đoạn trong budget.');}}>Lưu làm ngữ cảnh đã xác nhận</Action></div></Modal>}
    {snapshot&&current&&<Button variant="ghost" onClick={()=>setSnapshotEvidence([...current.snapshot.segments,...(current.snapshot.memory||[])].filter(s=>current.payload.supporting_segment_ids.includes(s.id)))}>Xem đoạn hội thoại đã dùng cho card</Button>}
    {snapshotEvidence&&<Drawer title="Snapshot hội thoại của card" onClose={()=>setSnapshotEvidence(null)}>{snapshotEvidence.map((s,i)=><div className="evidence-item" key={s.id+'-'+i}><Pill>{s.speaker||'Chưa rõ người nói'}</Pill><p>{s.text}</p><p className="mono muted small">{s.id} · revision {s.revision}</p></div>)}</Drawer>}
    {drawer&&<Drawer title="Bằng chứng dự án" onClose={()=>setDrawer(null)}>{drawer.length?drawer.map(s=><section className="citation-section" key={s.id}><SourceDetails source={s}/></section>):<p className="muted">Snapshot này không có nguồn dự án. Không suy ra status hoặc deadline từ dữ liệu thiếu.</p>}</Drawer>}
  </div>;
}
