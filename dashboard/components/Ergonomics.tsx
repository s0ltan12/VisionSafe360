
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from 'recharts';
import { UserCheck, AlertCircle, ShieldAlert } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';
import { ErgonomicsAPI } from '../api';
import { ErgonomicRecord, ErgonomicStats } from '../types';

const chartColorForValue = (value: number) => {
  if (value >= 10) return '#ef4444';
  if (value >= 5) return '#FF6A00';
  return '#fb923c';
};

const weekdayLabel = (dateValue: string) => {
  const parsed = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return dateValue;
  return parsed.toLocaleDateString('en-US', { weekday: 'short' });
};

const EmptyState = ({ title, description }: { title: string; description: string }) => (
  <div className="flex h-[300px] w-full flex-col items-center justify-center gap-3 text-center">
    <div className="h-10 w-10 rounded-full border border-zinc-800 bg-zinc-900" />
    <p className="text-sm font-semibold text-zinc-300">{title}</p>
    <p className="max-w-sm text-xs leading-relaxed text-zinc-500">{description}</p>
  </div>
);

const MetricCard = ({
  icon,
  value,
  label,
  hint,
}: {
  icon: React.ReactNode;
  value: string;
  label: string;
  hint: string;
}) => (
  <div className="bg-[#0f0f11] p-5 rounded-xl border border-zinc-800">
    <div className="flex justify-between items-start mb-2">
      <div className="text-vs-orange">{icon}</div>
      <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wide">{hint}</span>
    </div>
    <p className="text-2xl font-bold text-white">{value}</p>
    <p className="text-xs text-zinc-500 uppercase tracking-widest">{label}</p>
  </div>
);

const Ergonomics = () => {
  const { t, dir } = useLanguage();
  const [stats, setStats] = useState<ErgonomicStats | null>(null);
  const [records, setRecords] = useState<ErgonomicRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadErgonomics = useCallback(async () => {
    try {
      setLoading(true);
      const [statsData, recordsData] = await Promise.all([
        ErgonomicsAPI.getStats(7),
        ErgonomicsAPI.getRecords(500),
      ]);
      setStats(statsData);
      setRecords(recordsData);
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'Failed to load ergonomics data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadErgonomics();
    const timer = window.setInterval(() => {
      loadErgonomics();
    }, 10000);
    return () => window.clearInterval(timer);
  }, [loadErgonomics]);

  const trendData = useMemo(() => (
    (stats?.trend ?? []).map((point) => ({
      name: weekdayLabel(point.date),
      score: point.avgRulaScore,
      count: point.count,
    }))
  ), [stats]);

  const zoneRisk = useMemo(() => (
    (stats?.zoneDistribution ?? []).map((zone) => ({
      name: zone.zone,
      value: zone.highRiskCount > 0 ? zone.highRiskCount : zone.count,
    })).slice(0, 6)
  ), [stats]);

  const hasData = (stats?.totalRecords ?? 0) > 0;

  const handleExport = () => {
    const csvHeaders = 'Recorded At,Camera ID,Zone,Track ID,Risk Level,RULA Score,REBA Score,Description';
    const csvRows = records.map((record) => [
      record.recordedAt ?? '',
      record.cameraId,
      record.zone ?? '',
      record.trackId ?? '',
      record.riskLevel,
      record.rulaScore ?? '',
      record.rebaScore ?? '',
      (record.description ?? '').replaceAll('"', '""'),
    ].map((field) => `"${String(field)}"`).join(',')).join('\n');
    const csvContent = `${csvHeaders}\n${csvRows}`;
    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'ergonomics_report.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  };

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto bg-[#050505]">
      <div className="flex justify-between items-center">
        <div>
           <h2 className="text-2xl font-bold text-white">{t('ergonomics')}</h2>
           <p className="text-sm text-zinc-500">Postural analysis and skeletal risk factor monitoring.</p>
        </div>
        <button
          onClick={handleExport}
          disabled={loading || records.length === 0}
          className="px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-xs font-bold text-vs-orange uppercase tracking-wider hover:bg-zinc-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
           {t('exportCSV')}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MetricCard
          icon={<UserCheck size={24} />}
          value={`${(stats?.avgRulaScore ?? 0).toFixed(1)} / 7.0`}
          label={t('rulaScore')}
          hint={`${stats?.totalRecords ?? 0} ${t('records').toLowerCase()}`}
        />
        <MetricCard
          icon={<ShieldAlert size={24} />}
          value={`${(stats?.avgRebaScore ?? 0).toFixed(1)} / 15.0`}
          label={t('rebaScore')}
          hint="7d avg"
        />
        <MetricCard
          icon={<AlertCircle className="text-red-500" size={24} />}
          value={(stats?.highRiskCount ?? 0).toLocaleString()}
          label={t('badPostures')}
          hint={hasData ? t('high') : '0'}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#0f0f11] p-6 rounded-xl border border-zinc-800">
           <h3 className="font-bold text-white mb-6 uppercase text-xs tracking-widest">{t('ergoTrends')}</h3>
           {loading ? (
             <div className="h-[300px] animate-pulse rounded-lg bg-zinc-950/60" />
           ) : hasData ? (
             <div className="h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                   <AreaChart data={trendData}>
                      <defs>
                         <linearGradient id="ergoColor" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#FF6A00" stopOpacity={0.3}/>
                            <stop offset="95%" stopColor="#FF6A00" stopOpacity={0}/>
                         </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#262626"/>
                      <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#4b5563', fontSize: 10}} />
                      <YAxis axisLine={false} tickLine={false} tick={{fill: '#4b5563', fontSize: 10}} orientation={dir === 'rtl' ? 'right' : 'left'} />
                      <Tooltip
                        contentStyle={{backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px'}}
                        formatter={(value: number) => [value.toFixed(2), t('rulaScore')]}
                      />
                      <Area type="monotone" dataKey="score" stroke="#FF6A00" fillOpacity={1} fill="url(#ergoColor)" strokeWidth={3} />
                   </AreaChart>
                </ResponsiveContainer>
             </div>
           ) : (
             <EmptyState title={t('noErgonomicData')} description={t('runPostureAnalysis')} />
           )}
        </div>

        <div className="bg-[#0f0f11] p-6 rounded-xl border border-zinc-800">
           <h3 className="font-bold text-white mb-6 uppercase text-xs tracking-widest">{t('riskByZone')}</h3>
           {loading ? (
             <div className="h-[300px] animate-pulse rounded-lg bg-zinc-950/60" />
           ) : zoneRisk.length > 0 ? (
             <div className="h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                   <BarChart data={zoneRisk} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#262626"/>
                      <XAxis type="number" hide />
                      <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{fill: '#9CA3AF', fontSize: 10}} width={100} orientation={dir === 'rtl' ? 'right' : 'left'} />
                      <Tooltip contentStyle={{backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px'}} cursor={{fill: 'rgba(255,106,0,0.05)'}} />
                      <Bar dataKey="value" fill="#FF6A00" radius={[0, 4, 4, 0]} barSize={20}>
                         {zoneRisk.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={chartColorForValue(entry.value)} />
                         ))}
                      </Bar>
                   </BarChart>
                </ResponsiveContainer>
             </div>
           ) : (
             <EmptyState title={t('noErgonomicData')} description={t('runPostureAnalysis')} />
           )}
        </div>
      </div>
    </div>
  );
};

export default Ergonomics;
