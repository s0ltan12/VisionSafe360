import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Activity,
  AlertTriangle,
  Calendar,
  Camera,
  Clock3,
  Download,
  Flame,
  Gauge,
  ListFilter,
  RotateCcw,
  ShieldAlert,
  TimerReset,
  TrendingDown,
  TrendingUp,
  UserCheck,
} from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';
import { AlertsAPI, AnalyticsAPI, IncidentsAPI } from '../api';
import { RealtimeStatus, useRealtimeSocket } from '../hooks/useRealtimeSocket';
import {
  Alert,
  AnalyticsDistributionPoint,
  AnalyticsStats,
  AnalyticsTimeSeriesPoint,
  HazardType,
  Incident,
  IncidentStatus,
  Severity,
  Status,
} from '../types';
import { Badge, Button, FieldRoot, PageShell, Panel, SelectField } from './ui';

type FilterValue = 'all';
type ChartDatum = { name: string; value: number };

const TIME_WINDOWS = [7, 14, 30, 90];
const SEVERITIES: Severity[] = ['Critical', 'High', 'Medium', 'Low'];
const SEVERITY_COLORS: Record<Severity, string> = {
  Critical: '#ef4444',
  High: '#f97316',
  Medium: '#f59e0b',
  Low: '#10b981',
};
const HAZARD_COLORS = ['#FF6A00', '#f59e0b', '#3b82f6', '#10b981', '#a855f7', '#71717a'];

const ACTIVE_INCIDENT_STATUSES: IncidentStatus[] = ['New', 'Validating', 'Active', 'Acknowledged'];
const CLOSED_INCIDENT_STATUSES: IncidentStatus[] = ['Resolved', 'False Positive', 'Archived'];
const ACTIVE_ALERT_STATUSES: Status[] = ['New', 'Notified', 'Acknowledged', 'In Investigation', 'Active'];

const formatNumber = (value: number) => value.toLocaleString();

const formatPercent = (value: number) => `${Number(value || 0).toFixed(1)}%`;

const formatDateTime = (value?: string | null) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatRealtimeTime = (value?: string | null) => {
  if (!value) return 'Waiting for realtime events';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Updated recently';
  return `Last event ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
};

const formatDuration = (seconds?: number | null) => {
  const total = Math.max(0, Math.round(seconds ?? 0));
  if (!total) return '0m';
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
};

const formatTrend = (current: number, previous: number) => {
  if (previous === 0) return current > 0 ? 'New' : '0%';
  const change = ((current - previous) / previous) * 100;
  if (Math.abs(change) < 0.1) return '0%';
  if (Math.abs(change) > 999) return change > 0 ? '+999%+' : '-999%+';
  return `${change > 0 ? '+' : ''}${change.toFixed(1)}%`;
};

const parseDate = (value?: string | null) => {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const getIncidentTime = (incident: Incident) => (
  parseDate(incident.createdAt) ?? parseDate(incident.startedAt)
);

const getAlertTime = (alert: Alert) => parseDate(alert.timestamp);

const withinDays = (date: Date | null, days: number) => {
  if (!date) return false;
  const cutoff = new Date();
  cutoff.setHours(0, 0, 0, 0);
  cutoff.setDate(cutoff.getDate() - (days - 1));
  return date >= cutoff;
};

const csvEscape = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`;

const labelForDate = (dateValue: string, days: number) => {
  const parsed = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return dateValue;
  return parsed.toLocaleDateString('en-US', days > 14 ? { month: 'short', day: 'numeric' } : { weekday: 'short' });
};

const makeDateBuckets = (days: number) => {
  const now = new Date();
  return Array.from({ length: days }, (_, index) => {
    const day = new Date(now);
    day.setHours(0, 0, 0, 0);
    day.setDate(day.getDate() - (days - 1 - index));
    const date = day.toISOString().slice(0, 10);
    return { date, name: labelForDate(date, days), incidents: 0 };
  });
};

const groupCount = <T,>(items: T[], getKey: (item: T) => string | null | undefined): ChartDatum[] => {
  const counts = new Map<string, number>();
  items.forEach((item) => {
    const key = getKey(item) || 'Unassigned';
    counts.set(key, (counts.get(key) ?? 0) + 1);
  });
  return Array.from(counts.entries())
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value || a.name.localeCompare(b.name));
};

const uniqueSorted = (values: Array<string | null | undefined>) => (
  Array.from(new Set(values.filter((value): value is string => Boolean(value && value.trim())))).sort((a, b) => a.localeCompare(b))
);

const incidentMatchesHazard = (incident: Incident, hazard: string) => {
  const normalizedHazard = hazard.toLowerCase();
  return incident.classification.toLowerCase().includes(normalizedHazard);
};

const severityTone = (severity: Severity) => {
  if (severity === 'Critical' || severity === 'High') return 'danger';
  if (severity === 'Medium') return 'orange';
  return 'success';
};

const statusTone = (status: IncidentStatus | Status) => {
  if (status === 'Resolved') return 'success';
  if (status === 'False Positive' || status === 'Archived' || status === 'Dismissed') return 'neutral';
  if (status === 'Acknowledged' || status === 'Validating' || status === 'Notified') return 'warning';
  if (status === 'Active' || status === 'In Investigation' || status === 'New') return 'danger';
  return 'neutral';
};

const EmptyPanel = ({ label, description, compact = false }: { label: string; description?: string; compact?: boolean }) => (
  <div className={`flex w-full flex-col items-center justify-center rounded-lg border border-dashed border-zinc-800 bg-zinc-950/30 px-4 text-center ${compact ? 'min-h-[150px]' : 'h-[300px]'}`}>
    <p className="text-xs font-bold uppercase tracking-widest text-zinc-500">{label}</p>
    {description ? <p className="mt-2 max-w-sm text-xs leading-relaxed text-zinc-600">{description}</p> : null}
  </div>
);

const LoadingPanel = ({ compact = false }: { compact?: boolean }) => (
  <div className={`${compact ? 'h-[150px]' : 'h-[300px]'} animate-pulse rounded-lg bg-zinc-950/60`} />
);

const LiveStatusChip = ({ status, lastEventAt }: { status: RealtimeStatus; lastEventAt: string | null }) => {
  const className = status === 'live'
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
    <div className={`inline-flex min-h-[36px] items-center gap-2 rounded-lg border px-3 text-xs font-semibold ${className}`} title={formatRealtimeTime(lastEventAt)}>
      <span className={`h-2 w-2 rounded-full ${dotClass}`} />
      {status === 'live' ? 'Live updates' : status === 'reconnecting' ? 'Reconnecting' : 'Realtime offline'}
    </div>
  );
};

const KpiCard = ({
  label,
  value,
  hint,
  icon: Icon,
  tone = 'orange',
  trend,
}: {
  label: string;
  value: string;
  hint: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  tone?: 'orange' | 'red' | 'green' | 'blue' | 'zinc';
  trend?: string;
}) => {
  const toneClasses = {
    orange: 'bg-vs-orange/10 text-vs-orange border-vs-orange/20',
    red: 'bg-red-500/10 text-red-400 border-red-500/20',
    green: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    blue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    zinc: 'bg-zinc-900 text-zinc-300 border-zinc-800',
  };

  return (
    <Panel className="transition-colors hover:border-zinc-700">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className={`flex h-9 w-9 items-center justify-center rounded-md border ${toneClasses[tone]}`}>
          <Icon size={18} />
        </div>
        {trend ? (
          <span className={`inline-flex items-center gap-1 text-[10px] font-bold ${trend.startsWith('-') ? 'text-emerald-400' : trend === '0%' || trend === '0' ? 'text-zinc-500' : 'text-vs-orange'}`}>
            {trend.startsWith('-') ? <TrendingDown size={12} /> : <TrendingUp size={12} />}
            {trend}
          </span>
        ) : null}
      </div>
      <p className="text-2xl font-bold text-white">{value}</p>
      <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</p>
      <p className="mt-3 text-xs text-zinc-500">{hint}</p>
    </Panel>
  );
};

const FilterSelect = ({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) => (
  <FieldRoot label={label}>
    <SelectField value={value} onChange={(event) => onChange(event.target.value)} className="h-10 py-2 text-xs">
      <option value="all">All</option>
      {options.map((option) => (
        <option key={option} value={option}>{option}</option>
      ))}
    </SelectField>
  </FieldRoot>
);

const Reports = () => {
  const { t, dir } = useLanguage();
  const [stats, setStats] = useState<AnalyticsStats | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [serverTrend, setServerTrend] = useState<AnalyticsTimeSeriesPoint[]>([]);
  const [serverHazards, setServerHazards] = useState<AnalyticsDistributionPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [timeWindow, setTimeWindow] = useState(7);
  const [severityFilter, setSeverityFilter] = useState<FilterValue | Severity>('all');
  const [hazardFilter, setHazardFilter] = useState<FilterValue | HazardType>('all');
  const [zoneFilter, setZoneFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const refreshTimerRef = React.useRef<number | null>(null);

  const loadAnalytics = useCallback(async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true);
      const [statsData, alertsData, incidentsData] = await Promise.all([
        AnalyticsAPI.getStats(),
        AlertsAPI.getAll(),
        IncidentsAPI.getAll(),
      ]);
      const [trendResult, hazardsResult] = await Promise.allSettled([
        AnalyticsAPI.getIncidentTimeSeries(timeWindow),
        AnalyticsAPI.getAlertsByType(),
      ]);
      setStats(statsData);
      setAlerts(alertsData);
      setIncidents(incidentsData);
      setServerTrend(trendResult.status === 'fulfilled' ? trendResult.value : []);
      setServerHazards(hazardsResult.status === 'fulfilled' ? hazardsResult.value : []);
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'Failed to load analytics data');
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
      void loadAnalytics(false);
    }, 700);
  }, [loadAnalytics]);

  const realtime = useRealtimeSocket({
    path: '/ws/analytics',
    onEvent: (payload) => {
      if (payload?.type === 'analytics_changed') {
        scheduleRealtimeRefresh();
      }
    },
  });

  useEffect(() => {
    loadAnalytics();
    const timer = window.setInterval(() => loadAnalytics(false), 10000);
    return () => {
      window.clearInterval(timer);
      if (refreshTimerRef.current !== null) {
        window.clearTimeout(refreshTimerRef.current);
      }
    };
  }, [loadAnalytics]);

  const zoneOptions = useMemo(() => uniqueSorted([
    ...incidents.map((incident) => incident.zone),
    ...alerts.map((alert) => alert.zoneName || alert.areaName || alert.zone),
  ]), [alerts, incidents]);

  const hazardOptions = useMemo(() => uniqueSorted(alerts.map((alert) => alert.type)), [alerts]);

  const statusOptions = useMemo(() => uniqueSorted([
    ...incidents.map((incident) => incident.status),
    ...alerts.map((alert) => alert.status),
  ]), [alerts, incidents]);

  const filteredIncidents = useMemo(() => (
    incidents.filter((incident) => {
      const createdAt = getIncidentTime(incident);
      if (!withinDays(createdAt, timeWindow)) return false;
      if (severityFilter !== 'all' && incident.severity !== severityFilter) return false;
      if (zoneFilter !== 'all' && incident.zone !== zoneFilter) return false;
      if (statusFilter !== 'all' && incident.status !== statusFilter) return false;
      if (hazardFilter !== 'all' && !incidentMatchesHazard(incident, hazardFilter)) return false;
      return true;
    })
  ), [hazardFilter, incidents, severityFilter, statusFilter, timeWindow, zoneFilter]);

  const filteredAlerts = useMemo(() => (
    alerts.filter((alert) => {
      const createdAt = getAlertTime(alert);
      if (!withinDays(createdAt, timeWindow)) return false;
      if (severityFilter !== 'all' && alert.severity !== severityFilter) return false;
      if (zoneFilter !== 'all') {
        const alertZones = [alert.zone, alert.zoneName, alert.areaName].filter(Boolean);
        if (!alertZones.includes(zoneFilter)) return false;
      }
      if (statusFilter !== 'all' && alert.status !== statusFilter) return false;
      if (hazardFilter !== 'all' && alert.type !== hazardFilter) return false;
      return true;
    })
  ), [alerts, hazardFilter, severityFilter, statusFilter, timeWindow, zoneFilter]);

  const trendData = useMemo(() => {
    const buckets = makeDateBuckets(timeWindow);
    const byDate = new Map(buckets.map((bucket) => [bucket.date, bucket]));
    const filtersAreNeutral = severityFilter === 'all' && hazardFilter === 'all' && zoneFilter === 'all' && statusFilter === 'all';

    if (filtersAreNeutral && serverTrend.length > 0) {
      serverTrend.forEach((point) => {
        const bucket = byDate.get(point.date);
        if (bucket) bucket.incidents = point.count;
      });
      return buckets;
    }

    filteredIncidents.forEach((incident) => {
      const createdAt = getIncidentTime(incident);
      if (!createdAt) return;
      const date = createdAt.toISOString().slice(0, 10);
      const bucket = byDate.get(date);
      if (bucket) bucket.incidents += 1;
    });

    return buckets;
  }, [filteredIncidents, hazardFilter, serverTrend, severityFilter, statusFilter, timeWindow, zoneFilter]);

  const hazardData = useMemo(() => {
    if (filteredAlerts.length === alerts.length && serverHazards.length > 0 && severityFilter === 'all' && zoneFilter === 'all' && statusFilter === 'all' && hazardFilter === 'all') {
      return serverHazards.map((item) => ({ name: item.name, value: item.count }));
    }
    return groupCount(filteredAlerts, (alert) => alert.type);
  }, [alerts.length, filteredAlerts, hazardFilter, serverHazards, severityFilter, statusFilter, zoneFilter]);

  const severityData = useMemo(() => {
    const counts = new Map<Severity, number>();
    SEVERITIES.forEach((severity) => counts.set(severity, 0));
    filteredIncidents.forEach((incident) => counts.set(incident.severity, (counts.get(incident.severity) ?? 0) + 1));
    filteredAlerts.forEach((alert) => counts.set(alert.severity, (counts.get(alert.severity) ?? 0) + 1));
    return SEVERITIES.map((severity) => ({ name: severity, value: counts.get(severity) ?? 0 }));
  }, [filteredAlerts, filteredIncidents]);

  const zoneRiskData = useMemo(() => {
    const scores = new Map<string, { zone: string; incidents: number; alerts: number; riskScore: number }>();
    const weight: Record<Severity, number> = { Critical: 4, High: 3, Medium: 2, Low: 1 };
    const ensureZone = (zone: string) => {
      if (!scores.has(zone)) scores.set(zone, { zone, incidents: 0, alerts: 0, riskScore: 0 });
      return scores.get(zone)!;
    };

    filteredIncidents.forEach((incident) => {
      const entry = ensureZone(incident.zone || 'Unassigned');
      entry.incidents += 1;
      entry.riskScore += weight[incident.severity];
    });
    filteredAlerts.forEach((alert) => {
      const entry = ensureZone(alert.zoneName || alert.areaName || alert.zone || 'Unassigned');
      entry.alerts += 1;
      entry.riskScore += Math.max(1, weight[alert.severity] - 1);
    });

    return Array.from(scores.values())
      .sort((a, b) => b.riskScore - a.riskScore || b.incidents - a.incidents || b.alerts - a.alerts)
      .slice(0, 6);
  }, [filteredAlerts, filteredIncidents]);

  const recurringHazards = useMemo(() => {
    const statsHazards = stats?.recurringHazards ?? [];
    if (severityFilter === 'all' && hazardFilter === 'all' && zoneFilter === 'all' && statusFilter === 'all' && statsHazards.length > 0) {
      return statsHazards;
    }
    return groupCount(filteredIncidents, (incident) => `${incident.zone || 'Unassigned'}|${incident.classification || 'Hazard'}`)
      .filter((item) => item.value > 1)
      .slice(0, 5)
      .map((item) => {
        const [zone, classification] = item.name.split('|');
        return { zone, classification, count: item.value };
      });
  }, [filteredIncidents, hazardFilter, severityFilter, stats, statusFilter, zoneFilter]);

  const activeIncidents = filteredIncidents.filter((incident) => ACTIVE_INCIDENT_STATUSES.includes(incident.status)).length;
  const closedIncidents = filteredIncidents.filter((incident) => CLOSED_INCIDENT_STATUSES.includes(incident.status)).length;
  const activeAlerts = filteredAlerts.filter((alert) => ACTIVE_ALERT_STATUSES.includes(alert.status)).length;
  const slaBreaches = filteredIncidents.filter((incident) => incident.slaBreachedAt || (incident.slaBreachCount ?? 0) > 0).length;
  const filteredResolutionDurations = filteredIncidents
    .map((incident) => incident.durationSeconds)
    .filter((value): value is number => typeof value === 'number' && value > 0);
  const avgFilteredResolutionSeconds = filteredResolutionDurations.length > 0
    ? filteredResolutionDurations.reduce((sum, value) => sum + value, 0) / filteredResolutionDurations.length
    : 0;
  const cameraCoverage = stats?.totalCameras ? (stats.onlineCameras / stats.totalCameras) * 100 : 100;
  const hasAnyFilteredData = filteredIncidents.length > 0 || filteredAlerts.length > 0;
  const hasTrendData = trendData.some((point) => point.incidents > 0);
  const hasHazardData = hazardData.some((point) => point.value > 0);
  const hasSeverityData = severityData.some((point) => point.value > 0);

  const clearFilters = () => {
    setSeverityFilter('all');
    setHazardFilter('all');
    setZoneFilter('all');
    setStatusFilter('all');
  };

  const handleExport = () => {
    setIsExporting(true);
    const metadata = [
      ['Window Days', timeWindow],
      ['Severity Filter', severityFilter],
      ['Hazard Filter', hazardFilter],
      ['Zone Filter', zoneFilter],
      ['Status Filter', statusFilter],
    ].map((row) => row.map(csvEscape).join(',')).join('\n');
    const incidentHeaders = 'Record Type,ID,Time,Zone,Hazard,Severity,Status,Camera,Assigned/Worker,SLA,Duration,Description';
    const incidentRows = filteredIncidents.map((incident) => [
      'Incident',
      incident.id,
      incident.createdAt,
      incident.zone,
      incident.classification,
      incident.severity,
      incident.status,
      incident.cameraName || incident.cameraId || '',
      incident.acknowledgedBy || incident.workerId || '',
      incident.slaBreachedAt ? 'Breached' : 'Normal',
      formatDuration(incident.durationSeconds),
      incident.rootCause || incident.correctiveAction || '',
    ].map(csvEscape).join(','));
    const alertRows = filteredAlerts.map((alert) => [
      'Alert',
      alert.id,
      alert.timestamp,
      alert.zoneName || alert.areaName || alert.zone,
      alert.type,
      alert.severity,
      alert.status,
      alert.cameraName || alert.cameraId || alert.camera || '',
      alert.workerId || '',
      '',
      '',
      alert.description,
    ].map(csvEscape).join(','));
    const csvContent = `Analytics Filters\n${metadata}\n\n${incidentHeaders}\n${[...incidentRows, ...alertRows].join('\n')}`;
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

  const recentIncidents = [...filteredIncidents]
    .sort((a, b) => (getIncidentTime(b)?.getTime() ?? 0) - (getIncidentTime(a)?.getTime() ?? 0))
    .slice(0, 8);
  const recentAlerts = [...filteredAlerts]
    .sort((a, b) => (getAlertTime(b)?.getTime() ?? 0) - (getAlertTime(a)?.getTime() ?? 0))
    .slice(0, 8);

  return (
    <PageShell
      title={t('reports')}
      description="Safety trends, SLA pressure, hazard mix, and recent operational records."
      actions={
        <>
          <LiveStatusChip status={realtime.status} lastEventAt={realtime.lastEventAt} />
          <Button
            icon={<RotateCcw size={16} />}
            onClick={clearFilters}
            disabled={loading}
          >
            Reset filters
          </Button>
          <Button
            disabled={isExporting || loading || !hasAnyFilteredData}
            isLoading={isExporting}
            onClick={handleExport}
            variant="primary"
            icon={<Download size={16} />}
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

      <Panel className="p-4">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">
              <ListFilter size={14} className="text-vs-orange" />
              Analysis controls
            </div>
            <div className="flex flex-wrap gap-2">
              {TIME_WINDOWS.map((days) => (
                <button
                  key={days}
                  type="button"
                  onClick={() => setTimeWindow(days)}
                  className={`rounded-md border px-3 py-2 text-xs font-bold transition-colors ${timeWindow === days ? 'border-vs-orange bg-vs-orange/10 text-vs-orange' : 'border-zinc-800 bg-zinc-950 text-zinc-400 hover:border-zinc-700 hover:text-zinc-100'}`}
                >
                  <Calendar size={13} className="mr-1.5 inline" />
                  {days} days
                </button>
              ))}
            </div>
          </div>
          <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2 xl:w-auto xl:grid-cols-4">
            <FilterSelect label="Severity" value={severityFilter} onChange={(value) => setSeverityFilter(value as FilterValue | Severity)} options={SEVERITIES} />
            <FilterSelect label="Hazard" value={hazardFilter} onChange={(value) => setHazardFilter(value as FilterValue | HazardType)} options={hazardOptions} />
            <FilterSelect label="Zone" value={zoneFilter} onChange={setZoneFilter} options={zoneOptions} />
            <FilterSelect label="Status" value={statusFilter} onChange={setStatusFilter} options={statusOptions} />
          </div>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label={t('totalIncidents')}
          value={loading ? '...' : formatNumber(filteredIncidents.length)}
          hint={`${formatNumber(activeIncidents)} active, ${formatNumber(closedIncidents)} closed in view`}
          trend={stats ? formatTrend(stats.incidentsLast7Days, stats.incidentsPrevious7Days) : undefined}
          icon={ShieldAlert}
          tone={activeIncidents > 0 ? 'red' : 'zinc'}
        />
        <KpiCard
          label={t('activeAlerts')}
          value={loading ? '...' : formatNumber(activeAlerts)}
          hint={activeAlerts > 0 ? 'Requires operator review' : 'No active alerts in view'}
          icon={AlertTriangle}
          tone={activeAlerts > 0 ? 'red' : 'green'}
        />
        <KpiCard
          label={t('safetyScore')}
          value={loading ? '...' : `${(stats?.safetyScore ?? 0).toFixed(1)}%`}
          hint={(stats?.safetyScore ?? 0) >= 90 ? 'Current posture is stable' : 'Review active alerts and offline cameras'}
          icon={UserCheck}
          tone={(stats?.safetyScore ?? 0) >= 90 ? 'green' : 'orange'}
        />
        <KpiCard
          label="Camera coverage"
          value={loading ? '...' : formatPercent(cameraCoverage)}
          hint={`${formatNumber(stats?.onlineCameras ?? 0)} online of ${formatNumber(stats?.totalCameras ?? 0)} cameras`}
          icon={Camera}
          tone={cameraCoverage >= 90 ? 'green' : 'orange'}
        />
        <KpiCard
          label="SLA breach rate"
          value={loading ? '...' : formatPercent(stats?.slaBreachRate ?? 0)}
          hint={slaBreaches > 0 ? `${formatNumber(slaBreaches)} filtered incidents breached SLA` : 'No filtered SLA breaches'}
          icon={TimerReset}
          tone={(stats?.slaBreachRate ?? 0) > 0 ? 'red' : 'green'}
        />
        <KpiCard
          label="Avg response"
          value={loading ? '...' : formatDuration(stats?.avgResponseTimeSeconds ?? 0)}
          hint="Average acknowledgement response from backend SLA summary"
          icon={Gauge}
          tone="blue"
        />
        <KpiCard
          label="Avg resolution"
          value={loading ? '...' : formatDuration(avgFilteredResolutionSeconds || stats?.avgResolutionTimeSeconds || 0)}
          hint={avgFilteredResolutionSeconds > 0 ? 'Based on filtered resolved incidents' : 'Backend aggregate resolution time'}
          icon={Clock3}
          tone="blue"
        />
        <KpiCard
          label={t('fallsDetected')}
          value={loading ? '...' : formatNumber(filteredAlerts.filter((alert) => alert.type === 'Fall').length || stats?.fallsDetected || 0)}
          hint="Fall alerts from current data"
          icon={Activity}
          tone={(stats?.fallsDetected ?? 0) > 0 ? 'red' : 'zinc'}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Panel className="p-6 xl:col-span-2">
          <div className="mb-5 flex items-center justify-between gap-3">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Incident trend</h3>
            <span className="text-[11px] font-medium text-zinc-500">{timeWindow}-day window</span>
          </div>
          {loading ? (
            <LoadingPanel />
          ) : hasTrendData ? (
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trendData}>
                  <defs>
                    <linearGradient id="incidentTrendFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#FF6A00" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#FF6A00" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#262626" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#71717a', fontSize: 10 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#71717a', fontSize: 10 }} orientation={dir === 'rtl' ? 'right' : 'left'} allowDecimals={false} />
                  <Tooltip contentStyle={{ backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px' }} />
                  <Area type="monotone" dataKey="incidents" stroke="#FF6A00" fill="url(#incidentTrendFill)" strokeWidth={3} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyPanel label="No incidents in this period" description="Run the live AI pipeline or adjust filters to populate this trend." />
          )}
        </Panel>

        <Panel className="p-6">
          <div className="mb-5 flex items-center justify-between gap-3">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Severity mix</h3>
            <Flame size={16} className="text-zinc-500" />
          </div>
          {loading ? (
            <LoadingPanel />
          ) : hasSeverityData ? (
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={severityData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#262626" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#a1a1aa', fontSize: 10 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#71717a', fontSize: 10 }} allowDecimals={false} />
                  <Tooltip contentStyle={{ backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px' }} />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={28}>
                    {severityData.map((entry) => (
                      <Cell key={entry.name} fill={SEVERITY_COLORS[entry.name as Severity]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyPanel label="No severity data" description="No alerts or incidents match the current filters." />
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Panel className="p-6">
          <h3 className="mb-5 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Violation distribution</h3>
          {loading ? (
            <LoadingPanel />
          ) : hasHazardData ? (
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={hazardData} cx="50%" cy="45%" innerRadius={58} outerRadius={82} paddingAngle={6} dataKey="value">
                    {hazardData.map((entry, index) => (
                      <Cell key={entry.name} fill={HAZARD_COLORS[index % HAZARD_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px' }} />
                  <Legend verticalAlign="bottom" height={48} wrapperStyle={{ fontSize: '11px' }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyPanel label="No alerts by type yet" description="Hazard distribution will appear after real alerts are ingested." />
          )}
        </Panel>

        <Panel className="p-6 xl:col-span-2">
          <div className="mb-5 flex items-center justify-between gap-3">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Zone risk ranking</h3>
            <span className="text-[11px] font-medium text-zinc-500">Severity-weighted incidents and alerts</span>
          </div>
          {loading ? (
            <LoadingPanel />
          ) : zoneRiskData.length > 0 ? (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {zoneRiskData.map((zone) => (
                <div key={zone.zone} className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-bold text-zinc-100">{zone.zone}</p>
                      <p className="mt-1 text-xs text-zinc-500">{formatNumber(zone.incidents)} incidents, {formatNumber(zone.alerts)} alerts</p>
                    </div>
                    <Badge tone={zone.riskScore > 6 ? 'danger' : zone.riskScore > 2 ? 'orange' : 'neutral'}>{zone.riskScore} risk</Badge>
                  </div>
                  <div className="mt-4 h-2 overflow-hidden rounded-full bg-zinc-900">
                    <div className="h-full rounded-full bg-vs-orange" style={{ width: `${Math.min(100, Math.max(8, zone.riskScore * 10))}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyPanel label="No zone risk yet" description="No zones have matching alerts or incidents in this view." />
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Panel className="p-6">
          <h3 className="mb-5 text-[10px] font-bold uppercase tracking-widest text-zinc-400">SLA and weekly summary</h3>
          {loading ? (
            <LoadingPanel compact />
          ) : (
            <div className="space-y-3">
              <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-500">This week</span>
                  <Badge tone={(stats?.weeklySummary?.delta ?? 0) > 0 ? 'warning' : 'success'}>
                    {(stats?.weeklySummary?.delta ?? 0) > 0 ? '+' : ''}{stats?.weeklySummary?.delta ?? 0}
                  </Badge>
                </div>
                <p className="mt-2 text-2xl font-bold text-white">{formatNumber(stats?.weeklySummary?.incidents ?? 0)}</p>
                <p className="mt-1 text-xs text-zinc-500">{formatNumber(stats?.weeklySummary?.resolved ?? 0)} resolved this week</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
                  <p className="text-xs text-zinc-500">SLA breaches</p>
                  <p className={(stats?.slaBreachCount ?? 0) > 0 ? 'mt-2 text-xl font-bold text-red-400' : 'mt-2 text-xl font-bold text-zinc-100'}>{formatNumber(stats?.slaBreachCount ?? 0)}</p>
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
                  <p className="text-xs text-zinc-500">Resolution avg</p>
                  <p className="mt-2 text-xl font-bold text-zinc-100">{formatDuration(stats?.avgResolutionTimeSeconds ?? 0)}</p>
                </div>
              </div>
            </div>
          )}
        </Panel>

        <Panel className="p-6">
          <h3 className="mb-5 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Recurring hazards</h3>
          {loading ? (
            <LoadingPanel compact />
          ) : recurringHazards.length > 0 ? (
            <div className="space-y-3">
              {recurringHazards.map((hazard) => (
                <div key={`${hazard.zone}-${hazard.classification}`} className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-zinc-100">{hazard.classification}</p>
                      <p className="mt-1 truncate text-xs text-zinc-500">{hazard.zone || 'Unassigned'}</p>
                    </div>
                    <Badge tone="orange">{hazard.count}x</Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyPanel compact label="No recurring hazards" description="Repeated zone and hazard patterns will appear after more incidents accumulate." />
          )}
        </Panel>

        <Panel className="p-6">
          <h3 className="mb-5 text-[10px] font-bold uppercase tracking-widest text-zinc-400">Top dangerous zones</h3>
          {loading ? (
            <LoadingPanel compact />
          ) : (stats?.topDangerousZones?.length ?? 0) > 0 ? (
            <div className="space-y-3">
              {(stats?.topDangerousZones ?? []).map((zone) => (
                <div key={zone.zone} className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate text-sm font-semibold text-zinc-100">{zone.zone}</p>
                    <Badge tone={zone.riskScore > 6 ? 'danger' : 'orange'}>{zone.riskScore}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-zinc-500">{formatNumber(zone.incidentCount)} incidents</p>
                </div>
              ))}
            </div>
          ) : (
            <EmptyPanel compact label="No dangerous zones ranked" description="Risk-ranked zones need real incident history." />
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-6 2xl:grid-cols-2">
        <Panel padded={false}>
          <div className="border-b border-zinc-800 p-5">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Recent incidents</h3>
            <p className="mt-1 text-xs text-zinc-500">Newest matching incidents in the selected window.</p>
          </div>
          {loading ? (
            <div className="p-5"><LoadingPanel compact /></div>
          ) : recentIncidents.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-zinc-800 text-left text-sm">
                <thead className="bg-zinc-950/60 text-[10px] uppercase tracking-widest text-zinc-500">
                  <tr>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Time</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Zone</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Hazard</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Severity</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Status</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">SLA</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-900">
                  {recentIncidents.map((incident) => (
                    <tr key={incident.id} className="text-zinc-300 hover:bg-zinc-950/60">
                      <td className="whitespace-nowrap px-5 py-3 text-xs text-zinc-400">{formatDateTime(incident.createdAt)}</td>
                      <td className="max-w-[180px] truncate px-5 py-3 text-xs">{incident.zone || 'Unassigned'}</td>
                      <td className="max-w-[180px] truncate px-5 py-3 text-xs">{incident.classification || 'Hazard'}</td>
                      <td className="whitespace-nowrap px-5 py-3"><Badge tone={severityTone(incident.severity)}>{incident.severity}</Badge></td>
                      <td className="whitespace-nowrap px-5 py-3"><Badge tone={statusTone(incident.status)}>{incident.status}</Badge></td>
                      <td className="whitespace-nowrap px-5 py-3">
                        {incident.slaBreachedAt || (incident.slaBreachCount ?? 0) > 0 ? <Badge tone="danger">Breached</Badge> : <Badge tone="success">Normal</Badge>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyPanel compact label="No incidents match these filters" description="Change filters or ingest real incidents to populate this table." />
          )}
        </Panel>

        <Panel padded={false}>
          <div className="border-b border-zinc-800 p-5">
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Recent alerts</h3>
            <p className="mt-1 text-xs text-zinc-500">Newest matching AI alerts from the backend.</p>
          </div>
          {loading ? (
            <div className="p-5"><LoadingPanel compact /></div>
          ) : recentAlerts.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-zinc-800 text-left text-sm">
                <thead className="bg-zinc-950/60 text-[10px] uppercase tracking-widest text-zinc-500">
                  <tr>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Time</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Camera/source</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Type</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Zone</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Severity</th>
                    <th className="whitespace-nowrap px-5 py-3 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-900">
                  {recentAlerts.map((alert) => (
                    <tr key={alert.id} className="text-zinc-300 hover:bg-zinc-950/60">
                      <td className="whitespace-nowrap px-5 py-3 text-xs text-zinc-400">{formatDateTime(alert.timestamp)}</td>
                      <td className="max-w-[180px] truncate px-5 py-3 text-xs">{alert.cameraName || alert.cameraId || alert.camera || 'Unknown'}</td>
                      <td className="whitespace-nowrap px-5 py-3 text-xs">{alert.type}</td>
                      <td className="max-w-[180px] truncate px-5 py-3 text-xs">{alert.zoneName || alert.areaName || alert.zone || 'Unassigned'}</td>
                      <td className="whitespace-nowrap px-5 py-3"><Badge tone={severityTone(alert.severity)}>{alert.severity}</Badge></td>
                      <td className="whitespace-nowrap px-5 py-3"><Badge tone={statusTone(alert.status)}>{alert.status}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyPanel compact label="No alerts match these filters" description="AI alert records will appear here once the pipeline emits backend events." />
          )}
        </Panel>
      </div>
    </PageShell>
  );
};

export default Reports;
