import type {CaptionProfile} from './meet-adapter';
function path(element:Element,root?:Element):string{
  if(element===root)return ':scope';
  const pieces:string[]=[];let current:Element|null=element;
  while(current&&current!==root){
    if(!root && current.id){pieces.unshift('#'+CSS.escape(current.id));break;}
    const tag=current.tagName.toLowerCase();const siblings=Array.from(current.parentElement?.children||[]).filter(s=>s.tagName===current!.tagName);
    pieces.unshift(tag+(siblings.length>1?`:nth-of-type(${siblings.indexOf(current)+1})`:''));current=current.parentElement;
  }
  return pieces.join(' > ');
}
export async function calibrate():Promise<CaptionProfile>{
  const host=document.createElement('div');host.id='meet-copilot-calibration';
  const shadow=host.attachShadow({mode:'open'});document.documentElement.append(host);
  const style=document.createElement('style');style.textContent=':host{all:initial}section{position:fixed;z-index:2147483647;top:14px;left:14px;background:#152c26;color:white;border-radius:12px;padding:16px;max-width:350px;font:14px system-ui;box-shadow:0 8px 40px #0006}button{background:#d7f1a0;color:#183529;padding:9px;margin:7px 5px 0 0;border:0;border-radius:7px;cursor:pointer}p{margin:7px 0;line-height:1.5}';shadow.append(style);
  const box=document.createElement('section');shadow.append(box);let selected:Element|null=null;let root:Element|null=null;let text:Element|null=null;let speaker:Element|null=null;let stage=0;let previousStyle='';let highlighted:HTMLElement|null=null;
  return new Promise((resolve,reject)=>{
    const unhighlight=()=>{if(highlighted)highlighted.style.outline=previousStyle;highlighted=null;};
    const highlight=(el:Element)=>{unhighlight();if(el instanceof HTMLElement){highlighted=el;previousStyle=el.style.outline;el.style.outline='3px solid #a5d85e';}};
    const cleanup=()=>{unhighlight();document.removeEventListener('click',click,true);document.removeEventListener('pointermove',move,true);host.remove();};
    const render=()=>{
      box.replaceChildren();const title=document.createElement('strong');title.textContent='Meet Copilot · chọn DOM đang hiển thị';box.append(title);
      const p=document.createElement('p');p.textContent=['1/3: Bật phụ đề. Click vùng chứa các block phụ đề, rồi Mở rộng nếu cần. Không chọn toàn trang/chat.','2/3: Click đúng phần chữ của một câu phụ đề, rồi Xác nhận.','3/3: Click tên người nói trong cùng block. Nếu không có, chọn Bỏ qua.'][stage];box.append(p);
      const info=document.createElement('p');info.textContent=selected?`Đã chọn: <${selected.tagName.toLowerCase()}>`:'Di chuột và click để chọn';box.append(info);
      function button(label:string,fn:()=>void){const b=document.createElement('button');b.textContent=label;b.addEventListener('click',fn);box.append(b);}
      button('Mở rộng',()=>{if(selected?.parentElement&&selected.parentElement!==document.body&&selected.parentElement!==document.documentElement){selected=selected.parentElement;highlight(selected);render();}});
      button('Xác nhận',()=>{
        if(!selected)return;
        if(stage===0){if(selected===document.body||selected===document.documentElement)return;root=selected;stage=1;selected=null;unhighlight();render();}
        else if(stage===1){if(!root!.contains(selected))return;text=selected;stage=2;selected=null;unhighlight();render();}
        else{if(!root!.contains(selected))return;speaker=selected;finish();}
      });
      if(stage===2)button('Bỏ qua tên',()=>finish());
      button('Hủy',()=>{cleanup();reject(new Error('Đã hủy chọn vùng phụ đề'));});
    };
    const finish=()=>{
      if(!root||!text)return;
      let block=text.parentElement||text;
      if(speaker){while(block!==root&&!block.contains(speaker))block=block.parentElement!;}
      else {while(block.parentElement&&block.parentElement!==root&&block.parentElement.children.length===1)block=block.parentElement;}
      if(block===root && speaker){box.append(Object.assign(document.createElement('p'),{textContent:'Vùng quá hẹp; chọn container lớn hơn gồm các block phụ đề.'}));return;}
      const relative=(el:Element,base:Element)=>el===base?':scope':':scope > '+path(el,base);
      const blockSelector=relative(block,root).replace(/:nth-of-type\(\d+\)$/,'');
      const profile:CaptionProfile={root:path(root),block:blockSelector,text:relative(text,block),speaker:speaker?relative(speaker,block):undefined,version:'meet-calibrated-v1',calibrated_at:new Date().toISOString()};
      cleanup();resolve(profile);
    };
    const move=(e:PointerEvent)=>{if(e.composedPath().includes(host))return;if(!selected&&e.target instanceof Element)highlight(e.target);};
    const click=(e:MouseEvent)=>{if(e.composedPath().includes(host))return;e.preventDefault();e.stopImmediatePropagation();if(e.target instanceof Element){selected=e.target;highlight(selected);render();}};
    document.addEventListener('pointermove',move,true);document.addEventListener('click',click,true);render();
  });
}
