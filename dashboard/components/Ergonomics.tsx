import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Activity,
  AlertCircle,
  BarChart3,
  Clock3,
  Database,
  Download,
  ShieldAlert,
  UserCheck,
} from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';
import { ErgonomicsAPI } from '../api';
import { ErgonomicRecord, ErgonomicRiskLevel, ErgonomicStats } from '../types';
import { RealtimeStatus, useRealtimeSocket } from '../hooks/useRealtimeSocket';

const RISK_LEVELS: ErgonomicRiskLevel[] = ['Low', 'Medium', 'High', 'Critical'];
const TIME_WINDOWS = [7, 14, 30];

const riskStyles: Record<ErgonomicRiskLevel, { text: string; bg: string; border: string; dot: string; chart: string }> = {
  Low: {
    text: 'text-emerald-300',
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/20',
    dot: 'bg-emerald-400',
    chart: '#34d399',
  },
  Medium: {
    text: 'text-amber-300',
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/20',
    dot: 'bg-amber-400',
    chart: '#f59e0b',
  },
  High: {
    text: 'text-orange-300',
    bg: 'bg-vs-orange/10',
    border: 'border-vs-orange/25',
    dot: 'bg-vs-orange',
    chart: '#FF6A00',
  },
  Critical: {
    text: 'text-red-300',
    bg: 'bg-red-500/10',
    border: 'border-red-500/25',
    dot: 'bg-red-500',
    chart: '#ef4444',
  },
};

const formatNumber = (value: number) => value.toLocaleString();

const formatScore = (value: number | null | undefined) => (
  value == null ? '0.0' : Number(value).toFixed(1)
);

const formatPercent = (value: number) => `${value.toFixed(1)}%`;

const weekdayLabel = (dateValue: string) => {
  const parsed = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return dateValue;
  return parsed.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

const timeLabel = (dateValue?: string | null) => {
  if (!dateValue) return 'Unrecorded';
  const parsed = new Date(dateValue);
  if (Number.isNaN(parsed.getTime())) return dateValue;
  return parsed.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const realtimeLabel = (dateValue?: string | null) => {
  if (!dateValue) return 'Waiting for realtime events';
  const parsed = new Date(dateValue);
  if (Number.isNaN(parsed.getTime())) return 'Updated recently';
  return `Last realtime event ${parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
};

const rulaInterpretation = (score: number) => {
  if (score >= 7) return 'Immediate action';
  if (score >= 5) return 'Investigate soon';
  if (score >= 3) return 'Review posture';
  if (score > 0) return 'Acceptable';
  return 'No score';
};

const rebaInterpretation = (score: number) => {
  if (score >= 11) return 'Very high risk';
  if (score >= 8) return 'High risk';
  if (score >= 4) return 'Medium risk';
  if (score > 0) return 'Low risk';
  return 'No score';
};

const riskLabel = (level: string) => {
  const normalized = level.toLowerCase();
  if (normalized === 'critical') return 'Critical';
  if (normalized === 'high') return 'High';
  if (normalized === 'medium') return 'Medium';
  if (normalized === 'low') return 'Low';
  return level || 'Unknown';
};

const EmptyState = ({ title, description, compact = false }: { title: string; description: string; compact?: boolean }) => (
  <div className={`flex w-full flex-col items-center justify-center gap-3 text-center ${compact ? 'min-h-[160px]' : 'h-[300px]'}`}>
    <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-950">
      <Database size={18} className="text-zinc-600" />
    </div>
    <p className="text-sm font-semibold text-zinc-300">{title}</p>
    <p className="max-w-sm text-xs leading-relaxed text-zinc-500">{description}</p>
  </div>
);

const MetricCard = ({
  icon,
  value,
  label,
  hint,
  tone = 'orange',
}: {
  icon: React.ReactNode;
  value: string;
  label: string;
  hint: string;
  tone?: 'orange' | 'red' | 'zinc';
}) => {
  const iconTone = tone === 'red' ? 'text-red-400 bg-red-500/10 border-red-500/20' : tone === 'zinc' ? 'text-zinc-300 bg-zinc-900 border-zinc-800' : 'text-vs-orange bg-vs-orange/10 border-vs-orange/20';

  return (
    <div className="rounded-lg border border-zinc-800 bg-[#0f0f11] p-4 transition-colors hover:border-zinc-700">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className={`flex h-9 w-9 items-center justify-center rounded-md border ${iconTone}`}>
          {icon}
        </div>
        <span className="text-right text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{hint}</span>
      </div>
      <p className="text-2xl font-bold text-zinc-50">{value}</p>
      <p className="mt-1 text-xs uppercase tracking-widest text-zinc-500">{label}</p>
    </div>
  );
};

const RiskBadge = ({ level }: { level: ErgonomicRiskLevel }) => {
  const style = riskStyles[level];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[11px] font-semibold ${style.bg} ${style.border} ${style.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {level}
    </span>
  );
};

const LiveStatusChip = ({ status, lastEventAt }: { status: RealtimeStatus; lastEventAt: string | null }) => {
  const statusClass = status === 'live'
    ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
    : status === 'reconnecting'
      ? 'border-amber-500/25 bg-amber-500/10 text-amber-300'
      : 'border-zinc-800 bg-zinc-950 text-zinc-500';
  const dotClass = status === 'live'
    ? 'bg-emerald-400'
    : status === 'reconnecting'
      ? 'bg-amber-400'
      : 'bg-zinc-600';

  return (
    <div className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold ${statusClass}`} title={realtimeLabel(lastEventAt)}>
      <span className={`h-2 w-2 rounded-full ${dotClass}`} />
      {status === 'live' ? 'Live updates' : status === 'reconnecting' ? 'Reconnecting' : 'Realtime offline'}
    </div>
  );
};

const TimeWindowControl = ({
  value,
  onChange,
}: {
  value: number;
  onChange: (days: number) => void;
}) => (
  <div className="flex flex-col gap-1">
    <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-600">Trend window</span>
    <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-950 p-1">
      {TIME_WINDOWS.map((days) => (
        <button
          key={days}
          type="button"
          onClick={() => onChange(days)}
          className={`rounded-md px-3 py-1.5 text-xs font-bold transition-colors ${value === days ? 'bg-vs-orange text-zinc-950' : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100'}`}
        >
          {days}d
        </button>
      ))}
    </div>
  </div>
);

const Ergonomics = () => {
  const { t, dir } = useLanguage();
  const [stats, setStats] = useState<ErgonomicStats | null>(null);
  const [records, setRecords] = useState<ErgonomicRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeWindow, setTimeWindow] = useState(7);
  const [riskFilter, setRiskFilter] = useState<'All' | ErgonomicRiskLevel>('All');
  const refreshTimerRef = React.useRef<number | null>(null);

  const loadErgonomics = useCallback(async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true);
      const [statsData, recordsData] = await Promise.all([
        ErgonomicsAPI.getStats(timeWindow),
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
  }, [timeWindow]);

  const scheduleRealtimeRefresh = useCallback(() => {
    if (refreshTimerRef.current !== null) {
      window.clearTimeout(refreshTimerRef.current);
    }
    refreshTimerRef.current = window.setTimeout(() => {
      refreshTimerRef.current = null;
      void loadErgonomics(false);
    }, 600);
  }, [loadErgonomics]);

  const realtime = useRealtimeSocket({
    path: '/ws/ergonomics',
    onEvent: (payload) => {
      if (payload?.type === 'ergonomic_record_created') {
        scheduleRealtimeRefresh();
      }
    },
  });

  useEffect(() => {
    loadErgonomics();
    const timer = window.setInterval(() => {
      loadErgonomics(false);
    }, 10000);
    return () => {
      window.clearInterval(timer);
      if (refreshTimerRef.current !== null) {
        window.clearTimeout(refreshTimerRef.current);
      }
    };
  }, [loadErgonomics]);

  const totalRecords = stats?.totalRecords ?? 0;
  const highRiskCount = stats?.highRiskCount ?? 0;
  const highRiskRate = totalRecords > 0 ? (highRiskCount / totalRecords) * 100 : 0;
  const hasData = totalRecords > 0;

  const trendData = useMemo(() => (
    (stats?.trend ?? []).map((point) => ({
      name: weekdayLabel(point.date),
      rula: point.avgRulaScore,
      reba: point.avgRebaScore,
      count: point.count,
    }))
  ), [stats]);

  const zoneRisk = useMemo(() => (
    (stats?.zoneDistribution ?? []).map((zone) => ({
      name: zone.zone,
      total: zone.count,
      highRisk: zone.highRiskCount,
      avgRula: zone.avgRulaScore,
    })).slice(0, 6)
  ), [stats]);

  const riskDistribution = useMemo(() => {
    const counts = new Map((stats?.riskDistribution ?? []).map((item) => [riskLabel(item.riskLevel), item.count]));
    return RISK_LEVELS.map((level) => ({
      riskLevel: level,
      count: counts.get(level) ?? 0,
      percent: totalRecords > 0 ? ((counts.get(level) ?? 0) / totalRecords) * 100 : 0,
    }));
  }, [stats, totalRecords]);

  const filteredRecords = useMemo(() => (
    riskFilter === 'All' ? records : records.filter((record) => record.riskLevel === riskFilter)
  ), [records, riskFilter]);

  const visibleRecords = filteredRecords.slice(0, 50);

  const handleExport = () => {
    const csvHeaders = 'Recorded At,Camera ID,Zone,Track ID,Risk Level,RULA Score,REBA Score,Description';
    const csvRows = filteredRecords.map((record) => [
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
    <div className="h-full overflow-y-auto bg-[#050505] p-6">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white">{t('ergonomics')}</h2>
            <p className="mt-1 text-sm text-zinc-500">Postural analysis from live edge ergonomics records.</p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <LiveStatusChip status={realtime.status} lastEventAt={realtime.lastEventAt} />
            <TimeWindowControl value={timeWindow} onChange={setTimeWindow} />
            <button
              onClick={handleExport}
              disabled={loading || filteredRecords.length === 0}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2 text-xs font-bold uppercase tracking-wider text-vs-orange transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Download size={14} />
              {t('exportCSV')}
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <MetricCard
            icon={<Database size={19} />}
            value={formatNumber(totalRecords)}
            label="Total ergonomic records"
            hint="All records"
            tone="zinc"
          />
          <MetricCard
            icon={<Activity size={19} />}
            value={formatPercent(highRiskRate)}
            label="High-risk posture rate"
            hint={`${formatNumber(highRiskCount)} high`}
            tone={highRiskCount > 0 ? 'red' : 'zinc'}
          />
          <MetricCard
            icon={<UserCheck size={19} />}
            value={`${formatScore(stats?.avgRulaScore)} / 7`}
            label={t('rulaScore')}
            hint={rulaInterpretation(stats?.avgRulaScore ?? 0)}
          />
          <MetricCard
            icon={<ShieldAlert size={19} />}
            value={`${formatScore(stats?.avgRebaScore)} / 15`}
            label={t('rebaScore')}
            hint={rebaInterpretation(stats?.avgRebaScore ?? 0)}
          />
          <MetricCard
            icon={<AlertCircle size={19} />}
            value={formatNumber(highRiskCount)}
            label={t('badPostures')}
            hint={hasData ? 'High + Critical' : 'No records'}
            tone={highRiskCount > 0 ? 'red' : 'zinc'}
          />
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <div className="rounded-lg border border-zinc-800 bg-[#0f0f11] p-5 xl:col-span-2">
            <div className="mb-5 flex items-center justify-between gap-3">
              <h3 className="text-xs font-bold uppercase tracking-widest text-white">{t('ergoTrends')}</h3>
              <span className="text-[11px] font-medium text-zinc-500">Average daily RULA and REBA</span>
            </div>
            {loading ? (
              <div className="h-[300px] animate-pulse rounded-lg bg-zinc-950/60" />
            ) : hasData ? (
              <div className="h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trendData}>
                    <defs>
                      <linearGradient id="rulaColor" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#FF6A00" stopOpacity={0.28} />
                        <stop offset="95%" stopColor="#FF6A00" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="rebaColor" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#262626" />
                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#71717a', fontSize: 10 }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: '#71717a', fontSize: 10 }} orientation={dir === 'rtl' ? 'right' : 'left'} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px' }}
                      labelStyle={{ color: '#e4e4e7' }}
                      formatter={(value: number, name: string) => [
                        Number(value).toFixed(2),
                        name === 'rula' ? t('rulaScore') : t('rebaScore'),
                      ]}
                    />
                    <Legend iconType="circle" wrapperStyle={{ color: '#a1a1aa', fontSize: 11 }} />
                    <Area type="monotone" dataKey="rula" name="RULA" stroke="#FF6A00" fill="url(#rulaColor)" strokeWidth={3} />
                    <Area type="monotone" dataKey="reba" name="REBA" stroke="#f59e0b" fill="url(#rebaColor)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState title={t('noErgonomicData')} description={t('runPostureAnalysis')} />
            )}
          </div>

          <div className="rounded-lg border border-zinc-800 bg-[#0f0f11] p-5">
            <div className="mb-5 flex items-center justify-between gap-3">
              <h3 className="text-xs font-bold uppercase tracking-widest text-white">Risk level mix</h3>
              <BarChart3 size={16} className="text-zinc-500" />
            </div>
            {loading ? (
              <div className="h-[300px] animate-pulse rounded-lg bg-zinc-950/60" />
            ) : hasData ? (
              <div className="space-y-4">
                {riskDistribution.map((item) => {
                  const style = riskStyles[item.riskLevel];
                  return (
                    <div key={item.riskLevel}>
                      <div className="mb-2 flex items-center justify-between text-xs">
                        <span className={`font-semibold ${style.text}`}>{item.riskLevel}</span>
                        <span className="font-mono text-zinc-400">{formatNumber(item.count)} ({formatPercent(item.percent)})</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-zinc-950">
                        <div className={style.dot} style={{ width: `${Math.max(item.percent, item.count > 0 ? 3 : 0)}%`, height: '100%' }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptyState title={t('noErgonomicData')} description={t('runPostureAnalysis')} compact />
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
          <div className="rounded-lg border border-zinc-800 bg-[#0f0f11] p-5 xl:col-span-2">
            <div className="mb-5 flex items-center justify-between gap-3">
              <h3 className="text-xs font-bold uppercase tracking-widest text-white">{t('riskByZone')}</h3>
              <span className="text-[11px] font-medium text-zinc-500">Total records compared with high-risk records</span>
            </div>
            {loading ? (
              <div className="h-[300px] animate-pulse rounded-lg bg-zinc-950/60" />
            ) : zoneRisk.length > 0 ? (
              <div className="h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={zoneRisk} layout="vertical" margin={{ left: 8, right: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#262626" />
                    <XAxis type="number" axisLine={false} tickLine={false} tick={{ fill: '#71717a', fontSize: 10 }} />
                    <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: '#a1a1aa', fontSize: 10 }} width={110} orientation={dir === 'rtl' ? 'right' : 'left'} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px' }}
                      cursor={{ fill: 'rgba(255,106,0,0.05)' }}
                      formatter={(value: number, name: string) => [formatNumber(value), name === 'highRisk' ? 'High risk records' : 'Total records']}
                    />
                    <Legend iconType="circle" wrapperStyle={{ color: '#a1a1aa', fontSize: 11 }} />
                    <Bar dataKey="total" name="Total records" fill="#3f3f46" radius={[0, 4, 4, 0]} barSize={18} />
                    <Bar dataKey="highRisk" name="High risk records" radius={[0, 4, 4, 0]} barSize={18}>
                      {zoneRisk.map((entry, index) => (
                        <Cell key={`zone-risk-${entry.name}-${index}`} fill={entry.highRisk > 0 ? '#FF6A00' : '#71717a'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyState title={t('noErgonomicData')} description={t('runPostureAnalysis')} />
            )}
          </div>

          <div className="rounded-lg border border-zinc-800 bg-[#0f0f11] p-5">
            <div className="mb-5 flex items-center justify-between gap-3">
              <h3 className="text-xs font-bold uppercase tracking-widest text-white">Zone watchlist</h3>
              <ShieldAlert size={16} className="text-zinc-500" />
            </div>
            {loading ? (
              <div className="h-[300px] animate-pulse rounded-lg bg-zinc-950/60" />
            ) : zoneRisk.length > 0 ? (
              <div className="space-y-3">
                {zoneRisk.map((zone) => (
                  <div key={zone.name} className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="truncate text-sm font-semibold text-zinc-100">{zone.name}</p>
                      <span className="font-mono text-xs text-zinc-400">{formatNumber(zone.total)}</span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <p className="text-zinc-500">High risk</p>
                        <p className={zone.highRisk > 0 ? 'font-semibold text-vs-orange' : 'font-semibold text-zinc-300'}>{formatNumber(zone.highRisk)}</p>
                      </div>
                      <div>
                        <p className="text-zinc-500">Avg RULA</p>
                        <p className="font-semibold text-zinc-300">{formatScore(zone.avgRula)}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title={t('noErgonomicData')} description={t('runPostureAnalysis')} compact />
            )}
          </div>
        </div>

        <div className="rounded-lg border border-zinc-800 bg-[#0f0f11]">
          <div className="flex flex-col gap-4 border-b border-zinc-800 p-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h3 className="text-xs font-bold uppercase tracking-widest text-white">Recent ergonomic records</h3>
              <p className="mt-1 text-xs text-zinc-500">
                Showing {formatNumber(visibleRecords.length)} of {formatNumber(filteredRecords.length)} loaded records.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {(['All', ...RISK_LEVELS] as Array<'All' | ErgonomicRiskLevel>).map((level) => (
                <button
                  key={level}
                  type="button"
                  onClick={() => setRiskFilter(level)}
                  className={`rounded-md border px-3 py-1.5 text-xs font-semibold transition-colors ${riskFilter === level ? 'border-vs-orange bg-vs-orange/10 text-vs-orange' : 'border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100'}`}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          {loading ? (
            <div className="p-5">
              <div className="h-[260px] animate-pulse rounded-lg bg-zinc-950/60" />
            </div>
          ) : records.length === 0 ? (
            <EmptyState title={t('noErgonomicData')} description={t('runPostureAnalysis')} compact />
          ) : filteredRecords.length === 0 ? (
            <EmptyState title="No records match this filter" description="Choose another risk level to view the loaded ergonomic records." compact />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-zinc-800 text-left text-sm">
                <thead className="bg-zinc-950/60 text-[11px] uppercase tracking-widest text-zinc-500">
                  <tr>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Time</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Camera/source</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Zone</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Track ID</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Risk level</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">RULA</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">REBA</th>
                    <th className="min-w-[280px] px-5 py-3 font-semibold">Description</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-900">
                  {visibleRecords.map((record) => (
                    <tr key={record.id} className="text-zinc-300 transition-colors hover:bg-zinc-950/70">
                      <td className="whitespace-nowrap px-5 py-3 text-xs text-zinc-400">
                        <Clock3 size={12} className="mr-1.5 inline text-zinc-600" />
                        {timeLabel(record.recordedAt)}
                      </td>
                      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-zinc-300">{record.cameraId || 'Unknown'}</td>
                      <td className="whitespace-nowrap px-5 py-3 text-xs text-zinc-300">{record.zone || 'Unassigned'}</td>
                      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-zinc-400">{record.trackId ?? '-'}</td>
                      <td className="whitespace-nowrap px-5 py-3"><RiskBadge level={record.riskLevel} /></td>
                      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-zinc-100">{formatScore(record.rulaScore)}</td>
                      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-zinc-100">{formatScore(record.rebaScore)}</td>
                      <td className="px-5 py-3 text-xs leading-5 text-zinc-400">{record.description || 'No description provided.'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Ergonomics;
