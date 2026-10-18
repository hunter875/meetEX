import {it,expect,beforeEach,afterEach,vi} from 'vitest';
import {DOMCaptionAdapter,type CaptionProfile} from '../src/content/meet-adapter';
import type {CaptionEvent} from '../src/content/caption-reducer';
const profile:CaptionProfile={root:'#captions',block:'.block',text:'.words',speaker:'.speaker',toggle:'#toggle',version:'synthetic-v2',calibrated_at:'2026-10-18T00:00:00Z'};
let adapter:DOMCaptionAdapter;
beforeEach(()=>{vi.useFakeTimers();document.body.innerHTML='<button id="toggle" aria-pressed="true"></button><section id="captions"></section><aside id="chat">Minh: NOT 15.5 API-17</aside>';});
afterEach(()=>{adapter?.stop();vi.useRealTimers();document.body.replaceChildren();});
const block=(text:string,speaker='A')=>{const b=document.createElement('div');b.className='block';const s=document.createElement('span');s.className='speaker';s.textContent=speaker;const t=document.createElement('span');t.className='words';t.textContent=text;b.append(s,t);return b;};
it('missing text selector never reports observing forever; recovery reads only caption root',()=>{
  const events:CaptionEvent[]=[];adapter=new DOMCaptionAdapter(profile,e=>events.push(e),()=>{});adapter.start();
  document.querySelector('#captions')!.innerHTML='<div class="block"><span>Selector changed</span></div>';vi.advanceTimersByTime(500);
  expect(adapter.getStatus()).toBe('unsupported_dom');
  document.querySelector('#captions')!.replaceChildren(block('Minh:\nNOT API-17','Client'));vi.advanceTimersByTime(500);
  expect(adapter.getStatus()).toBe('observing');expect(events.at(-1)?.speaker_label).toBe('Client');expect(events.at(-1)?.text).toBe('Minh:\nNOT API-17');
  expect(events.some(e=>e.text.includes('15.5'))).toBe(false);
});
it('off disconnects observer and stops publishing; on returns to scoped observation',async()=>{
  const events:CaptionEvent[]=[];adapter=new DOMCaptionAdapter(profile,e=>events.push(e),()=>{});adapter.start();
  document.querySelector('#toggle')!.setAttribute('aria-pressed','false');vi.advanceTimersByTime(500);
  document.querySelector('#captions')!.append(block('Caption while OFF'));await Promise.resolve();vi.advanceTimersByTime(1500);
  expect(events).toEqual([]);expect(adapter.getStatus()).toBe('captions_off');
  document.querySelector('#toggle')!.setAttribute('aria-pressed','true');vi.advanceTimersByTime(500);expect(adapter.getStatus()).toBe('observing');
});
it('delivered mutation batches capture short turns before the watchdog/debounce',async()=>{
  const events:CaptionEvent[]=[];adapter=new DOMCaptionAdapter(profile,e=>events.push(e),()=>{});adapter.start();
  const a=block('Yes');document.querySelector('#captions')!.append(a);await Promise.resolve();a.remove();await Promise.resolve();
  expect(events[0]?.text).toBe('Yes');expect(events.at(-1)?.stable).toBe(true);
});
it('stop cleans observer/timers; a replacement adapter primes existing caption without duplicate capture',async()=>{
  const events:CaptionEvent[]=[];adapter=new DOMCaptionAdapter(profile,e=>events.push(e),()=>{});adapter.start();
  document.querySelector('#captions')!.append(block('Before recalibration'));await Promise.resolve();
  adapter.stop();const count=events.length;document.querySelector('.words')!.textContent='During recalibration';await Promise.resolve();vi.advanceTimersByTime(1500);expect(events).toHaveLength(count);
  adapter=new DOMCaptionAdapter(profile,e=>events.push(e),()=>{});adapter.start();vi.advanceTimersByTime(1500);expect(events).toHaveLength(count);
  document.querySelector('#captions')!.replaceChildren(block('New turn','B'));await Promise.resolve();expect(events.at(-1)?.text).toBe('New turn');
  adapter.stop();expect(vi.getTimerCount()).toBe(0);
});
it.each(['body','html','[broken'])('refuses broad or malformed root %s',root=>{
  const events:CaptionEvent[]=[];adapter=new DOMCaptionAdapter({...profile,root},e=>events.push(e),()=>{});adapter.start();vi.advanceTimersByTime(2000);expect(adapter.getStatus()).toBe('unsupported_dom');expect(events).toEqual([]);
});
it('container loss is unknown, silence is waiting, and replacement is a visible possible gap',()=>{
  let gaps=0;adapter=new DOMCaptionAdapter(profile,()=>{},()=>{},undefined,()=>gaps++);adapter.start();vi.advanceTimersByTime(60000);expect(adapter.getStatus()).toBe('waiting_for_caption');
  document.querySelector('#captions')!.remove();vi.advanceTimersByTime(500);expect(adapter.getStatus()).toBe('unknown');
  const root=document.createElement('section');root.id='captions';document.body.append(root);vi.advanceTimersByTime(500);expect(adapter.getStatus()).toBe('waiting_for_caption');expect(gaps).toBeGreaterThan(0);
});
