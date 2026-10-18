import {Outbox} from './outbox';
import type {CaptionProfile} from '../content/meet-adapter';
type Binding={session_id:string;tab_id:number;document_id:string;meeting_key:string;status:string;demo?:boolean};
type Config={url:string;token:string;profile?:CaptionProfile};
let config:Config={url:'http://127.0.0.1:8765',token:''};let binding:Binding|null=null;let outbox=new Outbox();let socket:WebSocket|null=null;
let authenticated=false;let bound=false;let reconnectTimer:ReturnType<typeof setTimeout>|undefined;let heartbeat:ReturnType<typeof setInterval>|undefined;let attempts=0;let blocked=false;let pendingGap=false;let ready:Promise<void>;
let serial=Promise.resolve<unknown>(undefined);
let captureTimings:number[]=[];
let interruptionGap=false;
let lastAdapterHeartbeat=Date.now();let adapterHeartbeatLost=false;
let captureRejected=false;let lastAdapterStatus='starting';
const extensionPage=(sender:chrome.runtime.MessageSender)=>sender.id===chrome.runtime.id && !!sender.url?.startsWith(chrome.runtime.getURL(''));
const meetingKey=(url:string)=>{const parsed=new URL(url);if(parsed.origin!=='https://meet.google.com')throw new Error('Chọn một tab Google Meet');return parsed.pathname;};
const configURL=(url:string)=>{const u=new URL(url);if(u.protocol!=='http:'||!['127.0.0.1','localhost'].includes(u.hostname)||u.port!=='8765'||u.pathname!=='/'||u.username||u.password||u.search||u.hash)throw new Error('Backend URL phải là http://127.0.0.1:8765 hoặc http://localhost:8765');return u.origin;};
const notify=(message:unknown)=>chrome.runtime.sendMessage(message).catch(()=>{});
const persist=()=>chrome.storage.session.set({binding,pending:outbox.items,pendingGap,interruptionGap,captureRejected,lastAdapterStatus});
const captureSend=(type:string,payload:unknown)=>{if(socket?.readyState===WebSocket.OPEN&&authenticated)socket.send(JSON.stringify({type,protocol_version:1,session_id:binding?.session_id,...(type==='caption.upsert'?{event_id:(payload as {event_id:string}).event_id}:{}),payload}));};
async function request(path:string,method='GET',body?:unknown){
  if(!path.startsWith('/api/v1/'))throw new Error('Invalid API route');
  const response=await fetch(config.url+path,{method,headers:{Authorization:'Bearer '+config.token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw new Error(data.message||data.code||`HTTP ${response.status}`);return data;
}
async function startCapture(){if(!binding||binding.demo)return;await chrome.tabs.sendMessage(binding.tab_id,{type:'capture.start',profile:config.profile||null}).catch(()=>notify({type:'transport.error',error:'Reload tab Meet để nạp content script'}));}
async function forgetSession(id:string){
  await chrome.storage.session.remove('reading_'+id);
  if(binding?.session_id===id){const tab=binding.tab_id;binding=null;bound=false;outbox=new Outbox();pendingGap=false;interruptionGap=false;await persist();if(tab>=0)await chrome.tabs.sendMessage(tab,{type:'capture.stop'}).catch(()=>{});}
}
async function reconcile(){
  try{
    const sessions=await request('/api/v1/meetings');const valid=new Set(sessions.map((m:{id:string})=>m.id));const values=await chrome.storage.session.get(null);
    for(const key of Object.keys(values))if(key.startsWith('reading_')&&!valid.has(key.slice(8)))await chrome.storage.session.remove(key);
    if(binding&&!valid.has(binding.session_id))await forgetSession(binding.session_id);
  }catch{/* Keep recoverable RAM state while backend is temporarily unavailable. */}
}
function connect(){
  if(socket && (socket.readyState===WebSocket.CONNECTING||socket.readyState===WebSocket.OPEN))return;
  if(blocked||!config.token)return;
  const ws=new WebSocket(config.url.replace('http:','ws:')+'/api/v1/events');socket=ws;authenticated=false;bound=false;
  ws.onopen=()=>ws.send(JSON.stringify({type:'auth',protocol_version:1,token:config.token}));
  ws.onmessage=event=>{
    if(socket!==ws)return;
    const msg=JSON.parse(String(event.data));
    if(msg.type==='auth.ok'){
      authenticated=true;attempts=0;void notify({type:'transport.status',status:'connected'});
      void reconcile().then(()=>{if(binding&&binding.status==='active'&&!binding.demo)captureSend('session.bind',{tab_id:binding.tab_id,document_id:binding.document_id,meeting_key:binding.meeting_key});});
      if(heartbeat)clearInterval(heartbeat);heartbeat=setInterval(()=>{
        captureSend('heartbeat',{});
        if(binding?.status==='active'&&!binding.demo&&Date.now()-lastAdapterHeartbeat>45000&&!adapterHeartbeatLost){captureSend('capture.status',{status:'unknown'});captureSend('capture.gap',{reason:'adapter_heartbeat_lost'});adapterHeartbeatLost=true;}
      },20000);
    }else if(msg.type==='auth.error'){blocked=true;ws.close();void notify({type:'transport.error',error:'Pairing token không hợp lệ'});}
    else if(msg.type==='session.snapshot' && binding && binding.session_id===msg.session_id){
      binding.status=msg.payload.snapshot.status;
      if(binding.status==='active'){
        bound=true;for(const p of outbox.items)captureSend('caption.upsert',p.event);
        if(pendingGap){captureSend('capture.gap',{reason:'outbox_overflow'});pendingGap=false;}
        if(interruptionGap){captureSend('capture.gap',{reason:'interrupted_pending_discarded'});interruptionGap=false;}
        void startCapture();
      }else bound=false;
      void persist();
    }else if(msg.type==='caption.ack'){
      if(msg.applied&&captureRejected){captureRejected=false;captureSend('capture.status',{status:lastAdapterStatus});}
      if(binding&&!binding.demo)void chrome.tabs.sendMessage(binding.tab_id,{type:'capture.ack',event_id:msg.event_id},{documentId:binding.document_id}).catch(()=>{});
      outbox.ack(msg.event_id);void persist();
    }else if(msg.type==='meeting.deleted'){
      void forgetSession(msg.payload.meeting_id);
    }else if(msg.type==='error'){
      if(msg.event_id&&outbox.items.some(p=>p.event.event_id===msg.event_id)){
        outbox.ack(msg.event_id);captureRejected=true;captureSend('capture.status',{status:'unknown'});captureSend('capture.gap',{reason:'event_rejected'});void persist();void notify({type:'transport.error',error:'Caption bị backend từ chối: '+msg.payload.message});
      }
      if(['SESSION_INTERRUPTED','SESSION_SCOPE','BINDING_SCOPE','NOT_FOUND'].includes(msg.payload?.code)){
        bound=false;void notify({type:'transport.error',error:msg.payload.message});
        if(binding){
          void chrome.tabs.sendMessage(binding.tab_id,{type:'capture.stop'}).catch(()=>{});
          if(msg.payload.code==='NOT_FOUND'){void chrome.storage.session.remove('reading_'+binding.session_id);binding=null;outbox=new Outbox();}
          else if(msg.payload.code==='SESSION_INTERRUPTED'){binding.status='interrupted';if(outbox.items.length)interruptionGap=true;outbox=new Outbox();}
          void persist();
        }
      }
    }
    void notify({type:'server.event',event:msg});
  };
  ws.onclose=event=>{
    if(socket!==ws)return;
    socket=null;authenticated=false;bound=false;if(heartbeat)clearInterval(heartbeat);
    void notify({type:'transport.status',status:'disconnected'});
    if(event.code===4401||event.code===4403){blocked=true;void notify({type:'transport.error',error:'Kiểm tra pairing token và extension ID ở backend'});return;}
    if(!blocked){const ms=Math.min(15000,1000*2**attempts++)+Math.random()*300;reconnectTimer=setTimeout(connect,ms);}
  };
}
async function handle(message:any,sender:chrome.runtime.MessageSender):Promise<any>{
  await ready;
  if(message.type?.startsWith('capture.') && sender.tab){
    if(sender.id!==chrome.runtime.id||!sender.url?.startsWith('https://meet.google.com/'))throw new Error('Untrusted caption sender');
    if(message.type==='capture.hello'){
      if(binding&&binding.tab_id===sender.tab.id&&binding.meeting_key===meetingKey(sender.url)&&sender.documentId){
        const changed=binding.document_id!==sender.documentId;binding.document_id=sender.documentId;await persist();
        if(changed&&binding.status==='active')captureSend('session.bind',{tab_id:binding.tab_id,document_id:binding.document_id,meeting_key:binding.meeting_key});
      }
      await chrome.storage.session.set({['document_'+sender.tab.id]:sender.documentId});return {ok:true};
    }
    if(message.type==='capture.profile'){
      config.profile=message.payload;await chrome.storage.local.set({config});
      if(binding?.status==='active')await startCapture();return {ok:true};
    }
    if(!binding||sender.tab.id!==binding.tab_id||sender.documentId!==binding.document_id||meetingKey(sender.url)!==binding.meeting_key)throw new Error('Caption belongs to an unbound tab/document');
    lastAdapterHeartbeat=Date.now();adapterHeartbeatLost=false;
    if(message.type==='capture.caption'&&binding.status==='active'){
      if(outbox.push(message.payload)>0)pendingGap=true;await persist();if(bound)captureSend('caption.upsert',message.payload);return {ok:true};
    }
    if(message.type==='capture.status'||message.type==='capture.heartbeat'){lastAdapterStatus=message.payload.status;if(bound)captureSend('capture.status',captureRejected?{status:'unknown'}:message.payload);}
    if(message.type==='capture.gap'&&bound)captureSend('capture.gap',message.payload);
    if(message.type==='capture.measurement'){
      const ms=message.payload?.duration_ms;if(typeof ms==='number'&&Number.isFinite(ms)&&ms>=0&&ms<=600000){captureTimings.push(ms);captureTimings=captureTimings.slice(-1000);await chrome.storage.session.set({captureTimings});void notify({type:'capture.timing',duration_ms:ms});}
    }
    return {ok:true};
  }
  if(!extensionPage(sender))throw new Error('Only extension UI may control sessions/settings');
  if(message.type==='ui.state')return {ok:true,config,binding,connected:authenticated,pending:outbox.items.length,extension_id:chrome.runtime.id,capture_timings:captureTimings};
  if(message.type==='ui.config'){
    config={...config,url:configURL(message.config.url),token:message.config.token};blocked=false;await chrome.storage.local.set({config});if(reconnectTimer)clearTimeout(reconnectTimer);
    const previous=socket;socket=null;previous?.close();connect();return {ok:true};
  }
  if(message.type==='ui.dashboard'){await chrome.tabs.create({url:chrome.runtime.getURL('dashboard.html')+'#'+(message.route||'/projects')});return {ok:true};}
  if(message.type==='ui.calibrate'){
    const tabs=await chrome.tabs.query({active:true,currentWindow:true});const tab=tabs[0];if(!tab?.id||!tab.url?.startsWith('https://meet.google.com/'))throw new Error('Mở tab Google Meet và bật caption trước');
    return chrome.tabs.sendMessage(tab.id,{type:'capture.calibrate'});
  }
  if(message.type==='ui.bind'){
    const m=await request('/api/v1/meetings/'+message.session_id);
    if(binding?.session_id!==m.id)captureRejected=false;
    if(m.demo){binding={session_id:m.id,tab_id:-1,document_id:'demo',meeting_key:'demo',status:m.status,demo:true};await persist();return {ok:true};}
    const tabs=await chrome.tabs.query({active:true,currentWindow:true});const tab=tabs[0];if(!tab?.id||!tab.url)throw new Error('Chọn tab Meet đang họp');
    const key=meetingKey(tab.url);if(m.meeting_key!==key)throw new Error('Phiên thuộc một meeting khác');
    const doc=(await chrome.storage.session.get('document_'+tab.id))['document_'+tab.id];if(!doc)throw new Error('Reload tab Meet để nhận document binding');
    binding={session_id:m.id,tab_id:tab.id,document_id:doc,meeting_key:key,status:m.status};await persist();connect();if(authenticated)captureSend('session.bind',{tab_id:tab.id,document_id:doc,meeting_key:key});return {ok:true};
  }
  if(message.type==='ui.meet-tab'){
    const tabs=await chrome.tabs.query({active:true,currentWindow:true});const tab=tabs[0];if(!tab?.id||!tab.url)throw new Error('Mở tab Meet trước');return {ok:true,meeting_key:meetingKey(tab.url)};
  }
  if(message.type==='ui.control'){
    if(!binding)throw new Error('Chưa có binding');let flushTimeout=false;
    if(message.action==='end'&&!binding.demo){
      await chrome.tabs.sendMessage(binding.tab_id,{type:'capture.flush'}).catch(()=>{});
      await new Promise(resolve=>setTimeout(resolve,40));await serial;
      const until=Date.now()+2000;
      while(outbox.items.length&&Date.now()<until)await new Promise(resolve=>setTimeout(resolve,30));
      if(outbox.items.length){flushTimeout=true;captureSend('capture.gap',{reason:'end_flush_timeout'});}
    }
    const result=await request('/api/v1/meetings/'+binding.session_id+'/control','POST',{action:message.action,idempotency_key:message.idempotency_key,...(flushTimeout?{reason:'end_flush_timeout'}:{})});binding.status=result.status;
    if(message.action==='resume'&&!binding.demo){if(authenticated)captureSend('session.bind',{tab_id:binding.tab_id,document_id:binding.document_id,meeting_key:binding.meeting_key});else connect();}
    else if(!binding.demo)await chrome.tabs.sendMessage(binding.tab_id,{type:'capture.stop'}).catch(()=>{});
    if(message.action==='end'){outbox=new Outbox();pendingGap=false;}await persist();return {ok:true,result};
  }
  throw new Error('Unknown extension command');
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(['server.event','transport.status','transport.error','capture.timing'].includes(message.type))return false;
  const work=message.type?.startsWith('capture.')?(serial=serial.then(()=>handle(message,sender),()=>handle(message,sender))):handle(message,sender);
  work.then(respond).catch(error=>respond({ok:false,error:String(error.message)}));return true;
});
async function interrupt(reason:string){if(!binding||!['active','paused'].includes(binding.status))return;await request('/api/v1/meetings/'+binding.session_id+'/control','POST',{action:'interrupt',idempotency_key:crypto.randomUUID(),reason}).catch(()=>{});binding.status='interrupted';bound=false;await persist();}
chrome.tabs.onRemoved.addListener(tabId=>{void ready.then(async()=>{if(binding?.tab_id===tabId)await interrupt('tab_closed');});});
chrome.tabs.onUpdated.addListener((tabId,change)=>{if(change.url||change.status==='loading')void ready.then(async()=>{
  if(binding?.tab_id===tabId){let changed=true;try{const tab=await chrome.tabs.get(tabId);changed=meetingKey(change.url||tab.url||'')!==binding.meeting_key;}catch{/* New origin is outside the granted Meet host permission. */}if(changed)await interrupt('tab_navigated');}
}).catch(()=>{});});
chrome.runtime.onInstalled.addListener(()=>{void chrome.sidePanel.setPanelBehavior({openPanelOnActionClick:true});});
chrome.alarms.onAlarm.addListener(()=>void ready.then(()=>connect()));
ready=(async()=>{
  await chrome.storage.local.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'});await chrome.storage.session.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'});
  const local=await chrome.storage.local.get('config');config={...config,...local.config};const state=await chrome.storage.session.get(['binding','pending','pendingGap','captureTimings','interruptionGap','captureRejected','lastAdapterStatus']);binding=state.binding||null;outbox=new Outbox(state.pending||[]);pendingGap=state.pendingGap||false;captureTimings=state.captureTimings||[];interruptionGap=state.interruptionGap||false;captureRejected=state.captureRejected||false;lastAdapterStatus=state.lastAdapterStatus||'starting';
  if(binding){try{const m=await request('/api/v1/meetings/'+binding.session_id);binding.status=m.status;}catch{}}
  await chrome.alarms.create('transport-recovery',{periodInMinutes:1});connect();
})();
