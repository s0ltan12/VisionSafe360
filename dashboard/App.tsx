import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
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
  Volume2,
  VolumeX
} from 'lucide-react';
import { NotificationRecord, Page, UserRole } from './types';
import VisionSafeLogo from './components/VisionSafeLogo';
import { LanguageProvider, useLanguage } from './contexts/LanguageContext';
import { AuthAPI, NotificationsAPI, setAuthToken } from './api';
import { a11yClasses } from './utils/accessibility';
import {
  getNotificationSoundEnabled,
  playDangerNotificationSound,
  playNotificationSound,
  setNotificationSoundEnabled,
  unlockNotificationSound,
} from './utils/notificationSound';

const Dashboard = lazy(() => import('./components/Dashboard'));
const LiveMonitoring = lazy(() => import('./components/LiveMonitoring'));
const Alerts = lazy(() => import('./components/Alerts'));
const Reports = lazy(() => import('./components/Reports'));
const CameraManagement = lazy(() => import('./components/CameraManagement'));
const UserManagement = lazy(() => import('./components/UserManagement'));
const Incidents = lazy(() => import('./components/Incidents'));
const Ergonomics = lazy(() => import('./components/Ergonomics'));
const SystemHealth = lazy(() => import('./components/SystemHealth'));
const Login = lazy(() => import('./components/Login'));

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
    role="menuitem"
    aria-current={isActive ? 'page' : undefined}
    aria-label={`${label}${isActive ? ', current page' : ''}`}
    className={`group min-w-0 w-full flex items-center space-x-3 rtl:space-x-reverse px-4 py-3 transition-all duration-200 border-s-2 mb-1 ${a11yClasses.focusRing} ${
      isActive 
        ? 'bg-vs-orange/10 text-vs-orange border-vs-orange' 
        : 'border-transparent text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100 hover:border-zinc-700'
    }`}
  >
    <Icon size={18} className={`transition-colors ${isActive ? 'text-vs-orange' : 'text-zinc-500 group-hover:text-zinc-300'}`} aria-hidden="true" />
    <span className="min-w-0 truncate font-medium text-sm tracking-wide">{label}</span>
  </button>
);

interface NotificationItem {
  id: string;
  message: string;
  time: string;
  read: boolean;
  type: 'alert' | 'system' | 'info';
}

const toNotificationItem = (record: NotificationRecord): NotificationItem => ({
  id: record.id,
  message: record.message,
  time: record.createdAt ? new Date(record.createdAt).toLocaleString() : 'just now',
  read: record.isRead,
  type: record.type === 'alert' || record.type === 'system' ? record.type : 'info',
});

const shouldPlayNotificationSound = (payload: any): boolean => {
  if (!payload || payload.type === 'keepalive') return false;
  if (payload.type === 'incident_created') return true;
  if (payload.type !== 'notification') return false;
  const notificationType = String(payload.notification_type ?? '').toLowerCase();
  return notificationType === 'alert';
};

const isDangerNotification = (payload: any): boolean => {
  const severity = String(
    payload?.severity ??
    payload?.incident?.severity ??
    payload?.incident?.riskLevel ??
    ''
  ).toLowerCase();
  return severity === 'critical' || severity === 'high';
};

const PageFallback = () => (
  <div className="h-full w-full flex items-center justify-center bg-[#050505] text-zinc-300">
    <div
      className="w-7 h-7 border-2 border-zinc-700 border-t-vs-orange rounded-full animate-spin"
      aria-label="Loading view"
    />
  </div>
);

const AppContent = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUser, setCurrentUser] = useState<{name: string, role: UserRole} | null>(null);
  const [currentPage, setCurrentPage] = useState<Page>(Page.DASHBOARD);
  const [targetAlertId, setTargetAlertId] = useState<string | null>(null);
  const [targetIncidentId, setTargetIncidentId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isSoundEnabled, setIsSoundEnabled] = useState(() => getNotificationSoundEnabled());
  const { language, setLanguage, dir, t } = useLanguage();

  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const notifWsRef = useRef<WebSocket | null>(null);
  const unreadCount = notifications.filter(n => !n.read).length;

  const refreshNotifications = useCallback(async () => {
    try {
      const records = await NotificationsAPI.getAll();
      setNotifications(records.map(toNotificationItem));
    } catch (error) {
      console.error('Failed to load notifications:', error);
    }
  }, []);

  const markAllRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
    NotificationsAPI.markAllRead().catch((error) => {
      console.error('Failed to mark notifications read:', error);
      void refreshNotifications();
    });
  };

  const dismissNotification = (id: string) => {
    const previous = notifications;
    setNotifications(prev => prev.filter(n => n.id !== id));
    NotificationsAPI.delete(id).catch((error) => {
      console.error('Failed to dismiss notification:', error);
      setNotifications(previous);
    });
  };

  const toggleNotificationSound = () => {
    const next = !isSoundEnabled;
    setIsSoundEnabled(next);
    setNotificationSoundEnabled(next);
    if (next) {
      unlockNotificationSound();
    }
  };

  useEffect(() => {
    const unlock = () => unlockNotificationSound();
    window.addEventListener('pointerdown', unlock, { once: true });
    window.addEventListener('keydown', unlock, { once: true });
    return () => {
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
    };
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    void refreshNotifications();
  }, [isAuthenticated, refreshNotifications]);

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
            if (shouldPlayNotificationSound(payload)) {
              if (isDangerNotification(payload)) {
                playDangerNotificationSound();
              } else {
                playNotificationSound();
              }
            }
            void refreshNotifications();
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
  }, [isAuthenticated, refreshNotifications]);

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

  const handlePageChange = (page: Page) => {
    setCurrentPage(page);
    setIsSidebarOpen(false);
  };

  const openAlertFromIncident = useCallback((alertId: string) => {
    setTargetAlertId(alertId);
    setTargetIncidentId(null);
    setCurrentPage(Page.ALERTS);
    setIsSidebarOpen(false);
  }, []);

  const openIncidentFromAlert = useCallback((incidentId: string) => {
    setTargetIncidentId(incidentId);
    setTargetAlertId(null);
    setCurrentPage(Page.INCIDENTS);
    setIsSidebarOpen(false);
  }, []);

  const renderPage = () => {
    switch (currentPage) {
      case Page.DASHBOARD: return <Dashboard onViewAlerts={() => setCurrentPage(Page.ALERTS)} />;
      case Page.LIVE_MONITORING: return <LiveMonitoring />;
      case Page.ALERTS: return (
        <Alerts
          targetAlertId={targetAlertId}
          onTargetAlertOpened={() => setTargetAlertId(null)}
          onOpenIncident={openIncidentFromAlert}
        />
      );
      case Page.INCIDENTS: return (
        <Incidents
          currentUserRole={currentUser?.role}
          targetIncidentId={targetIncidentId}
          onTargetIncidentOpened={() => setTargetIncidentId(null)}
          onOpenAlert={openAlertFromIncident}
        />
      );
      case Page.ERGONOMICS: return <Ergonomics />;
      case Page.REPORTS: return <Reports />;
      case Page.CAMERAS: return <CameraManagement />;
      case Page.HEALTH: return <SystemHealth />;
      case Page.USERS: return <UserManagement />;
      default: return <Dashboard onViewAlerts={() => setCurrentPage(Page.ALERTS)} />;
    }
  };

  if (isBootstrapping) return null;
  if (!isAuthenticated) {
    return (
      <Suspense fallback={<PageFallback />}>
        <Login onLogin={handleLogin} />
      </Suspense>
    );
  }

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

  const navigationContent = (
    <>
      <div className="mb-6">
        <p className="px-4 text-[10px] font-bold text-zinc-600 uppercase tracking-widest mb-2">{t('monitoring')}</p>
        {isSafetyEngineer && (
          <>
            <SidebarItem icon={LayoutDashboard} label={t('overview')} isActive={currentPage === Page.DASHBOARD} onClick={() => handlePageChange(Page.DASHBOARD)} />
            <SidebarItem icon={Video} label={t('liveFeeds')} isActive={currentPage === Page.LIVE_MONITORING} onClick={() => handlePageChange(Page.LIVE_MONITORING)} />
            <SidebarItem icon={AlertTriangle} label={t('alerts')} isActive={currentPage === Page.ALERTS} onClick={() => handlePageChange(Page.ALERTS)} />
          </>
        )}
        <SidebarItem icon={FileText} label={t('incidents')} isActive={currentPage === Page.INCIDENTS} onClick={() => handlePageChange(Page.INCIDENTS)} />
        <SidebarItem icon={UserCheck} label={t('ergonomics')} isActive={currentPage === Page.ERGONOMICS} onClick={() => handlePageChange(Page.ERGONOMICS)} />
      </div>
      
      <div>
        <p className="px-4 text-[10px] font-bold text-zinc-600 uppercase tracking-widest mb-2">{t('analytics')}</p>
        {isAnalyst && <SidebarItem icon={BarChart2} label={t('reports')} isActive={currentPage === Page.REPORTS} onClick={() => handlePageChange(Page.REPORTS)} />}
      </div>

      {isAdmin && (
        <div className="mt-6">
          <p className="px-4 text-[10px] font-bold text-zinc-600 uppercase tracking-widest mb-2">{t('system')}</p>
          <SidebarItem icon={Activity} label={t('cameras')} isActive={currentPage === Page.CAMERAS} onClick={() => handlePageChange(Page.CAMERAS)} />
          <SidebarItem icon={Cpu} label={t('health')} isActive={currentPage === Page.HEALTH} onClick={() => handlePageChange(Page.HEALTH)} />
          <SidebarItem icon={Users} label={t('users')} isActive={currentPage === Page.USERS} onClick={() => handlePageChange(Page.USERS)} />
        </div>
      )}
    </>
  );

  return (
    <div dir="ltr" className={`flex h-screen w-full max-w-full bg-[#050505] text-vs-text overflow-hidden font-sans antialiased ${dir === 'rtl' ? 'md:flex-row-reverse' : ''}`}>
      {/* Mobile overlay */}
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/60 z-40 md:hidden" 
          onClick={() => setIsSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside 
        dir={dir}
        className="hidden md:flex h-full w-64 shrink-0 flex-col bg-[#09090b] border-e border-zinc-800"
        role="navigation"
        aria-label="Main navigation"
      >
        <div className="h-16 flex items-center px-5 border-b border-zinc-800 bg-[#09090b]">
          <VisionSafeLogo className="w-8 h-8 me-3" showText={false} />
          <div>
            <span className="font-bold text-base tracking-tight text-white block leading-none">VISIONSAFE</span>
            <span className="text-[10px] font-mono text-vs-orange tracking-widest uppercase">360 Dashboard</span>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar px-2 pt-4" role="menu">
          {navigationContent}
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
              <button 
                onClick={handleLogout} 
                aria-label="Sign out"
                className={`text-zinc-500 hover:text-red-500 transition-colors ${a11yClasses.focusRing}`}
              >
                <LogOut size={18} />
              </button>
           </div>
        </div>
      </aside>

      <div dir={dir} className="min-w-0 flex-1 flex flex-col h-full overflow-hidden bg-[#050505]">
        <header className="h-16 bg-[#09090b]/90 backdrop-blur-md border-b border-zinc-800 flex items-center justify-between gap-3 px-4 sm:px-6 z-20">
          <div className="min-w-0 flex items-center">
            <button 
              onClick={() => setIsSidebarOpen(!isSidebarOpen)} 
              aria-label={isSidebarOpen ? 'Close navigation menu' : 'Open navigation menu'}
              aria-expanded={isSidebarOpen}
              className={`md:hidden p-2 -ms-2 rounded-md hover:bg-zinc-800 text-zinc-400 transition-colors me-4 ${a11yClasses.focusRing}`}
            >
              <Menu size={20} aria-hidden="true" />
            </button>
            <div className="min-w-0 flex flex-col">
               <h1 className="truncate text-sm font-bold text-white tracking-wide uppercase">{t(currentPage.toLowerCase().replace(/ /g, '') as any)}</h1>
               <div className="flex items-center space-x-2 rtl:space-x-reverse">
                  <span className="flex h-2 w-2 relative" aria-hidden="true">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                  <span className="truncate text-[10px] text-zinc-400 font-mono uppercase">{t('systemActive')}</span>
               </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center space-x-2 sm:space-x-4 rtl:space-x-reverse">
            <button 
              onClick={() => setLanguage(language === 'en' ? 'ar' : 'en')} 
              aria-label={`Switch language to ${language === 'en' ? 'Arabic' : 'English'}`}
              className={`flex items-center space-x-1 text-zinc-400 hover:text-white transition-colors border border-zinc-800 px-2 py-1 rounded bg-zinc-900 ${a11yClasses.focusRing}`}
            >
              <Globe size={16} aria-hidden="true" />
              <span className="text-xs font-bold uppercase">{language === 'en' ? 'AR' : 'EN'}</span>
            </button>

            <button
              onClick={toggleNotificationSound}
              aria-label={isSoundEnabled ? 'Mute notification sound' : 'Enable notification sound'}
              aria-pressed={isSoundEnabled}
              title={isSoundEnabled ? 'Mute notification sound' : 'Enable notification sound'}
              className={`p-2 text-zinc-400 hover:text-vs-orange transition-colors border border-zinc-800 rounded bg-zinc-900 ${a11yClasses.focusRing}`}
            >
              {isSoundEnabled ? <Volume2 size={18} aria-hidden="true" /> : <VolumeX size={18} aria-hidden="true" />}
            </button>

            {/* Notifications */}
            <div className="relative">
              <button 
                className={`p-2 text-zinc-400 hover:text-vs-orange transition-colors relative ${a11yClasses.focusRing}`}
                onClick={() => setShowNotifications(!showNotifications)}
                aria-label={`Notifications ${unreadCount > 0 ? `, ${unreadCount} unread` : ''}`}
                aria-expanded={showNotifications}
                aria-haspopup="true"
              >
                <Bell size={20} aria-hidden="true" />
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -end-0.5 min-w-[18px] h-[18px] bg-red-500 rounded-full border-2 border-[#09090b] text-[9px] font-bold text-white flex items-center justify-center px-1" aria-atomic="true">
                    {unreadCount}
                  </span>
                )}
              </button>

              {/* Notification Dropdown */}
              {showNotifications && (
                <>
                  <div 
                    className="fixed inset-0 z-40" 
                    onClick={() => setShowNotifications(false)}
                    aria-hidden="true"
                  />
                  <div 
                    className="absolute top-12 end-0 w-[calc(100vw-2rem)] max-w-sm bg-[#0f0f11] border border-zinc-800 rounded-xl shadow-2xl z-50 overflow-hidden animate-in slide-in-from-top-2 duration-200"
                    role="region"
                    aria-label="Notifications panel"
                    aria-live="polite"
                  >
                    <div className="p-4 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/30">
                      <h3 className="font-bold text-white text-sm">{t('notifications')}</h3>
                      <div className="flex items-center space-x-3 rtl:space-x-reverse">
                        {unreadCount > 0 && (
                          <button 
                            onClick={markAllRead} 
                            className={`text-[10px] text-vs-orange hover:text-vs-lightOrange font-bold uppercase tracking-wider ${a11yClasses.focusRing}`}
                            aria-label="Mark all notifications as read"
                          >
                            {t('markAllRead')}
                          </button>
                        )}
                      </div>
                    </div>
                    {notifications.length === 0 ? (
                      <div className="p-10 text-center">
                        <Bell size={32} className="mx-auto mb-3 text-zinc-700" aria-hidden="true" />
                        <p className="text-zinc-500 text-sm">{t('noNotifications')}</p>
                      </div>
                    ) : (
                      <div className="max-h-80 overflow-y-auto custom-scrollbar">
                        {notifications.map(n => (
                          <div 
                            key={n.id} 
                            className={`p-4 border-b border-zinc-800/50 flex items-start space-x-3 rtl:space-x-reverse hover:bg-zinc-900/40 transition-colors ${!n.read ? 'bg-vs-orange/[0.03]' : ''}`}
                            role="article"
                          >
                            <div className={`w-2 h-2 rounded-full mt-2 flex-shrink-0 ${!n.read ? notificationTypeIcon(n.type) : 'bg-zinc-700'}`} aria-hidden="true"></div>
                            <div className="flex-1 min-w-0">
                              <p className={`text-sm leading-relaxed ${!n.read ? 'text-zinc-200' : 'text-zinc-400'}`}>{n.message}</p>
                              <p className="text-[10px] text-zinc-600 mt-1 font-mono">{n.time}</p>
                            </div>
                            <button 
                              onClick={(e) => { e.stopPropagation(); dismissNotification(n.id); }}
                              aria-label={`Dismiss notification: ${n.message}`}
                              className={`text-zinc-700 hover:text-zinc-400 transition-colors flex-shrink-0 mt-1 ${a11yClasses.focusRing}`}
                            >
                              <X size={14} aria-hidden="true" />
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
        {isSidebarOpen && (
          <nav
            className="fixed inset-x-0 top-16 z-50 max-h-[calc(100vh-4rem)] overflow-y-auto border-b border-zinc-800 bg-[#09090b] px-2 py-4 shadow-2xl md:hidden"
            role="menu"
            aria-label="Mobile navigation"
          >
            {navigationContent}
          </nav>
        )}
        <main className="min-w-0 flex-1 overflow-hidden relative" role="main">
          <Suspense fallback={<PageFallback />}>{renderPage()}</Suspense>
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
