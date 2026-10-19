import {it,expect} from 'vitest';
import {Outbox} from '../src/background/outbox';
import {readingReducer,emptyReading} from '../src/ui/card-reducer';
import type {Suggestion} from '../src/ui/types';
import type {CaptionEvent} from '../src/content/caption-reducer';
function event(n:number):CaptionEvent{return {type:'caption.upsert',protocol_version:1,event_id:String(n),capture_epoch:'e',segment_id:'s',revision:n,seq:n,speaker_label:null,text:'NOT Friday '+n,observed_at:new Date().toISOString(),stable:false,adapter_version:'fixture'};}
function card(id:string,revision=1):Suggestion{return {id,request_id:id,created_at:'2026-10-17T00:00:00Z',mode:'demo',payload:{input_revision:revision,intent:'other',meaning_vi:'Nghĩa '+id,findings:[],reply_en:'Reply '+id,reply_vi:id,clarification_en:'',evidence_status:'missing',uncertainties:[],supporting_segment_ids:['s']},snapshot:{meeting_id:'m',project_id:'p',transcript_revision:revision,index_generation:{},segments:[],memory:[],sources:[],action:'suggest',question:'',input_hash:id,context_omitted_count:0,source_omitted_count:0,response_mode:'auto',memory_revision:0,ledger_omitted_count:0},stale:false,automatic:false,duration_ms:2};}
it('TRN-03 preserves retry IDs across worker reconstruction and removes only ACKed events',()=>{
  const box=new Outbox();box.push(event(1));box.push(event(2));const restarted=new Outbox(JSON.parse(JSON.stringify(box.items)));
  expect(restarted.items.map(p=>p.event.event_id)).toEqual(['1','2']);restarted.ack('1');restarted.ack('1');expect(restarted.items[0].event.revision).toBe(2);
});
it('TRN-03 bounds outbox by count and UTF-8 bytes and reports overflow',()=>{
  const box=new Outbox([],2,20000);expect(box.push(event(1))).toBe(0);box.push(event(2));expect(box.push(event(3))).toBe(1);expect(box.items.map(p=>p.event.event_id)).toEqual(['2','3']);
  const bytes=new Outbox([],500,50);expect(bytes.push(event(1))).toBe(1);expect(bytes.items).toEqual([]);
});
it('AI-06/UX-02 pin holds the full card; new suggestions wait until explicitly accepted',()=>{
  let state=readingReducer(emptyReading,{type:'offer',suggestion:card('A')});state=readingReducer(state,{type:'pin'});const original=JSON.stringify(state.current);
  state=readingReducer(state,{type:'offer',suggestion:card('B',2)});
  expect(JSON.stringify(state.current)).toBe(original);expect(state.pending?.id).toBe('B');
  state=readingReducer(state,{type:'next'});expect(state.current?.id).toBe('B');expect(state.pinned).toBe(false);
});
it('UX-02 explicit shorter action applies A while B stays queued; stale automatic output cannot replace it',()=>{
  let state=readingReducer(emptyReading,{type:'offer',suggestion:card('A')});state=readingReducer(state,{type:'pin'});state=readingReducer(state,{type:'offer',suggestion:card('B',2)});state=readingReducer(state,{type:'manual',request_id:'shortA'});
  state=readingReducer(state,{type:'offer',suggestion:{...card('shortA'),stale:true}});
  expect(state.current?.id).toBe('shortA');expect(state.pending?.id).toBe('B');expect(state.pinned).toBe(true);
  state=readingReducer(state,{type:'offer',suggestion:{...card('old'),stale:true,automatic:true}});expect(state.current?.id).toBe('shortA');
});
