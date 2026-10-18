import {CaptionReducer,type CaptionEvent,type Block} from './caption-reducer';
export type CaptureStatus='starting'|'observing'|'waiting_for_caption'|'captions_off'|'unsupported_dom'|'paused'|'disconnected'|'meeting_left'|'unknown';
export type CaptionProfile={root:string;block:string;text:string;speaker?:string;toggle?:string;version:string;calibrated_at:string};
export interface MeetCaptionAdapter {start():void;stop():void;getStatus():CaptureStatus;flush():void;}
export class DOMCaptionAdapter implements MeetCaptionAdapter {
  private observer?:MutationObserver;private watchdog?:ReturnType<typeof setInterval>;
  private stabilizer?:ReturnType<typeof setInterval>;
  private root:Element|null=null;private status:CaptureStatus='starting';private keys=new WeakMap<Element,string>();
  private reducer:CaptionReducer;private started=false;private initial=true;private everFound=false;
  constructor(private profile:CaptionProfile|null,onCaption:(e:CaptionEvent)=>void,private onStatus:(s:CaptureStatus)=>void,private diagnostic:(m:{code:string;adapter_version:string})=>void=()=>{},private onGap:()=>void=()=>{}) {
    this.reducer=new CaptionReducer(onCaption,profile?.version||'meet-calibrated-v2',1000,onGap);
  }
  getStatus(){return this.status;}
  private setStatus(s:CaptureStatus){if(s!==this.status){this.status=s;this.onStatus(s);}}
  start(){if(this.started)return;this.started=true;this.onStatus('starting');this.attach();this.watchdog=setInterval(()=>this.attach(),500);this.stabilizer=setInterval(()=>this.reducer.tick(),100);}
  stop(){this.started=false;this.observer?.disconnect();this.observer=undefined;this.root=null;if(this.watchdog)clearInterval(this.watchdog);if(this.stabilizer)clearInterval(this.stabilizer);this.setStatus('paused');}
  flush(){if(this.started){this.attach();this.reducer.flush();}}
  private attach(){
    if(!this.profile){this.setStatus('unsupported_dom');return;}
    let container:Element|null;
    try{container=document.querySelector(this.profile.root);}catch{this.setStatus('unsupported_dom');return;}
    if(this.profile.toggle){
      let button:Element|null=null;try{button=document.querySelector(this.profile.toggle);}catch{/* invalid calibration */}
      if(button?.getAttribute('aria-pressed')==='false'){this.observer?.disconnect();this.root=null;this.setStatus('captions_off');return;}
    }
    if(!container||container===document.body||container===document.documentElement){
      if(this.root){this.root=null;this.observer?.disconnect();this.onGap();}
      this.setStatus(this.everFound?'unknown':'unsupported_dom');return;
    }
    if(container!==this.root){
      if(this.everFound)this.onGap();
      this.root=container;this.everFound=true;this.observer?.disconnect();
      // Read each delivered mutation batch. A trailing debounce can erase a short turn before scanning it.
      this.observer=new MutationObserver(()=>{if(this.started)this.attach();});
      this.observer.observe(container,{subtree:true,childList:true,characterData:true});this.scan();
      this.diagnostic({code:'container_attached',adapter_version:this.profile.version});
    }else this.scan();
  }
  private scan(){
    if(!this.started||!this.root?.isConnected||!this.profile)return;
    if(this.status==='captions_off'){
      const toggle=this.profile.toggle?document.querySelector(this.profile.toggle):null;
      if(toggle?.getAttribute('aria-pressed')==='false')return;
    }
    let nodes:Element[];
    try{nodes=this.profile.block===':scope'?[this.root]:Array.from(this.root.querySelectorAll(this.profile.block));}catch{this.setStatus('unsupported_dom');return;}
    let blocks:Block[];let missingText=false;
    try{blocks=nodes.map(node=>{
      const textNode=this.profile!.text===':scope'?node:node.querySelector(this.profile!.text);
      if(!textNode)missingText=true;
      const speakerNode=this.profile!.speaker?node.querySelector(this.profile!.speaker):null;
      if(!this.keys.has(node))this.keys.set(node,crypto.randomUUID());
      return {key:this.keys.get(node)!,speaker:speakerNode?.textContent?.trim()||null,text:textNode?.textContent||''};
    }).filter(b=>b.text.trim());}catch{this.setStatus('unsupported_dom');return;}
    if(missingText||(!nodes.length&&this.root.textContent?.trim())){this.setStatus('unsupported_dom');return;}
    if(this.initial){this.reducer.prime(blocks);this.initial=false;}
    else this.reducer.update(blocks);
    this.setStatus(blocks.length?'observing':'waiting_for_caption');
  }
}
