
import React, { useEffect, useRef, useState } from 'react';
import { 
  LayoutDashboard, 
  Video, 
  AlertTriangle, 
  FileText, 
  BarChart2, 
  Users, 
  Menu, 
  Bell, 
  LogOut, 
  Globe,
  Activity,
  Cpu,
  UserCheck,
  X,
  Settings
} from 'lucide-react';
import { Page, UserRole } from './types';
import Dashboard from './components/Dashboard';
import LiveMonitoring from './components/LiveMonitoring';
import Alerts from './components/Alerts';
import Reports from './components/Reports';
import CameraManagement from './components/CameraManagement';
import UserManagement from './components/UserManagement';
import Incidents from './components/Incidents';
import Ergonomics from './components/Ergonomics';
import SystemHealth from './components/SystemHealth';
import Configuration from './components/Configuration';
import Login from './components/Login';
import VisionSafeLogo from './components/VisionSafeLogo';
import { LanguageProvider, useLanguage } from './contexts/LanguageContext';
import { AuthAPI, setAuthToken } from './api';

const SidebarItem = ({ 
  icon: Icon, 
  label, 
  isActive, 
  onClick 
}: { 
  icon: any, 
  label: string, 
  isActive: boolean, 
  onClick: () => void 
}) => (
  <button
    onClick={onClick}
    className={`group w-full flex items-center space-x-3 rtl:space-x-reverse px-4 py-3 transition-all duration-200 border-s-2 mb-1 ${
      isActive 
        ? 'bg-vs-orange/10 text-vs-orange border-vs-orange' 
        : 'border-transparent text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100 hover:border-zinc-700'
    }`}
  >
    <Icon size={18} className={`transition-colors ${isActive ? 'text-vs-orange' : 'text-zinc-500 group-hover:text-zinc-300'}`} />
    <span className="font-medium text-sm tracking-wide">{label}</span>
  </button>
);

interface NotificationItem {
  id: number;
  message: string;
  time: string;
  read: boolean;
  type: 'alert' | 'system' | 'info';
}

const AppContent = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUser, setCurrentUser] = useState<{name: string, role: UserRole} | null>(null);
  const [currentPage, setCurrentPage] = useState<Page>(Page.DASHBOARD);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [showNotifications, setShowNotifications] = useState(false);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const { language, setLanguage, dir, t } = useLanguage();

  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const notifWsRef = useRef<WebSocket | null>(null);
  const notifIdCounter = useRef(100);

  const unreadCount = notifications.filter(n => !n.read).length;

  const markAllRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  };

  const dismissNotification = (id: number) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  // Connect to real-time notification WebSocket
  useEffect(() => {
    if (!isAuthenticated) return;

    const token = localStorage.getItem('visionsafe360_token');
    if (!token) return;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const envMeta = (import.meta as any).env ?? {};
    const wsHost = envMeta.VITE_API_BASE_URL
      ? String(envMeta.VITE_API_BASE_URL).replace(/^https?:\/\//, '').replace(/\/+$/, '')
      : `${window.location.host}`;
    const wsUrl = `${wsProtocol}://${wsHost}/ws/notifications?token=${encodeURIComponent(token)}`;

    const connect = () => {
      const ws = new WebSocket(wsUrl);
      notifWsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'keepalive') return;
          if (payload.type === 'incident_created' || payload.type === 'notification') {
            notifIdCounter.current += 1;
            const msg = payload.message || payload.incident?.classification || 'New alert detected';
            setNotifications(prev => [{
              id: notifIdCounter.current,
              message: msg,
              time: 'just now',
              read: false,
              type: 'alert',
            }, ...prev].slice(0, 50));
          }
        } catch {}
      };

      ws.onclose = () => {
        setTimeout(connect, 5000);
      };
    };

    connect();

    return () => {
      if (notifWsRef.current) {
        notifWsRef.current.close();
        notifWsRef.current = null;
      }
    };
  }, [isAuthenticated]);

  useEffect(() => {
    const token = localStorage.getItem('visionsafe360_token');
    if (!token) {
      setIsBootstrapping(false);
      return;
    }

    setAuthToken(token);
    AuthAPI.me()
      .then((user) => {
        setCurrentUser({ name: user.name, role: user.role });
        setIsAuthenticated(true);
        if (user.role === 'Data Analyst') setCurrentPage(Page.REPORTS);
      })
      .catch(() => {
        setAuthToken(null);
        setIsAuthenticated(false);
      })
      .finally(() => setIsBootstrapping(false));
  }, []);

  const handleLogin = (user: {name: string, role: UserRole}, token: string) => {
    setCurrentUser(user);
    setIsAuthenticated(true);
    setAuthToken(token);
    if (user.role === 'Data Analyst') setCurrentPage(Page.REPORTS);
  };

  const handleLogout = () => {
    setAuthToken(null);
    setIsAuthenticated(false);
    setCurrentUser(null);
  };

  const renderPage = () => {
    switch (currentPage) {
      case Page.DASHBOARD: return <Dashboard onViewAlerts={() => setCurrentPage(Page.ALERTS)} />;
      case Page.LIVE_MONITORING: return <LiveMonitoring />;
      case Page.ALERTS: return <Alerts />;
      case Page.INCIDENTS: return <Incidents />;
      case Page.ERGONOMICS: return <Ergonomics />;
      case Page.REPORTS: return <Reports />;
      case Page.CAMERAS: return <CameraManagement />;
      case Page.HEALTH: return <SystemHealth />;
      case Page.USERS: return <UserManagement />;
      case Page.CONFIGURATION: return <Configuration />;
      default: return <Dashboard onViewAlerts={() => setCurrentPage(Page.ALERTS)} />;
    }
  };

  if (isBootstrapping) return null;
  if (!isAuthenticated) return <Login onLogin={handleLogin} />;

  const isAdmin = currentUser?.role === 'Admin';
  const isSafetyEngineer = currentUser?.role === 'Safety Engineer' || isAdmin;
  const isAnalyst = currentUser?.role === 'Data Analyst' || isAdmin;

  const notificationTypeIcon = (type: string) => {
    switch (type) {
      case 'alert': return 'bg-red-500';
      case 'system': return 'bg-blue-500';
      default: return 'bg-vs-orange';
    }
  };

  return (
    <div dir={dir} className="flex h-screen bg-[#050505] text-vs-text overflow-hidden font-sans antialiased">
      {/* Mobile overlay */}
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-20 lg:hidden" 
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      <aside className={`${isSidebarOpen ? 'w-64' : 'w-0 -ms-64'} flex-shrink-0 bg-[#09090b] border-e border-zinc-800 transition-all duration-300 flex flex-col z-30 fixed lg:relative h-full`}>
        <div className="h-16 flex items-center px-5 border-b border-zinc-800 bg-[#09090b]">
          <VisionSafeLogo className="w-8 h-8 me-3" showText={false} />
          <div>
            <span className="font-bold text-base tracking-tight text-white block leading-none">VISIONSAFE</span>
            <span className="text-[10px] font-mono text-vs-orange tracking-widest uppercase">360 Dashboard</span>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto custom-scrollbar px-2 pt-4">
          <div className="mb-6">
            <p className="px-4 text-[10px] font-bold text-zinc-600 uppercase tracking-widest mb-2">{t('monitoring')}</p>
            {isSafetyEngineer && (
              <>
                <SidebarItem icon={LayoutDashboard} label={t('overview')} isActive={currentPage === Page.DASHBOARD} onClick={() => setCurrentPage(Page.DASHBOARD)} />
                <SidebarItem icon={Video} label={t('liveFeeds')} isActive={currentPage === Page.LIVE_MONITORING} onClick={() => setCurrentPage(Page.LIVE_MONITORING)} />
                <SidebarItem icon={AlertTriangle} label={t('alerts')} isActive={currentPage === Page.ALERTS} onClick={() => setCurrentPage(Page.ALERTS)} />
              </>
            )}
            <SidebarItem icon={FileText} label={t('incidents')} isActive={currentPage === Page.INCIDENTS} onClick={() => setCurrentPage(Page.INCIDENTS)} />
            <SidebarItem icon={UserCheck} label={t('ergonomics')} isActive={currentPage === Page.ERGONOMICS} onClick={() => setCurrentPage(Page.ERGONOMICS)} />
          </div>
          
          <div>
            <p className="px-4 text-[10px] font-bold text-zinc-600 uppercase tracking-widest mb-2">{t('analytics')}</p>
            {isAnalyst && <SidebarItem icon={BarChart2} label={t('reports')} isActive={currentPage === Page.REPORTS} onClick={() => setCurrentPage(Page.REPORTS)} />}
          </div>

          {isAdmin && (
            <div className="mt-6">
              <p className="px-4 text-[10px] font-bold text-zinc-600 uppercase tracking-widest mb-2">{t('system')}</p>
              <SidebarItem icon={Activity} label={t('cameras')} isActive={currentPage === Page.CAMERAS} onClick={() => setCurrentPage(Page.CAMERAS)} />
              <SidebarItem icon={Cpu} label={t('health')} isActive={currentPage === Page.HEALTH} onClick={() => setCurrentPage(Page.HEALTH)} />
              <SidebarItem icon={Users} label={t('users')} isActive={currentPage === Page.USERS} onClick={() => setCurrentPage(Page.USERS)} />
              <SidebarItem icon={Settings} label={t('configuration')} isActive={currentPage === Page.CONFIGURATION} onClick={() => setCurrentPage(Page.CONFIGURATION)} />
            </div>
          )}
        </nav>

        <div className="p-4 border-t border-zinc-800 bg-[#09090b]">
           <div className="flex items-center space-x-3 rtl:space-x-reverse">
              <div className="w-10 h-10 rounded-full bg-vs-orange/20 border border-vs-orange/40 flex items-center justify-center text-vs-orange font-bold">
                {currentUser?.name[0]}
              </div>
              <div className="flex-1 overflow-hidden">
                <p className="text-sm font-medium text-zinc-200 truncate">{currentUser?.name}</p>
                <p className="text-[10px] text-zinc-500 uppercase">{t(currentUser?.role.toLowerCase().replace(/ /g, '') as any)}</p>
              </div>
              <button onClick={handleLogout} className="text-zinc-500 hover:text-red-500 transition-colors">
                <LogOut size={18} />
              </button>
           </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#050505]">
        <header className="h-16 bg-[#09090b]/90 backdrop-blur-md border-b border-zinc-800 flex items-center justify-between px-6 z-20">
          <div className="flex items-center">
            <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-2 -ms-2 rounded-md hover:bg-zinc-800 text-zinc-400 transition-colors me-4">
              <Menu size={20} />
            </button>
            <div className="flex flex-col">
               <h1 className="text-sm font-bold text-white tracking-wide uppercase">{t(currentPage.toLowerCase().replace(/ /g, '') as any)}</h1>
               <div className="flex items-center space-x-2 rtl:space-x-reverse">
                  <span className="flex h-2 w-2 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                  <span className="text-[10px] text-zinc-400 font-mono uppercase">{t('systemActive')}</span>
               </div>
            </div>
          </div>
          <div className="flex items-center space-x-4 rtl:space-x-reverse">
            <button onClick={() => setLanguage(language === 'en' ? 'ar' : 'en')} className="flex items-center space-x-1 text-zinc-400 hover:text-white transition-colors border border-zinc-800 px-2 py-1 rounded bg-zinc-900">
              <Globe size={16} />
              <span className="text-xs font-bold uppercase">{language === 'en' ? 'AR' : 'EN'}</span>
            </button>

            {/* Notifications */}
            <div className="relative">
              <button 
                className="p-2 text-zinc-400 hover:text-vs-orange transition-colors relative" 
                onClick={() => setShowNotifications(!showNotifications)}
              >
                <Bell size={20} />
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -end-0.5 min-w-[18px] h-[18px] bg-red-500 rounded-full border-2 border-[#09090b] text-[9px] font-bold text-white flex items-center justify-center px-1">
                    {unreadCount}
                  </span>
                )}
              </button>

              {/* Notification Dropdown */}
              {showNotifications && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setShowNotifications(false)} />
                  <div className="absolute top-12 end-0 w-96 bg-[#0f0f11] border border-zinc-800 rounded-xl shadow-2xl z-50 overflow-hidden animate-in slide-in-from-top-2 duration-200">
                    <div className="p-4 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/30">
                      <h3 className="font-bold text-white text-sm">{t('notifications')}</h3>
                      <div className="flex items-center space-x-3 rtl:space-x-reverse">
                        {unreadCount > 0 && (
                          <button onClick={markAllRead} className="text-[10px] text-vs-orange hover:text-vs-lightOrange font-bold uppercase tracking-wider">
                            {t('markAllRead')}
                          </button>
                        )}
                      </div>
                    </div>
                    {notifications.length === 0 ? (
                      <div className="p-10 text-center">
                        <Bell size={32} className="mx-auto mb-3 text-zinc-700" />
                        <p className="text-zinc-500 text-sm">{t('noNotifications')}</p>
                      </div>
                    ) : (
                      <div className="max-h-80 overflow-y-auto custom-scrollbar">
                        {notifications.map(n => (
                          <div 
                            key={n.id} 
                            className={`p-4 border-b border-zinc-800/50 flex items-start space-x-3 rtl:space-x-reverse hover:bg-zinc-900/40 transition-colors ${!n.read ? 'bg-vs-orange/[0.03]' : ''}`}
                          >
                            <div className={`w-2 h-2 rounded-full mt-2 flex-shrink-0 ${!n.read ? notificationTypeIcon(n.type) : 'bg-zinc-700'}`}></div>
                            <div className="flex-1 min-w-0">
                              <p className={`text-sm leading-relaxed ${!n.read ? 'text-zinc-200' : 'text-zinc-400'}`}>{n.message}</p>
                              <p className="text-[10px] text-zinc-600 mt-1 font-mono">{n.time}</p>
                            </div>
                            <button 
                              onClick={(e) => { e.stopPropagation(); dismissNotification(n.id); }} 
                              className="text-zinc-700 hover:text-zinc-400 transition-colors flex-shrink-0 mt-1"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-hidden relative">
          {renderPage()}
        </main>
      </div>
    </div>
  );
};

const App = () => (
  <LanguageProvider>
    <AppContent />
  </LanguageProvider>
);

export default App;
