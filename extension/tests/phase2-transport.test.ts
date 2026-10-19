import {beforeEach,afterEach,it,expect,vi} from 'vitest';
type Listener=(message:any,sender:any,respond:(r:any)=>void)=>boolean;
let listener:Listener,session:Record<string,any>,meeting:any,sockets:Socket[],sent:any[],tabsSent:any[];
const doc={id:'extension',url:'https://meet.google.com/room',documentId:'doc',tab:{id:1}};
const ui={id:'extension',url:'chrome-extension://extension/dashboard.html'};
class Socket {
  static OPEN=1;static CONNECTING=0;readyState=0;onopen?:()=>void;onclose?:(e:any)=>void;onmessage?:(e:any)=>void;
  constructor(_url:string){sockets.push(this);}
  send(raw:string){sent.push(JSON.parse(raw));}
  close(){this.readyState=3;this.onclose?.({code:1006});}
  receive(message:any){this.onmessage?.({data:JSON.stringify(message)});}
}
async function settle(){for(let i=0;i<40;i++)await Promise.resolve();}
const event=(revision=1)=>({type:'caption.upsert',protocol_version:1,event_id:'event-'+revision,capture_epoch:'epoch',segment_id:'s',revision,seq:revision,speaker_label:'A',text:'NOT 15.5 API-17',observed_at:'2026-10-18T00:00:00Z',stable:true,adapter_version:'synthetic'});
async function command(type:string,payload?:any,sender:any=doc,extra:any={}){
  const result=new Promise<any>(resolve=>listener({type,payload,...extra},sender,resolve));await settle();return result;
}
async function connected(){
  const ws=sockets.at(-1)!;ws.readyState=1;ws.onopen?.();ws.receive({type:'auth.ok'});await settle();
  ws.receive({type:'session.snapshot',session_id:'meeting',payload:{snapshot:{status:'active'}}});await settle();return ws;
}
async function boot(){
  await import('../src/background/index');await settle();
}
beforeEach(async()=>{
  vi.useFakeTimers();vi.resetModules();session={binding:{session_id:'meeting',tab_id:1,document_id:'doc',meeting_key:'/room',status:'active'}};sockets=[];sent=[];tabsSent=[];meeting={id:'meeting',meeting_key:'/room',status:'active'};
  const storage=(values:Record<string,any>)=>({setAccessLevel:async()=>{},get:async(keys:any)=>keys===null?structuredClone(values):Object.fromEntries((Array.isArray(keys)?keys:[keys]).map((k:string)=>[k,structuredClone(values[k])])),set:async(value:any)=>{Object.assign(values,structuredClone(value));},remove:async(key:string)=>{delete values[key];},clear:async()=>{for(const key of Object.keys(values))delete values[key];}});
  vi.stubGlobal('WebSocket',Socket);
  vi.stubGlobal('fetch',vi.fn(async(_url:string,options:any)=>{
    if(_url.endsWith('/ready'))return {ok:true,json:async()=>({ready:true,protocol_version:1,app_version:'0.1.0'})};
    if(_url.endsWith('/control')){const action=JSON.parse(options.body).action;meeting.status=action==='resume'?'active':action==='pause'?'paused':action==='end'?'ended':'interrupted';}
    return {ok:true,json:async()=>structuredClone(_url.endsWith('/meetings')?[meeting]:meeting)};
  }));
  vi.stubGlobal('chrome',{storage:{session:storage(session),local:storage({config:{url:'http://127.0.0.1:8765',token:'TEST_PAIRING_ONLY'}})},runtime:{id:'extension',getURL:(s:string)=>'chrome-extension://extension/'+s,sendMessage:async()=>{},onMessage:{addListener:(fn:Listener)=>{listener=fn;}},onInstalled:{addListener:()=>{}}},tabs:{sendMessage:async(...args:any[])=>{tabsSent.push(args);return {ok:true};},query:async()=>[{id:1,url:doc.url}],get:async()=>({url:doc.url}),onRemoved:{addListener:()=>{}},onUpdated:{addListener:()=>{}}},alarms:{create:async()=>{},onAlarm:{addListener:()=>{}}},sidePanel:{setPanelBehavior:async()=>{}}});
  await boot();
});
afterEach(()=>{vi.clearAllTimers();vi.useRealTimers();vi.unstubAllGlobals();});
it.each([5000,20000])('buffers actual worker commands during %i ms outage and resends identical IDs',async(duration)=>{
  const ws=await connected();await command('capture.caption',event(1));ws.close();
  await command('capture.caption',event(2));await vi.advanceTimersByTimeAsync(duration);
  const restored=await connected();const captions=sent.filter(m=>m.type==='caption.upsert');
  expect(captions.filter(m=>m.payload.event_id==='event-1').length).toBeGreaterThanOrEqual(2);expect(captions.at(-1).payload.revision).toBe(2);
  restored.receive({type:'caption.ack',event_id:'event-1',applied:true});restored.receive({type:'caption.ack',event_id:'event-2',applied:true});await settle();expect(session.pending).toEqual([]);
});
it('lost ACK on a live socket retries after two seconds with the same event ID',async()=>{
  const ws=await connected();await command('capture.caption',event());await vi.advanceTimersByTimeAsync(3100);
  expect(sent.filter(m=>m.type==='caption.upsert').map(m=>m.payload.event_id)).toEqual(['event-1','event-1']);
  ws.receive({type:'caption.ack',event_id:'event-1',applied:true});await settle();await vi.advanceTimersByTimeAsync(5000);expect(sent.filter(m=>m.type==='caption.upsert')).toHaveLength(2);
});
it.each([{...doc,tab:{id:2}},{...doc,documentId:'old'},{...doc,url:'https://meet.google.com/other'}])('rejects unbound tab/document/meeting $documentId $url',async(sender)=>{
  await connected();expect((await command('capture.caption',event(),sender)).ok).toBe(false);expect(session.pending||[]).toEqual([]);
});
it('rejects another tab overwriting the active caption calibration',async()=>{
  expect((await command('capture.profile',{root:'body'},{...doc,tab:{id:2}})).ok).toBe(false);
});
it('reload interrupts, discards old document pending events, and requires explicit resume',async()=>{
  await connected();await command('capture.caption',event());await command('capture.hello',{}, {...doc,documentId:'new'});
  expect(session.binding.status).toBe('interrupted');expect(session.pending).toEqual([]);expect(session.interruptionGap).toBe(true);expect(session.binding.document_id).toBe('new');
  const state=await command('ui.state',undefined,ui);expect(state.capture_diagnostics.adapter_status).toBe('disconnected');
});
it('worker reconstruction keeps pending event IDs and does not need an open side panel',async()=>{
  const ws=await connected();await command('capture.caption',event());ws.close();vi.clearAllTimers();vi.resetModules();await boot();
  const restarted=await connected();expect(sent.filter(m=>m.type==='caption.upsert').at(-1).payload.event_id).toBe('event-1');
  restarted.receive({type:'caption.ack',event_id:'event-1',applied:true});await settle();expect(session.pending).toEqual([]);
});
it.each(['pause','end'])('%s discards pending with explicit gap reason; no event from pause is queued',async(action)=>{
  await connected();await command('capture.caption',event());
  const resultPromise=command('ui.control',undefined,ui,{action,idempotency_key:'control'});await vi.advanceTimersByTimeAsync(2200);const result=await resultPromise;
  expect(result.ok).toBe(true);expect(session.pending).toEqual([]);
  await command('capture.caption',event(2));expect(session.pending).toEqual([]);
  const controls=(fetch as any).mock.calls.filter((c:any[])=>c[0].endsWith('/control'));expect(JSON.parse(controls.at(-1)[1].body).reason).toBe(action==='end'?'end_flush_timeout':'interrupted_pending_discarded');
});
it('overflow stays bounded and publishes an explicit gap after reconnect',async()=>{
  await connected();sockets.at(-1)!.close();
  for(let n=1;n<=501;n++)await command('capture.caption',event(n));
  expect(session.pending).toHaveLength(500);expect(session.pendingGap).toBe(true);await vi.advanceTimersByTimeAsync(2000);await connected();
  expect(sent.some(m=>m.type==='capture.gap'&&m.payload.reason==='outbox_overflow')).toBe(true);
});
it('backend interrupted after restart discards pending rather than replaying into resumed session',async()=>{
  await connected();await command('capture.caption',event());vi.clearAllTimers();meeting.status='interrupted';vi.resetModules();await boot();
  expect(session.pending).toEqual([]);expect(session.interruptionGap).toBe(true);expect(session.binding.status).toBe('interrupted');
});
it('a heartbeat proves content liveness while selector failure still reports unsupported_dom',async()=>{
  await connected();await command('capture.heartbeat',{status:'unsupported_dom'});
  const state=await command('ui.state',undefined,ui);expect(state.capture_diagnostics.content_alive).toBe(true);expect(state.capture_diagnostics.adapter_status).toBe('unsupported_dom');
  await vi.advanceTimersByTimeAsync(46000);expect((await command('ui.state',undefined,ui)).capture_diagnostics.adapter_status).toBe('unknown');
});
it('diagnostic loss markers survive lost ACK and are removed only by matching gap ACK',async()=>{
  const ws=await connected();await command('capture.gap',{reason:'adapter_replaced'});const first=sent.filter(m=>m.type==='capture.gap').at(-1).payload;
  await vi.advanceTimersByTimeAsync(1100);expect(sent.filter(m=>m.type==='capture.gap').at(-1).payload.event_id).toBe(first.event_id);expect(session.pendingReasons).toContain('adapter_replaced');
  ws.receive({type:'capture.gap.ack',event_id:first.event_id,reason:first.reason});await settle();expect(session.pendingReasons).toEqual([]);
});

it('Phase5 disconnect clears credentials and temporary content, stops capture and reconnect',async()=>{
  await connected();await command('capture.caption',event());session.reading_meeting={text:'SYNTHETIC'};
  const result=await command('ui.disconnect',undefined,ui);expect(result.ok).toBe(true);
  expect((await command('ui.state',undefined,ui)).config.token).toBe('');expect(session.pending).toEqual([]);expect(session.reading_meeting).toBeUndefined();expect(session.binding).toBeNull();
  const count=sockets.length;await vi.advanceTimersByTimeAsync(120000);expect(sockets).toHaveLength(count);
  expect(tabsSent.some(c=>c[1].type==='capture.stop')).toBe(true);
});
it('Phase5 invalid auth blocks reconnection until explicit re-pair',async()=>{
  const ws=await connected();ws.receive({type:'auth.error'});await settle();
  expect((await command('ui.state',undefined,ui)).pairing_status).toBe('invalid');const count=sockets.length;
  await vi.advanceTimersByTimeAsync(120000);expect(sockets).toHaveLength(count);
  await command('ui.config',undefined,ui,{config:{url:'http://127.0.0.1:8765',token:'NEW_TEST_PAIRING'}});expect(sockets).toHaveLength(count+1);
});
it('Phase5 incompatible protocol stops before opening/authenticating a socket',async()=>{
  const count=sockets.length;vi.clearAllTimers();vi.resetModules();
  (fetch as any).mockImplementation(async(url:string)=>({ok:true,json:async()=>url.endsWith('/ready')?{ready:true,protocol_version:999,app_version:'9.0.0'}:url.endsWith('/meetings')?[meeting]:meeting}));
  await boot();expect(sockets).toHaveLength(count);expect((await command('ui.state',undefined,ui)).pairing_status).toBe('incompatible');
});
