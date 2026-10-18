import {it,expect} from 'vitest';
import {readingReducer,emptyReading} from '../src/ui/card-reducer';
import type {Suggestion} from '../src/ui/types';
const card=(id:string,created_at:string)=>({id,request_id:id,created_at,stale:false} as Suggestion);
it('late old offers cannot replace a newer card or newer pending badge',()=>{
  let state=readingReducer(emptyReading,{type:'offer',suggestion:card('new','2026-10-18T12:00:02Z')});
  state=readingReducer(state,{type:'offer',suggestion:card('old','2026-10-18T12:00:01Z')});expect(state.current?.id).toBe('new');
  state=readingReducer(state,{type:'pin'});state=readingReducer(state,{type:'offer',suggestion:card('later','2026-10-18T12:00:04Z')});state=readingReducer(state,{type:'offer',suggestion:card('middle','2026-10-18T12:00:03Z')});expect(state.current?.id).toBe('new');expect(state.pending?.id).toBe('later');
});
it('explicit pinned-card action accepts its held snapshot, errors only clear matching manual intent',()=>{
  let state=readingReducer(emptyReading,{type:'offer',suggestion:card('new','2026-10-18T12:00:02Z')});state=readingReducer(state,{type:'pin'});state=readingReducer(state,{type:'manual',request_id:'held'});
  state=readingReducer(state,{type:'offer',suggestion:card('held','2026-10-18T12:00:01Z')});expect(state.current?.id).toBe('held');expect(state.pinned).toBe(true);
  state=readingReducer(state,{type:'manual',request_id:'new-request'});state=readingReducer(state,{type:'finished',request_id:'old-request'});expect(state.manualRequest).toBe('new-request');state=readingReducer(state,{type:'finished',request_id:'new-request'});expect(state.manualRequest).toBeNull();
});
