import {it,expect} from 'vitest';
import {CaptionReducer,type CaptionEvent} from '../src/content/caption-reducer';
import cases from '../../fixtures/phase2/caption-replay.json';
import {CaptionReducer as LegacyReducer} from './legacy/caption-reducer';

type Constructor = new (emit:(e:CaptionEvent)=>void)=>Pick<CaptionReducer,'update'|'prime'|'tick'>;
function replay(fixture:typeof cases[number],Reducer:Constructor=CaptionReducer){
  const events:CaptionEvent[]=[];const reducer=new Reducer(e=>events.push(e));
  for(const step of fixture.steps){
    if(step.op==='tick')reducer.tick(step.at);
    else if(step.op==='prime')reducer.prime(step.blocks,step.at);
    else reducer.update(step.blocks,step.at);
  }
  const latest=new Map<string,CaptionEvent>();
  for(const event of events){
    expect(event.revision).toBe((latest.get(event.segment_id)?.revision||0)+1);
    latest.set(event.segment_id,event);
  }
  return [...latest.values()].map(e=>({speaker:e.speaker_label,text:e.text,revision:e.revision}));
}
for(const fixture of cases)it(`synthetic replay: ${fixture.id}`,()=>{
  expect(replay(fixture)).toEqual(fixture.expected);
});
it('positive control: shipped Phase 1 reducer fails the unchanged numeric correction replay',()=>{
  const fixture=cases.find(c=>c.id==='numeric-task-correction')!;
  expect(replay(fixture,LegacyReducer)).not.toEqual(fixture.expected);
});
