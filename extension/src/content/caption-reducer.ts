import type {components} from '../api-schema';
export type CaptionEvent = Required<components['schemas']['Caption']>;
export type Block = {key:string; speaker:string|null; text:string};
type Segment = {key:string;id:string;revision:number;speaker:string|null;text:string;raw:string;prefix:string;changedAt:number;seenAt:number;stable:boolean;suppressed:boolean};
// Comparison keys only. Published text is never lowercased, punctuated or whitespace-normalised.
const tokens=(text:string)=>Array.from(text.matchAll(/\S+/gu)).slice(-160).map(m=>({key:m[0].toLocaleLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu,''),at:m.index!}));
function related(a:string,b:string){
  const x=tokens(a).map(t=>t.key),y=tokens(b).map(t=>t.key);
  if(x.join(' ')===y.join(' '))return true;
  if(a.startsWith(b)||b.startsWith(a))return true;
  const common=x.filter(w=>y.includes(w)).length;
  const shape=(words:string[])=>words.map(w=>w.replace(/\d/g,'#')).join(' ');
  return ((common>=2&&common/Math.max(x.length,y.length)>=.5)||(common>=1&&common/Math.max(x.length,y.length)>.5))||
    (common>=1&&x.length===y.length&&shape(x)===shape(y));
}
function scrollPrefix(previous:string,current:string):string|null{
  const a=tokens(previous),b=tokens(current);
  for(let count=Math.min(a.length-1,b.length-1);count>=3;count--){
    if(a.slice(-count).every((t,i)=>t.key===b[i].key))return previous.slice(0,a[a.length-count].at);
  }
  return null;
}
export class CaptionReducer {
  private previous:Segment[]=[];private seq=0;
  readonly epoch=crypto.randomUUID();
  constructor(private emit:(event:CaptionEvent)=>void,private version='meet-calibrated-v2',private stableMs=1000,private ambiguity:()=>void=()=>{}){}
  private publish(s:Segment,at:number){
    this.emit({type:'caption.upsert',protocol_version:1,event_id:crypto.randomUUID(),capture_epoch:this.epoch,
      segment_id:s.id,revision:s.revision,seq:++this.seq,speaker_label:s.speaker,text:s.text,
      observed_at:new Date(at).toISOString(),stable:s.stable,adapter_version:this.version});
  }
  prime(blocks:Block[],at=Date.now()){this.update(blocks,at,true);}
  update(blocks:Block[],at=Date.now(),silent=false){
    const next:Segment[]=[],claimed=new Set<string>(),keys=new Set(blocks.map(b=>b.key));
    for(const block of blocks){
      if(!block.text.trim())continue;
      const speaker=block.speaker?.trim()||null;
      let s=this.previous.find(p=>p.key===block.key&&!claimed.has(p.id));
      const compatible=(p:Segment)=>p.speaker===speaker||p.speaker===null||speaker===null;
      let prefix=s?.prefix||'';
      if(s){
        const rolling=at-s.seenAt<=3000?scrollPrefix(s.raw,block.text):null;
        if(!compatible(s)||(!related(s.raw,block.text)&&rolling===null)){
          if(compatible(s))this.ambiguity();
          s=undefined;prefix='';
        }else if(rolling!==null)prefix+=rolling;
      }else{
        // Only visible removed nodes, a short interval and a UNIQUE long-text match.
        // Slot number is irrelevant when the visible window scrolls.
        const candidates=this.previous.filter(p=>!keys.has(p.key)&&!claimed.has(p.id)&&
          p.speaker===speaker&&at-p.seenAt<=1500&&tokens(p.raw).length>=3&&related(p.raw,block.text));
        if(candidates.length===1){s=candidates[0];prefix=s.prefix;}
        else if(candidates.length>1)this.ambiguity();
      }
      if(!s){
        s={key:block.key,id:crypto.randomUUID(),revision:1,speaker,text:block.text,raw:block.text,prefix:'',changedAt:at,seenAt:at,stable:false,suppressed:silent};
        if(!silent)this.publish(s,at);
      }else{
        const label=speaker||s.speaker,text=prefix+block.text;
        const changed=text!==s.text||label!==s.speaker;
        s={...s,key:block.key,raw:block.text,prefix,seenAt:at,speaker:label};
        if(changed){s.text=text;s.revision++;s.changedAt=at;s.stable=false;s.suppressed ||= silent;if(!s.suppressed)this.publish(s,at);}
      }
      claimed.add(s.id);next.push(s);
    }
    for(const old of this.previous)if(!claimed.has(old.id)&&!old.stable&&!old.suppressed){old.stable=true;old.revision++;this.publish(old,at);}
    this.previous=next;
  }
  tick(at=Date.now()){
    for(const s of this.previous)if(!s.stable&&at-s.changedAt>=this.stableMs){s.stable=true;if(!s.suppressed){s.revision++;this.publish(s,at);}}
  }
  flush(at=Date.now()){
    for(const s of this.previous)if(!s.stable){s.stable=true;if(!s.suppressed){s.revision++;this.publish(s,at);}}
  }
}
