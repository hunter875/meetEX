import type {CaptionEvent} from '../content/caption-reducer';
export type Pending={event:CaptionEvent;created_at:number};
export class Outbox {
  items:Pending[]=[];
  constructor(items:Pending[]=[],readonly maxEvents=500,readonly maxBytes=5*1024*1024){this.items=items;}
  push(event:CaptionEvent){
    this.items.push({event,created_at:Date.now()});let dropped=0;
    while(this.items.length>this.maxEvents || new TextEncoder().encode(JSON.stringify(this.items)).byteLength>this.maxBytes){this.items.shift();dropped++;}
    return dropped;
  }
  ack(id:string){this.items=this.items.filter(p=>p.event.event_id!==id);}
}
