import {test,expect,chromium,type BrowserContext,type Page,type Worker} from '@playwright/test';
import {spawn,type ChildProcess} from 'node:child_process';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createServer,request as forwardHTTP,type Server} from 'node:http';
import {connect as connectTCP,type Socket} from 'node:net';
let context:BrowserContext;let page:Page;let worker:Worker;let extensionId:string;let backend:ChildProcess;let token:string;let dataDir:string;let projectId:string;let demoMeetingId:string;let logs='';
const base='http://127.0.0.1:8765';
const evidenceDir=process.env.MEET_E2E_EVIDENCE_DIR||'docs/evidence';
const evidencePath=(name:string)=>path.join(evidenceDir,name);
let proxy:Server;let transportBlocked=false;const transportClients=new Set<Socket>();
function dropTransport(){for(const socket of transportClients)socket.destroy();transportClients.clear();}
async function api(route:string,method='GET',body?:unknown){const response=await fetch(base+route,{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const value=await response.json();expect(response.ok,JSON.stringify(value)).toBeTruthy();return value;}
async function pair(target:Page){await target.goto(`chrome-extension://${extensionId}/dashboard.html#/settings`);await target.getByLabel('Pairing token ứng dụng local').fill(token);await target.getByRole('button',{name:'Lưu kết nối',exact:true}).click();await expect(target.getByText('Provider văn bản',{exact:true})).toBeVisible();}
test.describe.serial('Genuine MV3 extension + real local backend; synthetic Meet/controlled AI',()=>{
  test.beforeAll(async()=>{
    await mkdir(evidenceDir,{recursive:true});
    try{const r=await fetch(base+'/health');if(r.ok)throw new Error('Port 8765 is already in use. Stop the development backend before e2e; no existing data is touched.');}catch(e){if((e as Error).message.startsWith('Port'))throw e;}
    const dir=await mkdtemp(path.join(tmpdir(),'meet-copilot-e2e-'));dataDir=path.join(dir,'data');await mkdir(dataDir);
    const extension=path.resolve('extension/dist');
    context=await chromium.launchPersistentContext(path.join(dir,'profile'),{channel:'chromium',headless:true,executablePath:process.env.MEET_CHROMIUM_PATH||undefined,args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`],viewport:{width:1440,height:1000},acceptDownloads:true});
    worker=context.serviceWorkers()[0]||await context.waitForEvent('serviceworker');extensionId=worker.url().split('/')[2];
    // Test-only transparent proxy: drop WS transport without restarting the backend or mocking ACKs.
    proxy=createServer((req,res)=>{const upstream=forwardHTTP({hostname:'127.0.0.1',port:18765,path:req.url,method:req.method,headers:req.headers},r=>{res.writeHead(r.statusCode||502,r.headers);r.on('error',()=>res.destroy());r.pipe(res);});upstream.on('error',()=>{if(!res.headersSent)res.writeHead(502);res.end();});res.on('close',()=>upstream.destroy());req.pipe(upstream);});
    proxy.on('upgrade',(req,client,head)=>{if(transportBlocked){client.destroy();return;}transportClients.add(client);const upstream=connectTCP(18765,'127.0.0.1',()=>{upstream.write(`${req.method} ${req.url} HTTP/1.1\r\n`+req.rawHeaders.reduce((s,h,i)=>s+h+(i%2?'\r\n':': '),'')+'\r\n');if(head.length)upstream.write(head);client.pipe(upstream);upstream.pipe(client);});client.on('close',()=>{transportClients.delete(client);upstream.destroy();});client.on('error',()=>upstream.destroy());upstream.on('error',()=>client.destroy());upstream.on('close',()=>client.destroy());});
    await new Promise<void>(resolve=>proxy.listen(8765,'127.0.0.1',resolve));
    backend=spawn(path.resolve(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python'),['-m','uvicorn','phase2_server:app','--app-dir','e2e','--host','127.0.0.1','--port','18765','--workers','1'],{cwd:process.cwd(),env:{...process.env,MEET_DATA_DIR:dataDir,MEET_EXTENSION_ID:extensionId,MEET_DEV_ORIGIN:'',DEEPSEEK_API_KEY:''},windowsHide:true});
    backend.stdout?.on('data',d=>logs+=String(d));backend.stderr?.on('data',d=>logs+=String(d));
    await expect.poll(async()=>{try{return (await fetch(base+'/health')).ok;}catch{return false;}},{timeout:20000}).toBe(true);
    token=(await readFile(path.join(dataDir,'pairing-token'),'utf8')).trim();page=await context.newPage();page.on('pageerror',e=>console.error('UI error:',e.message));await pair(page);
  });
  test.afterAll(async()=>{dropTransport();await context?.close();backend?.kill();proxy?.closeAllConnections();proxy?.close();await writeFile(evidencePath('e2e-backend.log'),logs,'utf8');});
  test('UX-01/SRC-01/HIS-01/REP-02 five-screen demo journey with pin and exact export',async()=>{
    await page.getByRole('link',{name:'Dự án & dữ liệu',exact:true}).click();await page.getByRole('button',{name:'Tạo dự án',exact:true}).click();
    await page.getByLabel('Tên dự án',{exact:true}).fill('Demo Portal');await page.getByLabel('Mô tả',{exact:true}).fill('Dự án thử cho nghiệm thu — dữ liệu synthetic.');await page.getByRole('dialog').getByRole('button',{name:'Tạo dự án',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Demo Portal',exact:true})).toBeVisible();projectId=(await api('/api/v1/projects'))[0].id;
    await page.getByRole('button',{name:'Thêm nguồn',exact:true}).first().click();await page.getByLabel('Tên nguồn',{exact:true}).fill('API deployment notes');await page.getByLabel('Hoặc dán nội dung',{exact:true}).fill('API-17: The fix still needs testing on staging. Deployment date is not confirmed.');await page.getByRole('button',{name:'Xem trước',exact:true}).click();await page.getByRole('button',{name:'Nhập & tạo index',exact:true}).click();
    await expect(page.getByText('ready',{exact:true})).toBeVisible();await page.getByLabel('Tìm nguồn',{exact:true}).fill('API-17');await page.getByRole('button',{name:'Tìm kiếm',exact:true}).click();await expect(page.locator('.search-result')).toContainText('staging');await page.screenshot({path:evidencePath('projects.png'),fullPage:true});
    await page.getByRole('link',{name:'Đang họp',exact:true}).click();await page.getByLabel('Chế độ demo có nhãn',{exact:false}).check();await page.getByRole('button',{name:'Bắt đầu demo',exact:true}).click();await expect(page.locator('.demo-banner')).toBeVisible();
    demoMeetingId=(await api('/api/v1/meetings'))[0].id;
    await api(`/api/v1/meetings/${demoMeetingId}/demo-caption`,'POST',{type:'caption.upsert',protocol_version:1,event_id:crypto.randomUUID(),capture_epoch:'self-fixture',segment_id:'self-segment',revision:1,seq:1,speaker_label:'Me',text:'Hello, let us review API-17.',observed_at:new Date().toISOString(),stable:true,adapter_version:'e2e-fixture'});
    await page.getByLabel('Participant là Tôi').selectOption('Me');await page.getByLabel('Phụ đề demo',{exact:true}).fill('We will NOT deploy on Friday. Maybe Monday.');await page.getByRole('button',{name:'Thêm đoạn demo',exact:true}).click();
    await expect(page.getByTestId('english-reply')).toBeVisible({timeout:16000});await page.getByRole('button',{name:'Giữ câu',exact:true}).click();const held=await page.getByTestId('english-reply').innerText();
    await page.getByLabel('Phụ đề demo',{exact:true}).fill('Could you also confirm the billing requirements?');await page.getByRole('button',{name:'Thêm đoạn demo',exact:true}).click();await expect(page.getByRole('button',{name:'Có gợi ý mới',exact:true})).toBeVisible({timeout:16000});expect(await page.getByTestId('english-reply').innerText()).toBe(held);await page.screenshot({path:evidencePath('live-pinned.png'),fullPage:true});
    await page.getByRole('button',{name:'Ngắn hơn',exact:true}).click();await expect.poll(async()=>{const m=await api('/api/v1/meetings/'+demoMeetingId);return m.requests.at(-1)?.status;}).toMatch(/ready|stale/);const heldAction=(await api('/api/v1/meetings/'+demoMeetingId)).requests.at(-1);expect(heldAction.snapshot.segments.at(-1).text).toContain('NOT deploy');
    expect(heldAction.snapshot.routing).toBeTruthy();
    await page.getByLabel('Chế độ trả lời',{exact:true}).selectOption('deep');
    await page.getByLabel('Hỏi AI',{exact:true}).fill('Compare caching and indexing. Which approach should we choose?');
    await expect(page.getByTestId('routing-preview')).toContainText('Phân tích sâu');
    await expect(page.getByTestId('routing-preview')).toContainText('chưa phải thời gian được bảo đảm');
    const previewBefore=(await api('/api/v1/metrics')).request_count;
    const preview=await api(`/api/v1/meetings/${demoMeetingId}/classify`,'POST',{question:'Can we deploy to production?',response_mode:'fast'});
    expect(preview.route).toBe('clarify');expect(preview.requires_verification).toBe(true);
    expect((await api('/api/v1/metrics')).request_count).toBe(previewBefore);
    await page.getByRole('button',{name:'Tạo gợi ý',exact:false}).click();
    await expect.poll(async()=>{const m=await api('/api/v1/meetings/'+demoMeetingId);return m.requests.at(-1)?.status;}).toMatch(/ready|stale/);
    const deepRequest=(await api('/api/v1/meetings/'+demoMeetingId)).requests.at(-1);
    expect(deepRequest.snapshot.routing.route).toBe('deep');expect(deepRequest.snapshot.routing.source).toBe('manual');
    await page.screenshot({path:evidencePath('routing-ui.png'),fullPage:true});
    await page.getByLabel('Hỏi AI',{exact:true}).fill('');await page.getByLabel('Chế độ trả lời',{exact:true}).selectOption('auto');

    await page.getByRole('button',{name:'Có gợi ý mới',exact:true}).click();await page.getByRole('button',{name:'Kết thúc',exact:true}).click();await page.getByRole('button',{name:'Mở báo cáo',exact:true}).click();await page.getByRole('button',{name:'Tạo báo cáo nháp',exact:true}).first().click();await expect(page.getByLabel('Tóm tắt tiếng Việt',{exact:true})).toBeVisible();
    await page.getByLabel('Tóm tắt tiếng Việt',{exact:true}).fill('BẢN SỬA ĐÃ LƯU: ngày triển khai chưa được xác nhận.');await page.getByLabel('Tôi đã xem lại báo cáo',{exact:true}).check();await page.getByRole('button',{name:'Lưu bản nháp',exact:true}).click();await expect(page.getByRole('heading',{name:'Báo cáo v2',exact:true})).toBeVisible();
    const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'Markdown',exact:true}).click();const download=await downloadPromise;const exported=await readFile((await download.path())!,'utf8');expect(exported).toContain('BẢN SỬA ĐÃ LƯU');expect(exported).toContain('Evidence:');await page.screenshot({path:evidencePath('report.png'),fullPage:true});
    await page.getByRole('link',{name:'Lịch sử',exact:true}).click();await page.getByLabel('Tìm lịch sử',{exact:true}).fill('NOT deploy');await page.getByRole('button',{name:'Lọc',exact:true}).click();await expect(page.locator('.meeting-row')).toHaveCount(1);await page.getByRole('link',{name:'Cài đặt',exact:true}).click();await expect(page.getByText('Usage & thời gian thực đo',{exact:true})).toBeVisible();
  });
  test('SEC-06 provider key goes only to backend RAM; production key test never fakes success',async()=>{
    const sentinel='FAKE_KEY_SENTINEL_FOR_E2E';await page.getByLabel('Provider API key',{exact:true}).fill(sentinel);await page.getByRole('button',{name:'Đặt key vào RAM',exact:true}).click();await expect(page.getByLabel('Provider API key',{exact:true})).toHaveValue('');await expect(page.getByText('Đã có key ở backend',{exact:true})).toBeVisible();
    const storage=await worker.evaluate(async()=>({local:await chrome.storage.local.get(null),session:await chrome.storage.session.get(null)}));expect(JSON.stringify(storage)).not.toContain(sentinel);expect(JSON.stringify(await api('/api/v1/settings'))).not.toContain(sentinel);
    await page.getByRole('button',{name:'Xóa key',exact:true}).click();await page.getByRole('button',{name:'Test kết nối thật',exact:true}).click();await expect(page.getByText(/Test lỗi: Add an API key/)).toBeVisible();
  });
  test('CAP/TRN integrated worker and content script with calibrated synthetic Meet DOM',async()=>{
    const html='<!doctype html><html><head><title>SYNTHETIC MEET FIXTURE — not Google Meet live</title><style>body{font:18px sans-serif;margin:0;background:#202622;color:white}#captions{position:absolute;left:300px;top:450px;width:700px;min-height:110px;border:2px solid #66745f;padding:20px}.speaker{display:block;color:#c7dcaf;margin-bottom:10px}.words{display:block}</style></head><body><h1>Synthetic caption fixture</h1><section id="captions"><div class="block"><span class="speaker">Before start</span><span class="words">Already rendered — must not backfill</span></div></section><aside id="chat">CHAT MUST NOT BE READ</aside></body></html>';
    await context.route('https://meet.google.com/fixture-room',route=>route.fulfill({status:200,contentType:'text/html',body:html}));const meet=await context.newPage();await meet.goto('https://meet.google.com/fixture-room');await meet.bringToFront();
    await expect.poll(async()=>await worker.evaluate(async()=>{const tabs=await chrome.tabs.query({url:'https://meet.google.com/*'});const id=tabs[0]?.id;return id?(await chrome.storage.session.get('document_'+id))['document_'+id]:null;})).toBeTruthy();
    const calibration=page.evaluate(()=>chrome.runtime.sendMessage({type:'ui.calibrate'}));await expect(meet.getByText('Meet Copilot · chọn DOM đang hiển thị',{exact:true})).toBeVisible();await meet.locator('#captions').click({position:{x:8,y:8}});await meet.getByRole('button',{name:'Xác nhận',exact:true}).click();await meet.locator('.words').click();await meet.getByRole('button',{name:'Xác nhận',exact:true}).click();await meet.locator('.speaker').click();await meet.getByRole('button',{name:'Xác nhận',exact:true}).click();expect((await calibration).ok).toBe(true);
    const m=await api('/api/v1/meetings','POST',{project_id:projectId,title:'SYNTHETIC DOM CAPTURE',timezone:'America/Los_Angeles',persistence_mode:'local',demo:false,meeting_key:'/fixture-room'});
    await meet.bringToFront();const bound=await page.evaluate(id=>chrome.runtime.sendMessage({type:'ui.bind',session_id:id}),m.id);expect(bound.ok,JSON.stringify(bound)).toBe(true);
    await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).capture_status).toBe('observing');expect((await api('/api/v1/meetings/'+m.id)).segments).toHaveLength(0);
    await meet.evaluate(()=>{document.querySelector('.speaker')!.textContent='Client A';document.querySelector('.words')!.textContent='Can we';});await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).segments.length).toBe(1);
    await meet.evaluate(()=>document.querySelector('.words')!.textContent='Can we NOT deploy API-17 on Friday?');await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).segments[0]?.text).toContain('NOT deploy');
    const snap=await api('/api/v1/meetings/'+m.id);expect(snap.segments).toHaveLength(1);expect(JSON.stringify(snap.segments)).not.toContain('CHAT MUST');
    // Side panel document at its required narrow width. Native toolbar user gesture is a separate live check.
    const panel=await context.newPage();await panel.setViewportSize({width:320,height:950});await panel.goto(`chrome-extension://${extensionId}/sidepanel.html`);await expect(panel.locator('.caption-text')).toContainText('NOT deploy');expect(await panel.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await panel.screenshot({path:evidencePath('sidepanel-320.png'),fullPage:true});
    await panel.close();await meet.evaluate(()=>document.querySelector('.words')!.textContent='Can we NOT deploy API-17 on Friday? Please confirm.');await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).segments[0]?.text).toContain('Please confirm');
    const cdp=await context.newCDPSession(page);const targets=await cdp.send('Target.getTargets');const target=targets.targetInfos.find(t=>t.type==='service_worker'&&t.url.startsWith(`chrome-extension://${extensionId}/`));expect(target).toBeTruthy();const stopped=await cdp.send('Target.closeTarget',{targetId:target!.targetId});expect(stopped.success).toBe(true);
    await expect.poll(async()=>{const result=await page.evaluate(()=>chrome.runtime.sendMessage({type:'ui.state'}));return result.binding?.session_id;}).toBe(m.id);
    await expect.poll(async()=>{const result=await page.evaluate(()=>chrome.runtime.sendMessage({type:'ui.state'}));return result.connected;}).toBe(true);
    await meet.evaluate(()=>document.querySelector('.words')!.textContent='Can we NOT deploy API-17 on Friday? Please confirm after worker restart.');await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).segments[0]?.text).toContain('after worker restart');
    await meet.evaluate(()=>{document.querySelector('.speaker')!.textContent='Malformed fixture';document.querySelector('.words')!.textContent='x'.repeat(10001);});await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).gaps.some((g:{reason:string})=>g.reason==='event_rejected')).toBe(true);
    await meet.evaluate(()=>{document.querySelector('.speaker')!.textContent='Client B';document.querySelector('.words')!.textContent='Recovered valid caption after rejection.';});await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).segments.at(-1)?.text).toContain('Recovered valid caption');
    await expect.poll(async()=>{const value=await page.evaluate(()=>chrome.storage.session.get('captureTimings'));return value.captureTimings?.length||0;}).toBeGreaterThan(0);
    const measured=await page.evaluate(()=>chrome.storage.session.get('captureTimings'));const samples=[...measured.captureTimings].sort((a,b)=>a-b);await writeFile(evidencePath('capture-fixture.json'),JSON.stringify({mode:'calibrated synthetic DOM + actual MV3 worker + real backend',native_sidepanel_gesture_tested:false,worker_restart_tested:true,sidepanel_close_tested:true,browser:context.browser()?.version(),n:samples.length,median_ms:samples[Math.floor(samples.length/2)],p95_ms:samples[Math.min(samples.length-1,Math.floor(samples.length*.95))],samples_ms:samples,note:'Adapter observed event to backend ACK using content-script monotonic clock. Few samples, not reliable p95 or a Meet live result.'},null,2));
    await writeFile(evidencePath('runtime-metrics-fixture.json'),JSON.stringify(await api('/api/v1/metrics'),null,2));
    const spoof=await page.evaluate(()=>chrome.runtime.sendMessage({type:'capture.caption',payload:{text:'SPOOF'}}));expect(spoof.ok).toBe(false);
    await page.evaluate(()=>chrome.runtime.sendMessage({type:'ui.control',action:'end',idempotency_key:crypto.randomUUID()}));await meet.close();
    await page.evaluate(id=>chrome.storage.session.set({['reading_'+id]:{fixture:'delete-cache-sentinel'}}),m.id);await api('/api/v1/meetings/'+m.id,'DELETE');await expect.poll(async()=>page.evaluate(async id=>(await chrome.storage.session.get('reading_'+id))['reading_'+id],m.id)).toBeUndefined();
  });
  test('PHASE2 actual browser outage/recovery, scope, controls and correlated rendered latency',async()=>{
    test.setTimeout(180000);
    const html='<!doctype html><html><body><h1>SYNTHETIC PHASE 2</h1><section id="captions"></section><aside id="chat">CHAT NOT 15.5 API-17</aside></body></html>';
    await context.route('https://meet.google.com/phase2-room',route=>route.fulfill({status:200,contentType:'text/html',body:html}));
    const meet=await context.newPage();await meet.goto('https://meet.google.com/phase2-room');await meet.bringToFront();
    const profile={root:'#captions',block:'.block',text:'.words',speaker:'.speaker',version:'synthetic-phase2-v2',calibrated_at:new Date().toISOString()};
    await page.evaluate(async profile=>{const {config}=await chrome.storage.local.get('config');await chrome.storage.local.set({config:{...config,profile}});},profile);
    // Restart the actual worker to load the synthetic profile, preserving session RAM only.
    const cdp=await context.newCDPSession(page);const targets=await cdp.send('Target.getTargets');const target=targets.targetInfos.find(t=>t.type==='service_worker'&&t.url.startsWith(`chrome-extension://${extensionId}/`));await cdp.send('Target.closeTarget',{targetId:target!.targetId});
    await expect.poll(async()=>(await page.evaluate(()=>chrome.runtime.sendMessage({type:'ui.state'}))).connected).toBe(true);
    const m=await api('/api/v1/meetings','POST',{project_id:projectId,title:'SYNTHETIC PHASE 2 RECOVERY',timezone:'America/Los_Angeles',persistence_mode:'local',demo:false,meeting_key:'/phase2-room'});
    await meet.bringToFront();await expect.poll(async()=>await page.evaluate(()=>chrome.storage.session.get(null)).then(v=>Object.keys(v).filter(k=>k.startsWith('document_')).length)).toBeGreaterThan(0);
    expect((await page.evaluate(id=>chrome.runtime.sendMessage({type:'ui.bind',session_id:id}),m.id)).ok).toBe(true);
    await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).capture_status).toBe('waiting_for_caption');
    const observe=async(text:string,speaker='Client')=>{await meet.evaluate(({text,speaker})=>{let b=document.querySelector('.block');if(!b){b=document.createElement('div');b.className='block';b.innerHTML='<span class="speaker"></span><span class="words"></span>';document.querySelector('#captions')!.append(b);}b.querySelector('.speaker')!.textContent=speaker;b.querySelector('.words')!.textContent=text;},{text,speaker});};
    await observe('Timeout 15.5 ms API-17');await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).segments.at(-1)?.text).toBe('Timeout 15.5 ms API-17');
    await observe('Timeout 50.5 ms API-71');await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).segments.at(-1)?.text).toBe('Timeout 50.5 ms API-71');
    expect((await api('/api/v1/meetings/'+m.id)).segments).toHaveLength(1);
    const second=await context.newPage();await second.goto('https://meet.google.com/phase2-room');await second.evaluate(()=>document.querySelector('#captions')!.textContent='SECOND TAB MUST NOT LEAK');await second.close();
    await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).segments[0]?.stable).toBe(true);
    const faults=[];
    for(const duration of [5000,20000]){
      const before=(await api('/api/v1/meetings/'+m.id)).transcript_revision;
      transportBlocked=true;dropTransport();await expect.poll(async()=>(await page.evaluate(()=>chrome.runtime.sendMessage({type:'ui.state'}))).connected).toBe(false);
      await meet.evaluate(()=>document.querySelector('.block')!.remove());await new Promise(resolve=>setTimeout(resolve,30));
      await observe(`During outage ${duration} NOT API-17`);await new Promise(resolve=>setTimeout(resolve,duration));
      expect((await api('/api/v1/meetings/'+m.id)).transcript_revision).toBe(before);
      transportBlocked=false;
      await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).segments.at(-1)?.text,{timeout:30000}).toBe(`During outage ${duration} NOT API-17`);
      await expect.poll(async()=>(await page.evaluate(()=>chrome.runtime.sendMessage({type:'ui.state'}))).pending,{timeout:30000}).toBe(0);
      faults.push({outage_ms:duration,transcript_recovered:true,unacked:0});
    }
    expect((await api('/api/v1/meetings/'+m.id)).segments.map((s:any)=>s.text)).toEqual(['Timeout 50.5 ms API-71','During outage 5000 NOT API-17','During outage 20000 NOT API-17']);
    expect((await api('/api/v1/meetings/'+m.id)).requests).toEqual([]);
    const control=async(action:string)=>{const r=await page.evaluate(action=>chrome.runtime.sendMessage({type:'ui.control',action,idempotency_key:crypto.randomUUID()}),action);expect(r.ok,JSON.stringify(r)).toBe(true);};
    await control('pause');const count=(await api('/api/v1/meetings/'+m.id)).segments.length;await observe('PAUSED MUST NOT BACKFILL');await new Promise(resolve=>setTimeout(resolve,1200));await control('resume');await new Promise(resolve=>setTimeout(resolve,1200));expect((await api('/api/v1/meetings/'+m.id)).segments).toHaveLength(count);
    await observe('Could you explain the next step?','Another client');await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).segments.length).toBe(count+1);
    await new Promise(resolve=>setTimeout(resolve,1300));
    await api('/api/v1/provider/credential','PUT',{api_key:'FAKE_PHASE2_NO_NETWORK'});
    const panel=await context.newPage();await panel.goto(`chrome-extension://${extensionId}/sidepanel.html`);await panel.evaluate(id=>sessionStorage.setItem('meet-ui-session',id),m.id);await panel.reload();await expect(panel.locator('.caption-text')).toContainText('next step');
    const request=async(question:string)=>{const {request_id}=await api(`/api/v1/meetings/${m.id}/suggest`,'POST',{action:'suggest',question});return request_id;};
    const outcome=async(id:string,status:string)=>await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).requests.find((r:any)=>r.id===id)?.status).toBe(status);
    for(let n=0;n<3;n++){const rid=await request('PHASE2_READY '+n);await outcome(rid,'ready');await expect(panel.getByTestId('english-reply')).toBeVisible();await expect.poll(async()=>{const v=await page.evaluate(()=>chrome.storage.session.get('latencyRecords'));return v.latencyRecords?.some((r:any)=>r.request_id===rid&&r.stage==='card_rendered_notification');}).toBe(true);}
    const error=await request('PHASE2_ERROR');await outcome(error,'error');
    const stale=await request('PHASE2_SLOW_STALE');await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).requests.find((r:any)=>r.id===stale)?.status).toBe('running');await observe('Could you explain the revised next step?','Another client');await outcome(stale,'stale');
    const cancelled=await request('PHASE2_SLOW_CANCEL');await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).requests.find((r:any)=>r.id===cancelled)?.status).toBe('running');const next=await request('PHASE2_READY_AFTER_CANCEL');await outcome(cancelled,'cancelled');await outcome(next,'ready');
    await api(`/api/v1/meetings/${m.id}`,'PATCH',{self_speaker:'Client'});await observe('Which option should we choose next?','Another client');
    await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).requests.some((r:any)=>r.action==='auto'&&r.status==='ready'),{timeout:12000}).toBe(true);
    await panel.close();await observe('Could you clarify after the panel closes?','Another client');await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).segments.at(-1)?.text).toContain('panel closes');
    await meet.reload();await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).status).toBe('interrupted');await observe('OLD AT RELOAD MUST NOT BACKFILL');await control('resume');await new Promise(resolve=>setTimeout(resolve,1200));expect(JSON.stringify((await api('/api/v1/meetings/'+m.id)).segments)).not.toContain('OLD AT RELOAD');
    await observe('Fresh after reload','Fresh speaker');await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).segments.at(-1)?.text).toBe('Fresh after reload');
    const snapshot=await api('/api/v1/meetings/'+m.id);const telemetry=await page.evaluate(()=>chrome.storage.session.get(['latencyRecords','captureTimings']));const metrics=await api('/api/v1/metrics');
    expect(JSON.stringify(snapshot.segments)).not.toContain('PAUSED MUST');expect(JSON.stringify(snapshot.segments)).not.toContain('SECOND TAB MUST');expect(JSON.stringify(telemetry.latencyRecords)).not.toContain('Could you');
    await writeFile(evidencePath('phase2-recovery.json'),JSON.stringify({provenance:'synthetic calibrated DOM, genuine MV3 Chromium, real FastAPI/SQLite, httpx.MockTransport SSE provider, zero paid/network provider calls',browser:context.browser()?.version(),faults,snapshot,telemetry,backend_latency:metrics.latency_records,live_meet_tested:false},null,2));
    await control('end');await meet.close();await api('/api/v1/provider/credential','DELETE');
  });

  test('PHASE3 scheduler UI explains waiting/listening/quota and manual cache remains available',async()=>{
    const m=await api('/api/v1/meetings','POST',{project_id:projectId,title:'SYNTHETIC PHASE3 UI',timezone:'America/Los_Angeles',persistence_mode:'memory',demo:true});
    const emit=async(text:string,speaker='Client',id=crypto.randomUUID(),revision=1)=>await api(`/api/v1/meetings/${m.id}/demo-caption`,'POST',{type:'caption.upsert',protocol_version:1,event_id:crypto.randomUUID(),capture_epoch:'phase3-ui',segment_id:id,revision,seq:++sequence,speaker_label:speaker,text,observed_at:new Date().toISOString(),stable:true,adapter_version:'synthetic-phase3-ui'});
    let sequence=0;await emit('Hello','Me');await api(`/api/v1/meetings/${m.id}`,'PATCH',{self_speaker:'Me'});
    await page.evaluate(id=>chrome.runtime.sendMessage({type:'ui.bind',session_id:id}),m.id);
    const panel=await context.newPage();await panel.goto(`chrome-extension://${extensionId}/sidepanel.html`);await panel.evaluate(id=>sessionStorage.setItem('meet-ui-session',id),m.id);await panel.reload();
    await emit('Let me finish.');await expect(panel.getByTestId('scheduler-state')).toContainText('Đang chờ người nói kết thúc');
    await emit('Thanks!');await expect(panel.getByTestId('scheduler-state')).toContainText('Tiếp tục nghe');expect((await api('/api/v1/meetings/'+m.id)).requests).toHaveLength(0);
    await api('/api/v1/settings','PATCH',{auto_per_minute:1});
    await emit('Why is the cache blocked?');await emit('Which environment?');await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).requests.filter((r:any)=>r.status==='ready').length).toBe(1);
    const batch=await api('/api/v1/meetings/'+m.id);expect(batch.requests[0].snapshot.focus_segment_ids).toHaveLength(2);await expect(panel.getByTestId('english-reply')).toBeVisible();
    await panel.getByRole('button',{name:'Giữ câu',exact:true}).click();const held=await panel.getByTestId('english-reply').innerText();
    await emit('Why is production blocked?');await expect(panel.getByTestId('scheduler-state')).toContainText('giới hạn tự động');expect(await panel.getByTestId('english-reply').innerText()).toBe(held);
    const body={action:'suggest',question:'Please clarify this question.'};const [a,b]=await Promise.all([api(`/api/v1/meetings/${m.id}/suggest`,'POST',body),api(`/api/v1/meetings/${m.id}/suggest`,'POST',body)]);expect(a.request_id).toBe(b.request_id);
    await expect.poll(async()=>(await api('/api/v1/meetings/'+m.id)).requests.find((r:any)=>r.id===a.request_id)?.status).toBe('ready');expect(await panel.getByTestId('english-reply').innerText()).toBe(held);await expect(panel.getByRole('button',{name:'Có gợi ý mới',exact:true})).toBeVisible();
    await panel.screenshot({path:evidencePath('phase3-scheduler-ui.png'),fullPage:true});await writeFile(evidencePath('phase3-ui.json'),JSON.stringify({provenance:'synthetic demo + genuine MV3 UI/backend; no model calls',snapshot:await api('/api/v1/meetings/'+m.id),metrics:await api('/api/v1/metrics')},null,2));
    await page.evaluate(()=>chrome.runtime.sendMessage({type:'ui.control',action:'end',idempotency_key:crypto.randomUUID()}));await panel.close();await api('/api/v1/settings','PATCH',{auto_per_minute:12});
  });

  test('PHASE4 memory revisions, user provenance, report regeneration and exports',async()=>{
    const m=await api('/api/v1/meetings','POST',{project_id:projectId,title:'SYNTHETIC PHASE4 UI',timezone:'America/Los_Angeles',persistence_mode:'memory',demo:true});
    await api(`/api/v1/meetings/${m.id}`,'PATCH',{auto_mode:false});let seq=0;
    const emit=async(text:string,id:string,speaker:string,revision=1)=>await api(`/api/v1/meetings/${m.id}/demo-caption`,'POST',{type:'caption.upsert',protocol_version:1,event_id:crypto.randomUUID(),capture_epoch:'phase4-ui',segment_id:id,revision,seq:++seq,speaker_label:speaker,text,observed_at:'2026-10-19T00:30:00Z',stable:true,adapter_version:'synthetic-phase4-ui'});
    await emit('I will review API-71 by tomorrow.','task','Minh');await api(`/api/v1/meetings/${m.id}`,'PATCH',{self_speaker:'Minh'});await emit('Confirmed: test API-17 in staging.','decision','Client');
    await emit('We have NOT approved test API-17 in staging.','decision','Client',2);
    await page.evaluate(id=>chrome.runtime.sendMessage({type:'ui.bind',session_id:id}),m.id);
    const view=await context.newPage();await view.goto(`chrome-extension://${extensionId}/dashboard.html#/live`);await view.evaluate(id=>sessionStorage.setItem('meet-ui-session',id),m.id);await view.reload();
    const memory=view.getByTestId('meeting-memory');await expect(memory.getByTestId('memory-item')).toHaveCount(2);
    const decision=memory.getByTestId('memory-item').filter({hasText:'API-17'});await expect(decision).toContainText('Chưa xác nhận');await decision.getByRole('button',{name:'Lịch sử mục',exact:true}).click();await expect(view.getByRole('heading',{name:'Lịch sử version memory',exact:true})).toBeVisible();await expect(view.getByText('Confirmed: test API-17 in staging.',{exact:true})).toBeVisible();await view.getByRole('button',{name:'Đóng nguồn',exact:true}).click();
    await decision.getByRole('button',{name:'Mở evidence revision',exact:true}).click();await expect(view.getByText('decision · r2',{exact:true})).toBeVisible();await view.getByRole('button',{name:'Đóng nguồn',exact:true}).click();
    await memory.getByTestId('memory-item').filter({hasText:'API-71'}).getByRole('button',{name:'Chỉnh mục',exact:true}).click();await view.getByLabel('Owner memory',{exact:true}).fill('Alex');await view.getByLabel('Deadline memory',{exact:true}).fill('Maybe Friday');await view.getByLabel('Trạng thái memory',{exact:true}).selectOption('cancelled');await view.getByRole('button',{name:'Lưu thay đổi memory',exact:true}).click();await expect(memory.getByTestId('memory-item').filter({hasText:'API-71'})).toContainText('Bạn ghi/chỉnh sửa');
    await view.screenshot({path:evidencePath('phase4-memory-ui.png'),fullPage:true});
    await view.getByRole('button',{name:'Kết thúc',exact:true}).click();await view.goto(`chrome-extension://${extensionId}/dashboard.html#/meetings/${m.id}/report`);
    const generated=view.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith(`/meetings/${m.id}/reports`));await view.getByRole('button',{name:'Tạo báo cáo nháp',exact:true}).first().click();const reportJob=await (await generated).json();await expect.poll(async()=>(await api('/api/v1/jobs/'+reportJob.id)).status).toMatch(/ready|error/);const reportDone=await api('/api/v1/jobs/'+reportJob.id);expect(reportDone.status,JSON.stringify(reportDone)).toBe('ready');await expect(view.getByLabel('Tóm tắt tiếng Việt',{exact:true})).toBeVisible();
    await view.getByLabel('Tóm tắt tiếng Việt',{exact:true}).fill('PHASE4 USER EDIT preserved');const alternatives=view.locator('.report-content > section').last();await alternatives.getByRole('button',{name:'Thêm mục do bạn ghi',exact:true}).click();await alternatives.locator('textarea').first().fill('USER PROPOSAL: consider a staged rollout.');await expect(view.getByRole('button',{name:'Tạo lại thành phiên bản mới',exact:true})).toBeDisabled();await view.getByRole('button',{name:'Lưu bản nháp',exact:true}).click();await expect(view.getByRole('heading',{name:'Báo cáo v2',exact:true})).toBeVisible();
    const saved=(await api(`/api/v1/meetings/${m.id}`)).reports.find((r:any)=>r.version===2);expect(saved.payload.ai_proposals[0].origin).toBe('user_edit');await view.getByRole('button',{name:'Tạo lại thành phiên bản mới',exact:true}).click();await expect(view.getByRole('heading',{name:'Báo cáo v3',exact:true})).toBeVisible();expect((await api(`/api/v1/reports/${saved.id}`)).payload.summary_vi).toBe('PHASE4 USER EDIT preserved');
    const final=await api(`/api/v1/meetings/${m.id}`);expect(final.reports.at(-1).memory_snapshot.find((i:any)=>i.entity==='API-71').origin).toBe('user_edit');
    const exported=await fetch(base+`/api/v1/reports/${saved.id}/export?format=json`,{headers:{Authorization:'Bearer '+token}}).then(r=>r.json());expect(exported.edit_provenance.actor).toBe('local_user');expect(exported.evidence_snapshot.find((s:any)=>s.id==='decision').revision).toBe(2);
    await view.screenshot({path:evidencePath('phase4-report-ui.png'),fullPage:true});await writeFile(evidencePath('phase4-ui.json'),JSON.stringify({provenance:'Synthetic fixture + real MV3/backend, no paid calls',memory:await api(`/api/v1/meetings/${m.id}/memory`),reports:final.reports},null,2));await view.close();
  });

  test('PHASE5 rotation closes worker connection; re-pair and disconnect clear credential',async()=>{
    await page.goto(`chrome-extension://${extensionId}/dashboard.html#/settings`);
    await expect.poll(async()=>(await page.evaluate(()=>chrome.runtime.sendMessage({type:'ui.state'}))).connected).toBe(true);
    const previous=token;
    await api('/api/v1/local/pairing/rotate','POST',{});
    expect((await fetch(base+'/api/v1/projects',{headers:{Authorization:'Bearer '+previous}})).status).toBe(401);
    await expect.poll(async()=>(await page.evaluate(()=>chrome.runtime.sendMessage({type:'ui.state'}))).pairing_status).toBe('invalid');
    await expect(page.getByRole('alert').filter({hasText:'Pairing đã hết hiệu lực'})).toBeVisible();
    token=(await readFile(path.join(dataDir,'pairing-token'),'utf8')).trim();await pair(page);
    await expect.poll(async()=>(await page.evaluate(()=>chrome.runtime.sendMessage({type:'ui.state'}))).connected).toBe(true);
    await page.getByRole('button',{name:'Ngắt kết nối',exact:true}).click();
    await expect.poll(async()=>(await page.evaluate(()=>chrome.storage.local.get('config'))).config.token).toBe('');
    await page.reload();await expect(page.getByLabel('Pairing token ứng dụng local')).toHaveValue('');
    const state=await page.evaluate(()=>chrome.runtime.sendMessage({type:'ui.state'}));expect(state.connected).toBe(false);expect(state.binding).toBeNull();expect(state.pending).toBe(0);
    const storage=await page.evaluate(()=>chrome.storage.session.get(null));expect(Object.keys(storage).filter(k=>k.startsWith('reading_'))).toHaveLength(0);
    await page.screenshot({path:evidencePath('phase5-disconnected.png'),fullPage:true});
    await writeFile(evidencePath('phase5-pairing.json'),JSON.stringify({synthetic:true,old_rest_status:401,open_socket_invalidated:true,re_pair:true,disconnect_cleared:true,paid_calls:0},null,2));
  });

});
