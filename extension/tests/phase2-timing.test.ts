import {it,expect} from 'vitest';
import {CaptureTiming} from '../src/content/capture-timing';
import type {CaptionEvent} from '../src/content/caption-reducer';
it('correlates exact revision in one monotonic clock; wall-clock jumps do not affect durations',()=>{
  let at=10;const records:Record<string,unknown>[]=[];const clock=new CaptureTiming(r=>records.push(r),()=>at);
  const e:CaptionEvent={type:'caption.upsert',protocol_version:1,event_id:'e',capture_epoch:'epoch',segment_id:'s',revision:1,seq:1,speaker_label:null,text:'SECRET_TRANSCRIPT',observed_at:'1990-01-01T00:00:00Z',stable:false,adapter_version:'fixture'};
  clock.observe(e);at=40;clock.ack('e');clock.ack('e');expect(records).toHaveLength(1);expect(records[0].observed_to_ack_ms).toBe(30);
  at=1010;clock.observe({...e,event_id:'stable',revision:2,stable:true});at=2010;
  const payload={request_id:'r',automatic:true,stale:false,segments:[{id:'s',revision:2,capture_epoch:'epoch'}]};clock.scheduled(payload);at=3010;clock.rendered(payload);
  expect(records[1].stable_to_schedule_received_ms).toBe(1000);expect(records[2].observed_to_rendered_notification_ms).toBe(3000);expect(records[2].stable_to_rendered_notification_ms).toBe(2000);
  clock.rendered({...payload,segments:[{id:'s',revision:3,capture_epoch:'epoch'}]});expect(records).toHaveLength(3);
  expect(JSON.stringify(records)).not.toContain('SECRET_TRANSCRIPT');
});
