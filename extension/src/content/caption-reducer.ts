import type {components} from '../api-schema';
export type CaptionEvent = Required<components['schemas']['Caption']>;
export type Block = {key:string; speaker:string|null; text:string};
type Segment = {key:string; id:string; revision:number; speaker:string|null; text:string; changedAt:number; stable:boolean; slot:number; suppressed:boolean};
const normalise=(text:string)=>text.replace(/\s+/g,' ').trim();
function correction(a:string,b:string){
  if(a.startsWith(b)||b.startsWith(a))return true;
  const words=new Set(a.toLowerCase().split(/\s+/));const other=b.toLowerCase().split(/\s+/);
  return other.filter(w=>words.has(w)).length/Math.max(words.size,other.length)>.55;
}
export class CaptionReducer {
  private segments=new Map<string,Segment>(); private previous:Segment[]=[]; private seq=0;
  readonly epoch=crypto.randomUUID();
  constructor(private emit:(event:CaptionEvent)=>void,private version='meet-calibrated-v1',private stableMs=1000){}
  private publish(segment:Segment,at:number){
    this.emit({type:'caption.upsert',protocol_version:1,event_id:crypto.randomUUID(),capture_epoch:this.epoch,
      segment_id:segment.id,revision:segment.revision,seq:++this.seq,speaker_label:segment.speaker,
      text:segment.text,observed_at:new Date(at).toISOString(),stable:segment.stable,adapter_version:this.version});
  }
  prime(blocks:Block[],at=Date.now()) {this.update(blocks,at,true);}
  update(blocks:Block[],at=Date.now(),silent=false){
    const next:Segment[]=[];const claimed=new Set<string>();
    blocks.forEach((block,slot)=>{
      const text=normalise(block.text);const speaker=block.speaker?.trim()||null;if(!text)return;
      let segment=this.segments.get(block.key);
      if(!segment){
        // Reconcile re-render only within a currently visible turn/slot, never across the full transcript.
        const old=this.previous[slot];
        if(old && !claimed.has(old.id) && old.speaker===speaker && (old.text===text||correction(old.text,text)))segment=old;
      }
      if(segment && (segment.speaker!==speaker || (segment.stable && segment.text!==text && !correction(segment.text,text))))segment=undefined;
      if(!segment){
        segment={key:block.key,id:crypto.randomUUID(),revision:1,speaker,text,changedAt:at,stable:false,slot,suppressed:silent};
        if(!silent)this.publish(segment,at);
      }else if(segment.text!==text){
        segment={...segment,key:block.key,text,speaker,revision:segment.revision+1,changedAt:at,stable:false,slot,suppressed:segment.suppressed||silent};
        if(!segment.suppressed)this.publish(segment,at);
      }else segment={...segment,key:block.key,slot};
      claimed.add(segment.id);next.push(segment);
    });
    for(const removed of this.previous)if(!claimed.has(removed.id)&&!removed.stable&&!removed.suppressed){removed.stable=true;removed.revision++;this.publish(removed,at);}
    this.segments=new Map(next.map(s=>[s.key,s]));this.previous=next;
  }
  tick(at=Date.now()){
    for(const segment of this.segments.values())if(!segment.stable && at-segment.changedAt>=this.stableMs){segment.stable=true;if(!segment.suppressed){segment.revision++;this.publish(segment,at);}}
  }
  flush(at=Date.now()){
    for(const segment of this.segments.values())if(!segment.stable){segment.stable=true;if(!segment.suppressed){segment.revision++;this.publish(segment,at);}}
  }
}
