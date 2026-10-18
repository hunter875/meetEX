import {describe,it,expect,beforeEach,afterEach,vi} from 'vitest';
import {CaptionReducer,type CaptionEvent} from '../src/content/caption-reducer';
import {DOMCaptionAdapter,type CaptionProfile} from '../src/content/meet-adapter';
describe('CAP-01/02/03 reducer contracts',()=>{
  it('revises one partial and preserves negation, punctuation and numbers',()=>{
    const events:CaptionEvent[]=[];const reducer=new CaptionReducer(e=>events.push(e));
    reducer.update([{key:'node',speaker:'Client',text:'Can we'}],100);
    reducer.update([{key:'node',speaker:'Client',text:'Can we NOT deploy API-17 on Friday?'}],300);
    reducer.tick(1400);
    expect(new Set(events.map(e=>e.segment_id)).size).toBe(1);
    expect(events.map(e=>e.revision)).toEqual([1,2,3]);
    expect(events.at(-1)?.text).toBe('Can we NOT deploy API-17 on Friday?');
    expect(events.at(-1)?.stable).toBe(true);
  });
  it('keeps two speakers saying Yes and a repeated Yes after another turn',()=>{
    const events:CaptionEvent[]=[];const r=new CaptionReducer(e=>events.push(e));
    r.update([{key:'a',speaker:'A',text:'Yes'}],10);r.tick(1100);
    r.update([{key:'a',speaker:'B',text:'Yes'}],1200);r.tick(2300);
    r.update([{key:'a',speaker:'B',text:'No'}],2400);r.tick(3500);
    r.update([{key:'a',speaker:'B',text:'Yes'}],3600);
    expect(new Set(events.map(e=>e.segment_id)).size).toBe(4);
  });
  it('reconciles replaced/reparented nodes in the same visible turn',()=>{
    const events:CaptionEvent[]=[];const r=new CaptionReducer(e=>events.push(e));
    r.update([{key:'old',speaker:'A',text:'The fix needs testing'}],10);
    r.update([{key:'new',speaker:'A',text:'The fix needs testing'}],20);
    r.update([{key:'new',speaker:'A',text:'The fix does NOT need testing'}],30);
    expect(new Set(events.map(e=>e.segment_id)).size).toBe(1);
    expect(events.at(-1)?.revision).toBe(2);
  });
  it('finalizes a disappearing partial and accepts late correction of a stable turn',()=>{
    const events:CaptionEvent[]=[];const r=new CaptionReducer(e=>events.push(e));
    r.update([{key:'a',speaker:null,text:'Deploy Friday'}],10);r.update([],50);
    expect(events.at(-1)?.stable).toBe(true);
    r.update([{key:'b',speaker:null,text:'We will deploy on Friday'}],100);r.tick(1200);
    const id=events.at(-1)!.segment_id;
    r.update([{key:'b',speaker:null,text:'We will NOT deploy on Friday'}],1300);
    expect(events.at(-1)?.segment_id).toBe(id);
    expect(events.at(-1)?.text).toContain('NOT');
  });
  it('does not backfill the turn already rendered at start or resume',()=>{
    const events:CaptionEvent[]=[];const r=new CaptionReducer(e=>events.push(e));
    r.prime([{key:'a',speaker:'Client',text:'Already on screen'}],10);r.tick(1200);
    r.update([{key:'a',speaker:'Client',text:'Already on screen before capture'}],1300);r.tick(2400);
    expect(events).toEqual([]);
    r.update([{key:'b',speaker:'Next',text:'New speaker turn'}],2500);
    expect(events[0].text).toBe('New speaker turn');
  });
});
describe('CAP-04/05/06 calibrated DOM adapter fixture (not live Meet)',()=>{
  const profile:CaptionProfile={root:'#captions',block:'.block',text:'.words',speaker:'.speaker',toggle:'#toggle',version:'fixture-v1',calibrated_at:'2026-10-17T00:00:00Z'};
  beforeEach(()=>{vi.useFakeTimers();document.body.innerHTML='<button id="toggle" aria-pressed="true">Captions</button><section id="captions"></section><aside id="chat">CHAT_SENTINEL</aside>';});
  afterEach(()=>{vi.useRealTimers();document.body.replaceChildren();});
  it('silence for 60 seconds is waiting_for_caption, not captions_off',()=>{
    const statuses:string[]=[];const adapter=new DOMCaptionAdapter(profile,()=>{},s=>statuses.push(s));adapter.start();vi.advanceTimersByTime(60000);
    expect(adapter.getStatus()).toBe('waiting_for_caption');expect(statuses).not.toContain('captions_off');adapter.stop();
  });
  it('only reads the calibrated caption container and reattaches replacement',()=>{
    const events:CaptionEvent[]=[];let gaps=0;const adapter=new DOMCaptionAdapter(profile,e=>events.push(e),()=>{},undefined,()=>gaps++);adapter.start();
    document.querySelector('#captions')!.innerHTML='<div class="block"><span class="speaker">A</span><span class="words">API-17 needs testing</span></div>';
    vi.advanceTimersByTime(550);vi.advanceTimersByTime(1500);
    const segment=events[0].segment_id;
    const old=document.querySelector('#captions')!;const clone=old.cloneNode(true);old.replaceWith(clone);vi.advanceTimersByTime(600);
    expect(gaps).toBeGreaterThan(0);expect(new Set(events.map(e=>e.segment_id))).toEqual(new Set([segment]));
    expect(events.map(e=>e.text).join(' ')).not.toContain('CHAT_SENTINEL');adapter.stop();
  });
  it('reports off only with explicit toggle evidence; missing DOM becomes unknown',()=>{
    const adapter=new DOMCaptionAdapter(profile,()=>{},()=>{});adapter.start();document.querySelector('#toggle')!.setAttribute('aria-pressed','false');vi.advanceTimersByTime(600);expect(adapter.getStatus()).toBe('captions_off');
    document.querySelector('#toggle')!.setAttribute('aria-pressed','true');document.querySelector('#captions')!.remove();vi.advanceTimersByTime(600);expect(adapter.getStatus()).toBe('unknown');adapter.stop();
  });
  it('never calls an uncalibrated page observing',()=>{
    const adapter=new DOMCaptionAdapter(null,()=>{},()=>{});adapter.start();expect(adapter.getStatus()).toBe('unsupported_dom');adapter.stop();
  });
});
