import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  AreaChart,
  Area,
} from 'recharts';
import { Download, Calendar, TrendingUp, ShieldAlert, UserCheck } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';
import { AlertsAPI, AnalyticsAPI, IncidentsAPI } from '../api';
import { Alert, AnalyticsStats, Incident } from '../types';
import { Button, PageShell, Panel } from './ui';

const COLORS = ['#FF6A00', '#FF8A3A', '#3b82f6', '#4b5563', '#10b981', '#ef4444'];

const formatTrend = (current: number, previous: number) => {
  if (previous === 0) {
    return current > 0 ? `+${current}` : '0';
  }
  const change = ((current - previous) / previous) * 100;
  if (Math.abs(change) < 0.1) return '0%';
  return `${change > 0 ? '+' : ''}${change.toFixed(1)}%`;
};

const KPICard = ({ label, value, trend, icon: Icon }: any) => (
  <Panel className="hover:border-zinc-700 transition-colors">
    <div className="flex justify-between items-start mb-4">
      <div className="p-2 bg-zinc-900 rounded-lg border border-zinc-800 text-vs-orange">
        <Icon size={20} />
      </div>
      {trend && (
        <div className="text-[10px] font-bold text-emerald-400 flex items-center space-x-1 rtl:space-x-reverse">
          <TrendingUp size={12} />
          <span>{trend}</span>
        </div>
      )}
    </div>
    <p className="text-2xl font-bold text-white mb-1">{value}</p>
    <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-widest">{label}</p>
  </Panel>
);

const EmptyPanel = ({ label }: { label: string }) => (
  <div className="h-[300px] flex items-center justify-center rounded-lg border border-dashed border-zinc-800 bg-zinc-950/30">
    <p className="text-xs font-bold uppercase tracking-widest text-zinc-600">{label}</p>
  </div>
);

const Reports = () => {
  const { t, dir } = useLanguage();
  const [stats, setStats] = useState<AnalyticsStats | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const loadAnalytics = useCallback(async () => {
    try {
      setLoading(true);
      const [statsData, alertsData, incidentsData] = await Promise.all([
        AnalyticsAPI.getStats(),
        AlertsAPI.getAll(),
        IncidentsAPI.getAll(),
      ]);
      setStats(statsData);
      setAlerts(alertsData);
      setIncidents(incidentsData);
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'Failed to load analytics data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAnalytics();
    const timer = window.setInterval(loadAnalytics, 10000);
    return () => window.clearInterval(timer);
  }, [loadAnalytics]);

  const trendData = useMemo(() => {
    const now = new Date();
    const days: Array<{ date: string; label: string; count: number }> = [];
    for (let offset = 6; offset >= 0; offset -= 1) {
      const day = new Date(now);
      day.setHours(0, 0, 0, 0);
      day.setDate(day.getDate() - offset);
      const key = day.toISOString().slice(0, 10);
      days.push({
        date: key,
        label: day.toLocaleDateString('en-US', { weekday: 'short' }),
        count: 0,
      });
    }
    const trendMap = new Map(days.map((day) => [day.date, day]));
    incidents.forEach((incident) => {
      if (!incident.createdAt) return;
      const parsed = new Date(incident.createdAt);
      if (Number.isNaN(parsed.getTime())) return;
      const key = parsed.toISOString().slice(0, 10);
      const bucket = trendMap.get(key);
      if (bucket) bucket.count += 1;
    });
    return days.map((day) => ({
      name: day.label,
      date: day.date,
      incidents: day.count,
    }));
  }, [incidents]);

  const hazardData = useMemo(() => {
    const counts = new Map<string, number>();
    alerts.forEach((alert) => {
      const name = alert.type || 'Other';
      counts.set(name, (counts.get(name) ?? 0) + 1);
    });
    return Array.from(counts.entries()).map(([name, value]) => ({ name, value }));
  }, [alerts]);

  const hasTrendData = trendData.some((point) => point.incidents > 0);
  const hasDistributionData = hazardData.some((point) => point.value > 0);

  const handleExport = () => {
    setIsExporting(true);
    const csvHeaders = 'Date,Incidents';
    const csvRows = trendData.map((point) => `${point.date},${point.incidents}`).join('\n');
    const csvContent = `${csvHeaders}\n${csvRows}`;
    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'safety_analytics_report.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
    setIsExporting(false);
  };

  return (
    <PageShell
      title={t('reports')}
      description="Global safety trends and AI performance analytics."
      actions={
        <>
          <Button icon={<Calendar size={18} />}>Last 7 Days</Button>
          <Button
            disabled={isExporting || loading || trendData.length === 0}
            isLoading={isExporting}
            onClick={handleExport}
            variant="primary"
            icon={<Download size={18} />}
          >
            {isExporting ? 'Generating...' : t('exportCSV')}
          </Button>
        </>
      }
    >

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          label="Total Incidents"
          value={loading ? '...' : String(stats?.totalIncidents ?? 0)}
          trend={stats ? formatTrend(stats.incidentsLast7Days, stats.incidentsPrevious7Days) : undefined}
          icon={ShieldAlert}
        />
        <KPICard label="Safety Score" value={loading ? '...' : `${(stats?.safetyScore ?? 0).toFixed(1)}%`} icon={UserCheck} />
        <KPICard label="Falls Detected" value={loading ? '...' : String(stats?.fallsDetected ?? 0)} icon={Activity} />
        <KPICard label="Active Alerts" value={loading ? '...' : String(stats?.activeAlerts ?? 0)} icon={ShieldAlert} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Panel className="lg:col-span-2 p-6">
          <h3 className="font-bold text-white mb-6 uppercase text-[10px] tracking-widest opacity-60">Weekly Incident Trend</h3>
          {loading ? (
            <div className="h-[300px] animate-pulse rounded-lg bg-zinc-950/60" />
          ) : hasTrendData ? (
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trendData}>
                  <defs>
                    <linearGradient id="colorAlerts" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#FF6A00" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#FF6A00" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#262626"/>
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#4b5563', fontSize: 10}} />
                  <YAxis axisLine={false} tickLine={false} tick={{fill: '#4b5563', fontSize: 10}} orientation={dir === 'rtl' ? 'right' : 'left'} allowDecimals={false} />
                  <Tooltip contentStyle={{backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px'}} />
                  <Area type="monotone" dataKey="incidents" stroke="#FF6A00" fillOpacity={1} fill="url(#colorAlerts)" strokeWidth={3} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyPanel label="No incidents in this period" />
          )}
        </Panel>

        <Panel className="p-6">
          <h3 className="font-bold text-white mb-6 uppercase text-[10px] tracking-widest opacity-60">Violation Distribution</h3>
          {loading ? (
            <div className="h-[300px] animate-pulse rounded-lg bg-zinc-950/60" />
          ) : hasDistributionData ? (
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={hazardData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={8}
                    dataKey="value"
                  >
                    {hazardData.map((entry, index) => (
                      <Cell key={`cell-${entry.name}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px'}} />
                  <Legend verticalAlign="bottom" height={36} wrapperStyle={{fontSize: '11px'}}/>
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyPanel label="No alerts by type yet" />
          )}
        </Panel>
      </div>
    </PageShell>
  );
};

export default Reports;
