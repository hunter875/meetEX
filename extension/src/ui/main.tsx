import {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {FolderKanban,Radio,FileText,History as HistoryIcon,Settings,MessageSquare,ArrowUpRight,ShieldCheck,ChevronRight} from 'lucide-react';
import {AppProvider,useApp,useRoute,navigate,inExtension,runtime} from './api';
import {Projects} from './projects';
import {Live} from './live';
import {History} from './history';
import {SettingsPage} from './settings';
import {ReportPage} from './report';
import {Loading} from './shared';
import './styles.css';
const links=[{route:'/projects',icon:FolderKanban,name:'Dự án & dữ liệu'},{route:'/live',icon:Radio,name:'Đang họp'},{route:'/reports',icon:FileText,name:'Báo cáo'},{route:'/meetings',icon:HistoryIcon,name:'Lịch sử'},{route:'/settings',icon:Settings,name:'Cài đặt'}];
function App(){
  const {config,state,loading}=useApp();const route=useRoute();const sidepanel=location.pathname.includes('sidepanel.html');const [health,setHealth]=useState(false);
  useEffect(()=>{let alive=true;const check=()=>fetch(config.url+'/health').then(r=>r.ok).then(v=>{if(alive)setHealth(v);}).catch(()=>{if(alive)setHealth(false);});void check();const timer=setInterval(check,10000);return ()=>{alive=false;clearInterval(timer);};},[config.url]);
  if(loading)return <Loading/>;
  if(sidepanel)return <Live sidepanel/>;
  const project=route.match(/^\/projects\/([^/]+)/);const report=route.match(/^\/meetings\/([^/]+)\/report/);
  const content=route==='/settings'?<SettingsPage/>:route==='/live'?<Live/>:report?<ReportPage key={report[1]} meetingId={report[1]}/>:route==='/reports'?<History reportList/>:route.startsWith('/meetings')?<History/>:<Projects key={project?.[1]||'all'} id={project?.[1]}/>;
  const active=report?'/reports':route.startsWith('/projects')?'/projects':route;
  return <div className="app-shell"><aside className="sidebar"><a className="brand" href="#/projects"><div className="brand-mark"><MessageSquare size={21}/></div><div>meet<span>copilot</span><small>YOUR MEETING COMPANION</small></div></a><div className="workspace-label">KHÔNG GIAN LÀM VIỆC</div><nav aria-label="Điều hướng chính">{links.map(link=><a className={active===link.route?'active':''} href={'#'+link.route} key={link.route}><link.icon size={18}/><span>{link.name}</span>{active===link.route&&<span className="nav-dot"/>}</a>)}</nav><div className="sidebar-bottom"><div className="local-note"><ShieldCheck size={21}/><strong>Trên máy của bạn.</strong><p>Nguồn và lịch sử lưu local.<br/>Bạn chủ động chia sẻ.</p></div><div className="sidebar-profile"><div className="avatar">ME</div><div><strong>Personal workspace</strong><small>Windows · Chrome</small></div></div></div></aside>
    <div className="app-main"><header className="topbar"><div className="breadcrumb">Workspace <ChevronRight size={13}/> <span>{links.find(l=>l.route===active)?.name||'Dự án'}</span></div><div className="row"><span className="backend-status"><i className={'dot '+(health?'green':'red')}/>{health?(config.token?'Backend local sẵn sàng':'Backend · cần pairing'):'Backend chưa kết nối'}</span><span className="top-divider"/><span className="small muted">Local edition</span><div className="avatar small-avatar">M</div></div></header>
    <main className="page-content">{!inExtension&&<div className="preview-banner">Browser preview · giao diện dùng backend thật; capture Meet chạy qua Chrome extension.</div>}{!config.token&&route!=='/settings'&&<div className="connection-banner"><span>Thiết lập kết nối local để bắt đầu.</span><button onClick={()=>navigate('/settings')}>Mở cài đặt <ArrowUpRight size={14}/></button></div>}{content}</main><footer className="app-footer"><span>Meet Copilot · local workspace</span><span>Hiểu rõ hơn. Nói tự tin hơn.</span></footer></div></div>;
}
createRoot(document.getElementById('root')!).render(<AppProvider><App/></AppProvider>);
