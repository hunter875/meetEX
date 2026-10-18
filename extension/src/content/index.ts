import {DOMCaptionAdapter,type CaptionProfile} from './meet-adapter';
import {calibrate} from './calibrate';
let adapter:DOMCaptionAdapter|null=null;
const observations=new Map<string,number>();
const send=(type:string,payload:unknown)=>chrome.runtime.sendMessage({type,payload}).catch(()=>{});
function observed(e:import('./caption-reducer').CaptionEvent){observations.set(e.event_id,performance.now());if(observations.size>500)observations.delete(observations.keys().next().value!);void send('capture.caption',e);}
chrome.runtime.onMessage.addListener((message,_sender,respond)=>{
  if(message.type==='capture.start'){
    if(adapter){respond({ok:true});return false;}
    adapter=new DOMCaptionAdapter(message.profile as CaptionProfile|null,observed,status=>void send('capture.status',{status}),undefined,()=>void send('capture.gap',{reason:'adapter_replaced'}));adapter.start();respond({ok:true});
  }else if(message.type==='capture.stop'){adapter?.stop();adapter=null;respond({ok:true});}
  else if(message.type==='capture.flush'){adapter?.flush();respond({ok:true});}
  else if(message.type==='capture.ack'){
    const started=observations.get(message.event_id);if(started!==undefined){observations.delete(message.event_id);void send('capture.measurement',{duration_ms:performance.now()-started});}respond({ok:true});
  }
  else if(message.type==='capture.calibrate'){
    adapter?.stop();adapter=null;calibrate().then(profile=>{void send('capture.profile',profile);respond({ok:true,profile});}).catch(error=>respond({ok:false,error:String(error.message)}));return true;
  }
  return false;
});
void send('capture.hello',{url:location.href});
setInterval(()=>{if(adapter)void send('capture.heartbeat',{status:adapter.getStatus()});},20000);
