import {test,expect,chromium,type BrowserContext,type Page,type Worker} from '@playwright/test';
import {spawn,type ChildProcess} from 'node:child_process';
import {mkdtemp,readFile,writeFile,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
let context:BrowserContext;let page:Page;let worker:Worker;let extensionId:string;let backend:ChildProcess;let token:string;let dataDir:string;let projectId:string;let demoMeetingId:string;let logs='';
const base='http://127.0.0.1:8765';
const evidenceDir=process.env.MEET_E2E_EVIDENCE_DIR||'docs/evidence';
const evidencePath=(name:string)=>path.join(evidenceDir,name);
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
    backend=spawn(path.resolve('.venv/Scripts/python.exe'),['-m','uvicorn','app.main:app','--app-dir','backend','--host','127.0.0.1','--port','8765','--workers','1'],{cwd:process.cwd(),env:{...process.env,MEET_DATA_DIR:dataDir,MEET_EXTENSION_ID:extensionId,MEET_DEV_ORIGIN:'',DEEPSEEK_API_KEY:''},windowsHide:true});
    backend.stdout?.on('data',d=>logs+=String(d));backend.stderr?.on('data',d=>logs+=String(d));
    await expect.poll(async()=>{try{return (await fetch(base+'/health')).ok;}catch{return false;}},{timeout:20000}).toBe(true);
    token=(await readFile(path.join(dataDir,'pairing-token'),'utf8')).trim();page=await context.newPage();page.on('pageerror',e=>console.error('UI error:',e.message));await pair(page);
  });
  test.afterAll(async()=>{await context?.close();backend?.kill();await writeFile(evidencePath('e2e-backend.log'),logs,'utf8');});
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
});
