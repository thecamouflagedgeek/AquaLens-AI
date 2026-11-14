import React,{useState} from 'react';
import {BrowserRouter,Routes,Route,Navigate,Outlet,NavLink,Link,useLocation,useNavigate} from 'react-router-dom';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MotionConfig,motion} from 'framer-motion';
import {Waves,LayoutDashboard,Fingerprint,ChartNoAxesCombined,ClipboardCheck,Menu,LogOut,Eye,EyeOff,PanelLeftClose} from 'lucide-react';
import LandingPage from '../LandingPage';
import {AuthProvider,useAuth,MonitoringProvider,useMonitoring} from './state';
import {message} from './api';
import {StationControls} from './components';
import {DashboardPage,AnalysisPage,FindingsPage,PredictionsPage,RecommendationsPage} from './pages';
import './platform.css';
import IndiaWorkspace from './IndiaWorkspace';
import {workspaceHome,loginDestination} from './workspace';
const client=new QueryClient({defaultOptions:{queries:{staleTime:60000,retry:1,refetchOnWindowFocus:false}}});
function Protected({workspace='existing'}){const a=useAuth();const location=useLocation();if(a.pending)return <div className="portal session-state" role="status">Verifying your session.</div>;if(!a.user)return <Navigate to="/login" state={{from:location.pathname+location.search}} replace/>;const actual=a.user.workspace||'existing';return actual===workspace?<Outlet/>:<Navigate to={workspaceHome(a.user)} replace/>;}
function Login(){const a=useAuth();const navigate=useNavigate();const location=useLocation();const [show,setShow]=useState(false);const [pending,setPending]=useState(false);const [error,setError]=useState('');async function submit(e){e.preventDefault();setPending(true);setError('');const form=new FormData(e.currentTarget);try{const user=await a.login({username:form.get('username'),password:form.get('password')});navigate(loginDestination(user,location.state?.from),{replace:true});}catch(err){setError(message(err));}finally{setPending(false);}}if(a.user)return <Navigate to={workspaceHome(a.user)} replace/>;return <main className="portal login-page login-reference">
  <div className="login-frame">
    <div className="login-story">
      <Link to="/" className="brand"><Waves aria-hidden="true"/> AquaLens AI</Link>
      <div className="login-story-content">
        <span className="login-pill">Water monitoring portal</span>
        <h1>Start your journey</h1>
        <p>Sign in to explore your water monitoring workspace.</p>
        <ol className="login-steps">
          <li><span>1</span>Sign in to your account</li>
          <li><span>2</span>Select a monitoring station</li>
          <li><span>3</span>Explore water fingerprints</li>
        </ol>
      </div>
    </div>
    <motion.section className="login-card" initial={{opacity:0,y:12}} animate={{opacity:1,y:0}}>
      <h2>Welcome back</h2>
      <form onSubmit={submit}>
        <label>Username<input name="username" placeholder="Enter your username" autoComplete="username" required/></label>
        <label>Password<div className="password"><input name="password" placeholder="Enter your password" type={show?'text':'password'} autoComplete="current-password" required/><button type="button" aria-label={show?'Hide password':'Show password'} onClick={()=>setShow(!show)}>{show?<EyeOff size={18}/>:<Eye size={18}/>}</button></div></label>
        {error&&<p className="error" role="alert">{error}</p>}
        <button className="primary" disabled={pending||a.pending}>{pending?'Signing in…':'Continue'}</button>
      </form>
      <p className="caption">Use your authorized AquaLens monitoring account.</p>
      <Link className="login-return" to="/">Return to AquaLens</Link>
    </motion.section>
  </div>
</main>;}
const nav=[['/dashboard','Dashboard',LayoutDashboard],['/findings','Detailed Findings',Fingerprint],['/predictions','Future Predictions',ChartNoAxesCombined],['/recommendations','Recommendations',ClipboardCheck]];
function Shell() {
  const a = useAuth();
  const m = useMonitoring();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const title = location.pathname.includes('/analysis/') ? 'Detailed Score Analysis' : nav.find(n => n[0] === location.pathname)?.[1];
  const account = a.user?.name || a.user?.username || a.user?.email || 'Authorized user';

  async function logout() {
    setBusy(true);
    try { await a.logout(); navigate('/', { replace: true }); }
    catch (err) { setError(`Unable to terminate the session. ${message(err)}`); }
    finally { setBusy(false); }
  }

  return <div className="portal admin-workspace">
    <a href="#main-content" className="skip-link">Skip to monitoring content</a>
    <header className="admin-topbar">
      <Link to="/" className="admin-brand"><Waves aria-hidden="true"/><span>AquaLens<small>MONITORING</small></span></Link>
      <div className="admin-account"><span className="admin-avatar" title={account} aria-label={account}>{account.slice(0, 2).toUpperCase()}</span><button type="button" onClick={logout} disabled={busy} title="Sign out" aria-label={busy ? 'Signing out' : 'Sign out'}><LogOut size={18}/></button></div>
    </header>
    <nav className="admin-rail" aria-label="Monitoring workspace">
      {nav.map(([to, label, Icon]) => <NavLink key={to} to={to} end={to === '/dashboard' && !location.pathname.includes('/analysis/')} title={label} aria-label={label}><Icon size={19} aria-hidden="true"/></NavLink>)}
    </nav>
    <main id="main-content" className="admin-main">
      <header className="admin-heading"><div><span className="eyebrow">WATER FINGERPRINTING · MONITORING WORKSPACE</span><h2>{title}</h2></div><small>{m.stationRecord?.name || 'No station selected'}</small></header>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="admin-filters"><StationControls/></div>
      <motion.div key={location.pathname} initial={{opacity:0,y:6}} animate={{opacity:1,y:0}} transition={{duration:0.18}}><Outlet/></motion.div>
      <footer className="platform-footer">AquaLens AI · Traceable observations. Source-specific evidence.</footer>
    </main>
  </div>;
}
export default function AppRouter(){return <QueryClientProvider client={client}><MotionConfig reducedMotion="user"><BrowserRouter><AuthProvider><Routes><Route path="/" element={<LandingPage/>}/><Route path="/login" element={<Login/>}/><Route element={<Protected workspace="india"/>}><Route path="/india/dashboard" element={<IndiaWorkspace/>}/></Route><Route element={<Protected/>}><Route element={<MonitoringProvider><Shell/></MonitoringProvider>}><Route path="/dashboard" element={<DashboardPage/>}/><Route path="/dashboard/analysis/:stationId" element={<AnalysisPage/>}/><Route path="/findings" element={<FindingsPage/>}/><Route path="/predictions" element={<PredictionsPage/>}/><Route path="/recommendations" element={<RecommendationsPage/>}/></Route></Route><Route path="*" element={<div className="portal session-state"><h1>Page not found</h1><Link to="/">Return to AquaLens</Link></div>}/></Routes></AuthProvider></BrowserRouter></MotionConfig></QueryClientProvider>;}
