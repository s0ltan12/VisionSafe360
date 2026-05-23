import React, { useState, useEffect, useCallback } from 'react';
import { 
  AlertTriangle, 
  Activity, 
  Camera, 
  MoreHorizontal,
  TrendingUp,
  TrendingDown,
  ShieldCheck,
  Clock,
  Timer,
  ExternalLink
} from 'lucide-react';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer
} from 'recharts';
import { Alert as AlertType, Severity } from '../types';
import { useLanguage } from '../contexts/LanguageContext';
import { StatsAPI, AlertsAPI } from '../api';
import { a11yClasses } from '../utils/accessibility';

interface DashboardProps {
  onViewAlerts: () => void;
}

const KPICard = ({ 
  title, 
  value, 
  icon: Icon, 
  trend, 
  trendValue,
  colorBase 
}: { 
  title: string, 
  value: string, 
  icon: any, 
  trend?: 'up' | 'down' | 'neutral',
  trendValue?: string,
  colorBase: 'red' | 'orange' | 'emerald' | 'blue' | 'purple';
}) => {
  const colorStyles = {
    red: { text: 'text-red-500', bg: 'bg-red-500/10', border: 'border-red-500/20' },
    orange: { text: 'text-vs-orange', bg: 'bg-vs-orange/10', border: 'border-vs-orange/20' },
    emerald: { text: 'text-emerald-500', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20' },
    blue: { text: 'text-blue-500', bg: 'bg-blue-500/10', border: 'border-blue-500/20' },
    purple: { text: 'text-purple-500', bg: 'bg-purple-500/10', border: 'border-purple-500/20' },
  };

  const styles = colorStyles[colorBase];

  return (
    <div 
      className="bg-[#0f0f11] p-5 rounded-lg border border-zinc-800 hover:border-zinc-700 transition-colors group relative overflow-hidden"
      role="status"
      aria-label={`${title}: ${value}${trendValue ? ` ${trendValue}` : ''}`}
      aria-live="polite"
    >
      <div className={`absolute -right-6 -top-6 w-24 h-24 rounded-full ${styles.bg} blur-2xl opacity-20 group-hover:opacity-30 transition-opacity`} aria-hidden="true"></div>
      <div className="flex justify-between items-start mb-4 relative z-10">
        <div className={`p-2 rounded-md ${styles.bg} border ${styles.border}`}>
          <Icon className={styles.text} size={20} aria-hidden="true" />
        </div>
        {trend && (
           <div className={`flex items-center space-x-1 rtl:space-x-reverse text-xs font-medium px-2 py-1 rounded-full bg-zinc-900 border border-zinc-800 ${
             trend === 'up' && colorBase === 'red' ? 'text-red-400' : 
             trend === 'down' && colorBase === 'red' ? 'text-emerald-400' : 
             trend === 'up' ? 'text-emerald-400' : 'text-red-400'
           }`}
           aria-label={`Trend ${trend} by ${trendValue}`}
           >
             {trend === 'up' ? <TrendingUp size={12} aria-hidden="true" /> : <TrendingDown size={12} aria-hidden="true" />}
             <span>{trendValue}</span>
           </div>
        )}
      </div>
      <div className="relative z-10">
        <h3 className="text-2xl font-bold text-white tracking-tight mb-1">{value}</h3>
        <p className="text-xs font-medium text-zinc-500 uppercase tracking-wide">{title}</p>
      </div>
    </div>
  );
};


const SeverityBadge = ({ severity }: { severity: Severity }) => {
  const styles = {
    High: 'bg-red-500/10 text-red-500 border-red-500/20',
    Medium: 'bg-vs-orange/10 text-vs-orange border-vs-orange/20',
    Low: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  };
  const { t } = useLanguage();
  return (
    <span 
      className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider border ${styles[severity]}`}
      role="img"
      aria-label={`Severity: ${severity}`}
    >
      {t(severity.toLowerCase() as any)}
    </span>
  );
};

const CompactMetadataRow = ({ alert }: { alert: AlertType }) => (
  <div className="mt-1 flex flex-wrap gap-1.5 text-[9px] font-mono uppercase tracking-wide text-zinc-500">
    {alert.cameraId && <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5">Cam {alert.cameraId}</span>}
    {alert.cameraName && <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5">{alert.cameraName}</span>}
    {alert.workerId && <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5">Worker {alert.workerId}</span>}
    {alert.workerGpuId && <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5">GPU {alert.workerGpuId}</span>}
  </div>
);

const Dashboard: React.FC<DashboardProps> = ({ onViewAlerts }) => {
  const { t, dir } = useLanguage();
  const [stats, setStats] = useState<any>(null);
  const [alerts, setAlerts] = useState<AlertType[]>([]);
  const [chartData, setChartData] = useState<any[]>(() => {
    return Array.from({ length: 7 }).map((_, i) => {
      const d = new Date();
      d.setDate(d.getDate() - 6 + i);
      return {
        name: d.toLocaleDateString('en-US', { weekday: 'short' }),
        incidents: 0
      };
    });
  });
  const [loading, setLoading] = useState(true);

  const fetchDashboardData = useCallback(async () => {
    try {
      setLoading(true);
      const [statsData, alertsData] = await Promise.all([
        StatsAPI.getAll(),
        AlertsAPI.getAll()
      ]);
      setStats(statsData);
      
      if (statsData.trends) {
        const last7Days = Array.from({ length: 7 }).map((_, i) => {
          const d = new Date();
          d.setDate(d.getDate() - 6 + i);
          const yyyy = d.getFullYear();
          const mm = String(d.getMonth() + 1).padStart(2, '0');
          const dd = String(d.getDate()).padStart(2, '0');
          const dateStr = `${yyyy}-${mm}-${dd}`;
          return { 
            name: d.toLocaleDateString('en-US', { weekday: 'short' }), 
            incidents: 0,
            dateStr
          };
        });

        statsData.trends.forEach((item: any) => {
          const match = last7Days.find(d => d.dateStr === item.date);
          if (match) {
            match.incidents = item.count;
          }
        });

        setChartData(last7Days);
      }
      
      setAlerts(alertsData.slice(0, 5));
    } catch (e) {
      console.error('Failed to fetch dashboard data:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  const zones = [
    { name: t('zoneA'), image: 'https://images.unsplash.com/photo-1565034946487-0d7150a275ce?q=80&w=2070', risk: 'High' },
    { name: t('zoneB'), image: 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?q=80&w=2070', risk: 'Medium' },
    { name: t('zoneC'), image: 'https://images.unsplash.com/photo-1590105577767-e21a46b53002?q=80&w=2070', risk: 'High' }
  ];

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-2xl font-bold text-white">{t('safetyOverview')}</h2>
          <p className="text-sm text-zinc-500">{t('realTimeMonitoring')}</p>
        </div>
        <div className="flex space-x-2">
           <span className="px-3 py-1 bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-400 flex items-center">
             <Clock size={12} className="me-2" aria-hidden="true" /> {t('lastUpdated')}: 10:45 AM
           </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title={t('activeAlerts')} value={stats?.active_alerts?.toString() || '0'} icon={AlertTriangle} trend="up" trendValue="+2" colorBase="red" />
        <KPICard title={t('incidents')} value={stats?.total_incidents?.toString() || '0'} icon={Activity} colorBase="orange" />
        <KPICard title={t('resolvedAlerts')} value={stats?.resolved_alerts?.toString() || '0'} icon={ShieldCheck} trend="up" trendValue="+15%" colorBase="emerald" />
        <KPICard title={t('camerasOnline')} value={`${stats?.online_cameras || 0}/${stats?.total_cameras || 0}`} icon={Camera} colorBase="blue" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-[#0f0f11] rounded-lg border border-zinc-800 p-6 flex flex-col">
          <div className="flex justify-between items-center mb-6">
            <h3 className="font-bold text-base text-white">{t('incidentTrends')}</h3>
          </div>
          <div className="flex-1 min-h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} aria-label="7-day incident trends chart">
                <defs>
                  <linearGradient id="colorAlerts" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#FF6A00" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#FF6A00" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#27272a" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#71717a', fontSize: 11}} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{fill: '#71717a', fontSize: 11}} orientation={dir === 'rtl' ? 'right' : 'left'} />
                <Tooltip contentStyle={{backgroundColor: '#18181b', borderRadius: '4px', border: '1px solid #27272a', color: '#fff'}} />
                <Area type="monotone" dataKey="incidents" stroke="#FF6A00" strokeWidth={2} fillOpacity={1} fill="url(#colorAlerts)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-[#0f0f11] rounded-lg border border-zinc-800 p-6 flex flex-col">
           <h3 className="font-bold text-base text-white mb-4">{t('criticalZones')}</h3>
           <div className="space-y-4">
              {zones.map((zone, i) => (
                <div 
                  key={i} 
                  className="flex items-center space-x-3 rtl:space-x-reverse p-3 bg-zinc-900/50 rounded border border-zinc-800 hover:border-vs-orange/30 transition-colors group cursor-pointer"
                  role="button"
                  tabIndex={0}
                  aria-label={`${zone.name} zone with ${zone.risk} risk level`}
                  onClick={() => alert(`Redirecting to live feed for ${zone.name}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      alert(`Redirecting to live feed for ${zone.name}`);
                    }
                  }}
                >
                   <div className="w-16 h-12 bg-black rounded overflow-hidden relative">
                      <img 
                        src={zone.image} 
                        className="w-full h-full object-cover opacity-70 group-hover:opacity-100 transition-opacity"
                        alt={`Zone ${zone.name} overview image`}
                      />
                   </div>
                   <div className="flex-1">
                      <p className="text-sm font-medium text-zinc-200 group-hover:text-vs-orange transition-colors">{zone.name}</p>
                      <p className="text-xs text-zinc-500">Active Sensors</p>
                   </div>
                   <div className={`text-[10px] font-bold px-2 py-0.5 rounded border ${zone.risk === 'High' ? 'text-red-500 bg-red-500/10 border-red-500/20' : 'text-vs-orange bg-vs-orange/10 border-vs-orange/20'}`}>
                      {zone.risk}
                   </div>
                </div>
              ))}
           </div>
           <button 
             onClick={onViewAlerts} 
             className={`mt-auto w-full py-2 bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-white rounded text-xs font-bold uppercase transition-colors flex items-center justify-center space-x-2 rtl:space-x-reverse ${a11yClasses.focusRing}`}
             aria-label="View all events and alerts"
           >
              <span>{t('viewAllEvents')}</span>
              <ExternalLink size={14} aria-hidden="true" />
           </button>
        </div>
      </div>

      <div className="bg-[#0f0f11] rounded-lg border border-zinc-800 flex flex-col overflow-hidden">
        <div className="p-5 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/30">
          <h3 className="font-bold text-base text-white">{t('liveIncidentFeed')}</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-start text-sm text-zinc-400" role="grid" aria-label="Live incident feed table">
            <thead className="bg-zinc-900/50 text-zinc-500 uppercase text-[10px] font-bold tracking-wider border-b border-zinc-800">
              <tr role="row">
                <th className="px-6 py-3 text-start" role="columnheader">{t('severity')}</th>
                <th className="px-6 py-3 text-start" role="columnheader">{t('alertType')}</th>
                <th className="px-6 py-3 text-start" role="columnheader">{t('location')}</th>
                <th className="px-6 py-3 text-start" role="columnheader">{t('timestamp')}</th>
                <th className="px-6 py-3 text-start" role="columnheader">{t('status')}</th>
                <th className="px-6 py-3 text-end" role="columnheader">{t('action')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {alerts.map((alert) => (
                <tr key={alert.id} className="hover:bg-zinc-900/40 transition-colors group" role="row">
                  <td className="px-6 py-3" role="cell"><SeverityBadge severity={alert.severity} /></td>
                  <td className="px-6 py-3" role="cell">
                    <div className="flex items-center space-x-3 rtl:space-x-reverse">
                       <div className="w-10 h-10 rounded bg-black overflow-hidden border border-zinc-800">
                          <img 
                            src={alert.thumbnail} 
                            className="w-full h-full object-cover" 
                            alt={`Alert video frame: ${alert.type}`}
                          />
                       </div>
                      <span className="text-zinc-200 font-semibold">{alert.type}</span>
                    </div>
                    <CompactMetadataRow alert={alert} />
                  </td>
                  <td className="px-6 py-4 text-zinc-400 font-mono text-xs" role="cell">{alert.zone}</td>
                  <td className="px-6 py-3 text-zinc-500 font-mono text-xs" role="cell">{alert.timestamp}</td>
                  <td className="px-6 py-3" role="cell">
                    <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${
                      alert.status === 'New' ? 'bg-blue-900/30 text-blue-400 border-blue-800' : 'bg-zinc-800 text-zinc-400 border-zinc-700'
                    }`}>
                      {t(alert.status.toLowerCase() as any)}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-end" role="cell">
                    <button 
                      className={`p-1 hover:bg-zinc-800 rounded text-zinc-500 hover:text-white transition-colors ${a11yClasses.focusRing}`}
                      onClick={() => window.alert(`Action options for ${alert.id}`)}
                      aria-label={`Action menu for alert ${alert.id}`}
                    >
                       <MoreHorizontal size={16} aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
