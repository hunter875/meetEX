import type {CaptionEvent} from './caption-reducer';
type Mark={observed:number;stable?:number};
type Ref={id:string;revision:number;capture_epoch:string};
export class CaptureTiming {
  private events=new Map<string,{ref:Ref;mark:Mark}>();
  private revisions=new Map<string,Mark>();
  private latest=new Map<string,Mark>();
  constructor(private record:(r:Record<string,unknown>)=>void,private clock=()=>performance.now()){}
  private key(s:Ref){return `${s.capture_epoch}/${s.id}/${s.revision}`;}
  observe(e:CaptionEvent){
    const ref={id:e.segment_id,revision:e.revision,capture_epoch:e.capture_epoch};
    const at=this.clock(),key=`${e.capture_epoch}/${e.segment_id}`;
    const previous=this.latest.get(key);
    const mark={observed:e.stable&&previous?previous.observed:at,...(e.stable?{stable:at}:{})};
    this.latest.set(key,mark);this.revisions.set(this.key(ref),mark);this.events.set(e.event_id,{ref,mark});
    for(const map of [this.latest,this.revisions,this.events])while(map.size>1000)map.delete(map.keys().next().value!);
  }
  ack(event_id:string){
    const event=this.events.get(event_id);if(!event)return;
    this.events.delete(event_id);
    this.record({stage:'ack_received',event_id,segment_id:event.ref.id,revision:event.ref.revision,observed_to_ack_ms:this.clock()-event.mark.observed,clock:'content_monotonic'});
  }
  scheduled(payload:{request_id:string;segments:Ref[];automatic:boolean}){
    const ref=payload.segments.at(-1),mark=ref&&this.revisions.get(this.key(ref));
    if(mark?.stable!==undefined)this.record({stage:'suggestion_scheduled_received',request_id:payload.request_id,trigger:payload.automatic?'auto':'manual',stable_to_schedule_received_ms:this.clock()-mark.stable,clock:'content_monotonic'});
  }
  rendered(payload:{request_id:string;segments:Ref[];automatic:boolean;stale:boolean}){
    const ref=payload.segments.at(-1),mark=ref&&this.revisions.get(this.key(ref));
    // A card from a different revision/document cannot borrow a newer caption's clock.
    if(!mark)return;
    this.record({stage:'card_rendered_notification',request_id:payload.request_id,segment_id:ref!.id,revision:ref!.revision,trigger:payload.automatic?'auto':'manual',outcome:payload.stale?'stale':'ready',observed_to_rendered_notification_ms:this.clock()-mark.observed,...(mark.stable===undefined?{}:{stable_to_rendered_notification_ms:this.clock()-mark.stable}),clock:'content_monotonic'});
  }
}
