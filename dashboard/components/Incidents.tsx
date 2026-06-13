
import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { 
  Plus, 
  Search, 
  FileText, 
  AlertTriangle, 
  Bell,
	  Clock,
	  CheckCircle,
	  Download,
	  X,
	  Archive,
	  RotateCcw,
	  ShieldCheck,
	  CircleDot,
	  CheckCircle2
		} from 'lucide-react';
import { Incident, IncidentEvent, IncidentStatus, Severity, UserRole } from '../types';
import { useLanguage } from '../contexts/LanguageContext';
import { AlertsAPI, IncidentsAPI } from '../api';
import { Badge, Button, FieldRoot, PageShell, Panel, SelectField, TextAreaField, TextInput } from './ui';



const SeverityBadge = ({ severity }: { severity: Severity }) => {
  const tones = {
    Critical: 'danger',
    High: 'danger',
    Medium: 'orange',
    Low: 'warning',
  } as const;
  const { t } = useLanguage();
  return (
    <Badge tone={tones[severity]}>
      {t(severity.toLowerCase() as any)}
    </Badge>
  );
};

const StatusBadge = ({ status }: { status: IncidentStatus }) => {
  const { t } = useLanguage();
  const tones = {
    New: 'info',
    Validating: 'warning',
    Active: 'danger',
    Acknowledged: 'orange',
    Resolved: 'success',
    'False Positive': 'neutral',
    Archived: 'neutral',
  } as const;
  const key = status.toLowerCase().replace(/ /g, '') as any;
  return <Badge tone={tones[status]}>{t(key)}</Badge>;
};

const SLABadge = ({ incident }: { incident: Incident }) => {
  if (!incident.slaBreachedAt) return null;
  return <Badge tone="danger">SLA BREACHED</Badge>;
};

const formatDateTime = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

const formatTimelineAction = (event: IncidentEvent) => {
  const labels: Record<string, string> = {
    created: 'Created',
    validated: 'Validated',
    composite_created: 'Composite Created',
    source_hazard_attached: 'Source Hazard Attached',
    source_incidents_merged: 'Source Incidents Merged',
    active: 'Activated',
    acknowledged: 'Acknowledged',
    escalated: 'Escalated',
    resolved: 'Resolved',
    reopened: 'Reopened',
    archived: 'Archived',
    false_positive: 'False Positive',
    sla_breached: 'SLA Breached',
  };
  return labels[event.action] || event.action.replace(/_/g, ' ');
};

type ComponentHazard = {
  label?: string;
  category?: string;
  event_type?: string;
  severity?: string;
  frame_number?: number;
  timestamp?: number;
};

const titleFromEventType = (value?: string) => {
  if (!value) return 'Hazard';
  return value
    .replace(/^forklift_proximity_/i, 'Forklift Proximity ')
    .replace(/^ppe_missing_/i, 'Missing ')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase());
};

const componentLabel = (component: ComponentHazard) =>
  String(component.label || titleFromEventType(component.event_type));

const componentKey = (component: ComponentHazard) =>
  [
    component.event_type || component.label || 'hazard',
    component.frame_number ?? 'frame',
    component.timestamp ?? 'time',
  ].join(':');

const collectComponentHazards = (events: IncidentEvent[]): ComponentHazard[] => {
  const byKey = new Map<string, ComponentHazard>();
  for (const event of events) {
    const metadata = event.metadata || {};
    const multi = metadata.component_hazards;
    if (Array.isArray(multi)) {
      for (const item of multi) {
        if (item && typeof item === 'object') {
          const component = item as ComponentHazard;
          byKey.set(componentKey(component), component);
        }
      }
    }
    const single = metadata.component_hazard;
    if (single && typeof single === 'object') {
      const component = single as ComponentHazard;
      byKey.set(componentKey(component), component);
    }
  }
  return Array.from(byKey.values());
};

const compositeTitle = (incident: Incident) => {
  const value = incident.classification || '';
  if (/ppe/i.test(value) && /forklift/i.test(value)) return 'PPE + Forklift Risk';
  return value.replace(/^Composite\s+/i, '') || 'Composite Hazard';
};

const formatDuration = (seconds?: number | null) => {
  if (!seconds || seconds < 0) return '0m';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
};

const incidentDuration = (incident: Incident) => {
  if (incident.durationSeconds !== null && incident.durationSeconds !== undefined) {
    return incident.durationSeconds;
  }
  const started = incident.startedAt || incident.createdAt;
  if (!started) return 0;
  const startMs = new Date(started).getTime();
  if (Number.isNaN(startMs)) return 0;
  const endMs = incident.resolvedAt ? new Date(incident.resolvedAt).getTime() : Date.now();
  return Math.max(0, Math.floor((endMs - startMs) / 1000));
};

const StatCard = ({ label, value, icon: Icon, colorClass }: { label: string, value: string, icon: any, colorClass: string }) => (
    <Panel className="p-4 flex items-center space-x-4 rtl:space-x-reverse">
        <div className={`p-2 rounded bg-zinc-900 border border-zinc-800 ${colorClass}`}>
            <Icon size={20} />
        </div>
        <div>
            <p className="text-zinc-500 text-xs font-medium uppercase tracking-wider">{label}</p>
            <p className="text-xl font-bold text-white">{value}</p>
        </div>
    </Panel>
);

const IncidentTimelineDrawer = ({
  incident,
  events,
  loading,
  error,
  canOperate,
  isAdmin,
  onAcknowledge,
  onResolve,
  onEscalate,
  onArchive,
  onReopen,
  onOpenAlert,
  onClose,
}: {
  incident: Incident;
  events: IncidentEvent[];
  loading: boolean;
  error: string | null;
  canOperate: boolean;
  isAdmin: boolean;
  onAcknowledge: (id: string) => void;
  onResolve: (id: string) => void;
  onEscalate: (id: string) => void;
  onArchive: (id: string) => void;
  onReopen: (id: string) => void;
  onOpenAlert?: (alertId: string) => void;
  onClose: () => void;
}) => {
  const isHistory = ['Resolved', 'False Positive', 'Archived'].includes(incident.status);
  const canAcknowledge = canOperate && ['New', 'Validating', 'Active'].includes(incident.status);
  const canResolve = canOperate && !isHistory;
  const canEscalate = canOperate && !isHistory;
  const componentHazards = collectComponentHazards(events);
  const showComposite = componentHazards.length > 0 || /^Composite/i.test(incident.classification || '');

  return (
	  <div className="fixed inset-0 z-50 flex justify-end bg-black/70 backdrop-blur-sm">
	    <div className="h-full w-full max-w-xl border-s border-zinc-800 bg-[#0f0f11] shadow-2xl">
      <div className="flex items-center justify-between border-b border-zinc-800 p-5">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold uppercase tracking-widest text-white">{incident.id}</h3>
            <SeverityBadge severity={incident.severity} />
            <StatusBadge status={incident.status} />
            <SLABadge incident={incident} />
          </div>
          <p className="mt-1 text-xs text-zinc-500">{incident.classification} • {incident.zone}</p>
        </div>
        <button onClick={onClose} className="rounded p-2 text-zinc-500 hover:bg-zinc-800 hover:text-white">
          <X size={18} />
        </button>
      </div>
      <div className="space-y-5 p-5">
        {incident.slaBreachedAt && (
	          <div className="rounded border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">
	            SLA breached at {formatDateTime(incident.slaBreachedAt)}
	          </div>
	        )}
        {events.some(event => event.metadata?.alert_id) && (
          <div className="rounded border border-zinc-800 bg-zinc-950 p-3">
            <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Related Alert Signal</div>
            {events
              .filter(event => event.metadata?.alert_id)
              .slice(0, 1)
              .map(event => (
                <button
                  key={event.id}
                  type="button"
                  onClick={() => onOpenAlert?.(String(event.metadata?.alert_id))}
                  className="mt-2 inline-flex items-center gap-2 rounded border border-vs-orange/40 bg-vs-orange/10 px-3 py-2 text-xs font-bold uppercase tracking-wide text-vs-orange transition-colors hover:bg-vs-orange hover:text-black"
                >
                  <Bell size={14} />
                  <span>Open Alert</span>
                  <span className="font-mono">{String(event.metadata?.alert_id)}</span>
                </button>
              ))}
          </div>
        )}
        {showComposite && (
          <div className="rounded border border-red-500/30 bg-red-500/10 p-4">
            <div className="text-[10px] font-bold uppercase tracking-widest text-red-200/80">Composite Hazard</div>
            <div className="mt-2 text-sm font-semibold text-white">{compositeTitle(incident)}</div>
            {componentHazards.length > 0 && (
              <div className="mt-4 space-y-2">
                <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Contributing Hazards</div>
                {componentHazards.map(component => (
                  <div
                    key={componentKey(component)}
                    className="rounded border border-zinc-800 bg-zinc-950 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs font-semibold text-zinc-100">{componentLabel(component)}</span>
                      {component.severity && <Badge tone="danger">{String(component.severity)}</Badge>}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-2 text-[10px] font-mono uppercase text-zinc-500">
                      {component.category && <span>{String(component.category)}</span>}
                      {component.frame_number !== undefined && <span>Frame {String(component.frame_number)}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {(canAcknowledge || canResolve || canEscalate || isAdmin) && (
          <div className="flex flex-wrap gap-2 rounded border border-zinc-800 bg-zinc-950 p-3">
            {canAcknowledge && (
              <Button size="sm" icon={<ShieldCheck size={14} />} onClick={() => onAcknowledge(incident.id)}>
                Acknowledge
              </Button>
            )}
            {canEscalate && (
              <Button size="sm" icon={<AlertTriangle size={14} />} onClick={() => onEscalate(incident.id)}>
                Escalate
              </Button>
            )}
            {canResolve && (
              <Button size="sm" icon={<CheckCircle size={14} />} onClick={() => onResolve(incident.id)}>
                Resolve
              </Button>
            )}
            {isAdmin && !isHistory && (
              <Button size="sm" variant="ghost" icon={<Archive size={14} />} onClick={() => onArchive(incident.id)}>
                Archive
              </Button>
            )}
            {isAdmin && isHistory && (
              <Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} onClick={() => onReopen(incident.id)}>
                Reopen
              </Button>
            )}
          </div>
        )}
	        {loading ? (
	          <div className="text-sm text-zinc-500">Loading timeline...</div>
        ) : error ? (
          <div className="rounded border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">{error}</div>
        ) : events.length === 0 ? (
          <div className="text-sm text-zinc-500">No timeline entries recorded.</div>
        ) : (
          <div className="space-y-5">
            {events.map((event, index) => (
              <div key={event.id} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div className={`rounded-full border p-1 ${event.action === 'sla_breached' ? 'border-red-500/50 bg-red-500/10 text-red-400' : 'border-vs-orange/40 bg-vs-orange/10 text-vs-orange'}`}>
                    <CircleDot size={12} />
                  </div>
                  {index < events.length - 1 && <div className="mt-1 min-h-10 w-px flex-1 bg-zinc-800" />}
                </div>
                <div className="min-w-0 pb-2">
                  <div className="text-sm font-semibold text-zinc-100">{formatTimelineAction(event)}</div>
                  <div className="mt-1 text-[11px] font-mono text-zinc-500">{formatDateTime(event.createdAt)}</div>
                  <div className="mt-1 text-xs text-zinc-400">
                    {event.actorName || 'System'}
                    {event.newStatus ? <span className="text-zinc-600">{` -> ${event.newStatus}`}</span> : null}
                  </div>
                  {event.note && <div className="mt-1 text-xs text-zinc-500">{event.note}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
	    </div>
	  </div>
  );
};

const Incidents = ({
  currentUserRole,
  targetIncidentId,
  onTargetIncidentOpened,
  onOpenAlert,
}: {
  currentUserRole?: UserRole | null;
  targetIncidentId?: string | null;
  onTargetIncidentOpened?: () => void;
  onOpenAlert?: (alertId: string) => void;
}) => {
  const { t } = useLanguage();
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [timelineByIncidentId, setTimelineByIncidentId] = useState<Record<string, IncidentEvent[]>>({});
  const [alertIdByIncidentId, setAlertIdByIncidentId] = useState<Record<string, string>>({});
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [zoneFilter, setZoneFilter] = useState('all');
  const [incidentView, setIncidentView] = useState<'active' | 'history'>('active');
  const isAdmin = currentUserRole === 'Admin';
  const canOperate = currentUserRole === 'Safety Engineer' || isAdmin;

  const fetchIncidents = useCallback(async () => {
    try {
      setLoading(true);
      const data = await IncidentsAPI.getAll({}, incidentView);
      setIncidents(data);
    } catch (error) {
      console.error('Failed to fetch incidents:', error);
    } finally {
      setLoading(false);
    }
  }, [incidentView]);

  useEffect(() => {
    fetchIncidents();
  }, [fetchIncidents]);

  useEffect(() => {
    if (!targetIncidentId) return;
    let cancelled = false;
    (async () => {
      try {
        const incident = await IncidentsAPI.getById(targetIncidentId);
        if (cancelled) return;
        setIncidentView(['Resolved', 'False Positive', 'Archived'].includes(incident.status) ? 'history' : 'active');
        setIncidents(prev => {
          const exists = prev.some(item => item.id === incident.id);
          return exists
            ? prev.map(item => item.id === incident.id ? incident : item)
            : [incident, ...prev];
        });
        setSelectedIncident(incident);
        onTargetIncidentOpened?.();
      } catch (error) {
        console.error(`Failed to open incident ${targetIncidentId}:`, error);
      }
    })();
    return () => { cancelled = true; };
  }, [targetIncidentId, onTargetIncidentOpened]);

  const replaceIncident = (updated: Incident) => {
    setIncidents(prev => prev.map(item => item.id === updated.id ? updated : item));
  };

  useEffect(() => {
    if (!selectedIncident) return;
    let cancelled = false;
    const loadTimeline = async () => {
      setTimelineError(null);
      setTimelineLoading(true);
      try {
        const events = await IncidentsAPI.getEvents(selectedIncident.id);
        if (!cancelled) {
          setTimelineByIncidentId(prev => ({ ...prev, [selectedIncident.id]: events }));
        }
      } catch (error) {
        console.error('Failed to load incident timeline:', error);
        if (!cancelled) setTimelineError('Failed to load incident timeline.');
      } finally {
        if (!cancelled) setTimelineLoading(false);
      }
    };
    void loadTimeline();
    return () => {
      cancelled = true;
    };
  }, [selectedIncident?.id]);

  const openRelatedAlert = async (incident: Incident) => {
    try {
      const timelineAlertId = timelineByIncidentId[incident.id]?.find(event => event.metadata?.alert_id)?.metadata?.alert_id;
      if (timelineAlertId) {
        onOpenAlert?.(String(timelineAlertId));
        return;
      }
      if (alertIdByIncidentId[incident.id]) {
        onOpenAlert?.(alertIdByIncidentId[incident.id]);
        return;
      }
      const alerts = await AlertsAPI.getAll();
      const linked = alerts.find(alert => alert.incidentId === incident.id);
      if (linked) {
        setAlertIdByIncidentId(prev => ({ ...prev, [incident.id]: linked.id }));
        onOpenAlert?.(linked.id);
        return;
      }
      console.warn(`No linked alert found for incident ${incident.id}`);
    } catch (error) {
      console.error(`Failed to load related alert for incident ${incident.id}:`, error);
    }
  };

  // Form state
  const [formCategory, setFormCategory] = useState('Near Miss');
  const [formSeverity, setFormSeverity] = useState<Severity>('High');
  const [formZone, setFormZone] = useState('Zone A - Welding');
  const [formDescription, setFormDescription] = useState('');
  const [formRootCause, setFormRootCause] = useState('');
  const [formCorrectiveAction, setFormCorrectiveAction] = useState('');

  const filteredIncidents = useMemo(() => {
    return incidents.filter(inc => {
      const matchesSearch = searchQuery === '' ||
        inc.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        inc.zone.toLowerCase().includes(searchQuery.toLowerCase()) ||
        inc.classification.toLowerCase().includes(searchQuery.toLowerCase()) ||
        inc.rootCause.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesZone = zoneFilter === 'all' || inc.zone.includes(zoneFilter);

      return matchesSearch && matchesZone;
    });
  }, [incidents, searchQuery, zoneFilter]);

  const uniqueZones = [...new Set(incidents.map(i => i.zone.split(' - ')[0]))];

  const activeCount = incidents.filter(i => ['New', 'Validating', 'Active', 'Acknowledged'].includes(i.status)).length;
  const resolvedCount = incidents.filter(i => ['Resolved', 'False Positive', 'Archived'].includes(i.status)).length;
  const avgResolutionSeconds = incidents
    .map(i => i.durationSeconds)
    .filter((value): value is number => typeof value === 'number' && value > 0);
  const avgResolution = avgResolutionSeconds.length
    ? formatDuration(Math.round(avgResolutionSeconds.reduce((sum, value) => sum + value, 0) / avgResolutionSeconds.length))
    : '0m';

  const handleExport = () => {
    const headers = 'ID,Date,Zone,Severity,Status,Duration,Category,Root Cause,Corrective Action';
    const rows = filteredIncidents.map(i => `"${i.id}","${i.createdAt}","${i.zone}","${i.severity}","${i.status}","${formatDuration(incidentDuration(i))}","${i.classification}","${i.rootCause}","${i.correctiveAction}"`).join('\n');
    const csvContent = `${headers}\n${rows}`;
    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'incidents_export.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  };

  const handleAddIncident = async () => {
    if (!formDescription.trim()) return;
    const newIncident: Incident = {
      id: `INC-${new Date().getFullYear()}-${String(incidents.length + 1).padStart(3, '0')}`,
      zone: formZone,
      classification: formCategory,
      severity: formSeverity,
      status: 'New',
      rootCause: formRootCause || 'Under Investigation',
      correctiveAction: formCorrectiveAction || 'Pending Review',
      createdAt: new Date().toISOString().split('T')[0],
    };
    
    try {
      const created = await IncidentsAPI.create(newIncident);
      setIncidents(prev => [created, ...prev]);
      setShowAddModal(false);
      // Reset form
      setFormCategory('Near Miss');
      setFormSeverity('High');
      setFormZone('Zone A - Welding');
      setFormDescription('');
      setFormRootCause('');
      setFormCorrectiveAction('');
    } catch (e) {
      console.error('Failed to create incident: ', e);
    }
  };

	  const handleAcknowledge = async (id: string) => {
	    try {
	      const updated = await IncidentsAPI.acknowledge(id);
      if (selectedIncident?.id === id) setSelectedIncident(updated);
	      await fetchIncidents();
	    } catch (e) {
	      console.error('Failed to acknowledge incident:', e);
    }
  };

		  const handleResolve = async (id: string) => {
		    try {
		      const updated = await IncidentsAPI.resolve(id);
      if (selectedIncident?.id === id) setSelectedIncident(updated);
		      await fetchIncidents();
	    } catch (e) {
	      console.error('Failed to resolve incident:', e);
    }
	  };

  const handleArchive = async (id: string) => {
    try {
      const updated = await IncidentsAPI.archive(id);
      if (selectedIncident?.id === id) setSelectedIncident(updated);
      await fetchIncidents();
    } catch (e) {
      console.error('Failed to archive incident:', e);
    }
  };

		  const handleEscalate = async (id: string) => {
		    try {
		      const updated = await IncidentsAPI.escalate(id);
      replaceIncident(updated);
      if (selectedIncident?.id === id) setSelectedIncident(updated);
	    } catch (e) {
	      console.error('Failed to escalate incident:', e);
	    }
  };

	  const handleReopen = async (id: string) => {
	    try {
	      const updated = await IncidentsAPI.reopen(id);
      if (selectedIncident?.id === id) setSelectedIncident(updated);
	      await fetchIncidents();
	    } catch (e) {
      console.error('Failed to reopen incident:', e);
    }
  };

  return (
    <PageShell
      title={t('incidents')}
      description="Review and manage reported workplace incidents."
      actions={
        <>
          <Button onClick={handleExport} icon={<Download size={16} />}>{t('exportCSV')}</Button>
          {canOperate && (
            <Button onClick={() => setShowAddModal(true)} variant="primary" icon={<Plus size={16} />}>{t('reportIncident')}</Button>
          )}
        </>
      }
    >
      {selectedIncident && (
        <IncidentTimelineDrawer
          incident={selectedIncident}
	          events={timelineByIncidentId[selectedIncident.id] || []}
	          loading={timelineLoading}
	          error={timelineError}
          canOperate={canOperate}
          isAdmin={isAdmin}
          onAcknowledge={handleAcknowledge}
          onResolve={handleResolve}
          onEscalate={handleEscalate}
          onArchive={handleArchive}
          onReopen={handleReopen}
          onOpenAlert={(alertId) => onOpenAlert?.(alertId)}
	          onClose={() => setSelectedIncident(null)}
	        />
      )}

      <div className="inline-flex w-fit rounded-lg border border-zinc-800 bg-zinc-950 p-1">
        {(['active', 'history'] as const).map((view) => (
          <button
            key={view}
            type="button"
            onClick={() => setIncidentView(view)}
            className={`rounded-md px-4 py-2 text-xs font-bold uppercase tracking-wide transition-colors ${
              incidentView === view ? 'bg-vs-orange text-black' : 'text-zinc-500 hover:text-zinc-200'
            }`}
          >
            {view === 'active' ? t('activeIncidents') : t('incidents')}
          </button>
        ))}
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard label={t('activeCases')} value={String(activeCount)} icon={AlertTriangle} colorClass="text-red-500" />
        <StatCard label={t('avgResolution')} value={avgResolution} icon={Clock} colorClass="text-vs-orange" />
        <StatCard label={t('totalReports')} value={String(incidents.length)} icon={FileText} colorClass="text-blue-500" />
        <StatCard label={t('resolved')} value={String(resolvedCount)} icon={CheckCircle} colorClass="text-emerald-500" />
      </div>

      {/* Filter Bar */}
      <Panel className="p-4 flex flex-col lg:flex-row gap-4 items-center">
         <div className="relative flex-1 w-full lg:w-auto">
           <Search className="absolute start-3 top-1/2 -translate-y-1/2 text-zinc-600" size={16} />
           <input 
            type="text" 
            placeholder={t('searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-9 py-2 bg-[#050505] border border-zinc-800 rounded text-sm text-white focus:outline-none focus:border-vs-orange/50 transition-colors placeholder-zinc-600"
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')} className="absolute end-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white">
              <X size={14} />
            </button>
          )}
         </div>
         <div className="flex gap-2 w-full lg:w-auto overflow-x-auto pb-2 lg:pb-0">
            <SelectField
              value={zoneFilter}
              onChange={(e) => setZoneFilter(e.target.value)}
              className="py-2"
            >
               <option value="all">{t('allZones')}</option>
               {uniqueZones.map(zone => (
                 <option key={zone} value={zone}>{zone}</option>
               ))}
            </SelectField>
         </div>
      </Panel>

      {/* Incidents Table */}
      <Panel padded={false} className="rounded-lg shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-start text-sm text-zinc-400">
            <thead className="bg-zinc-900/50 text-zinc-500 uppercase text-[10px] font-bold tracking-wider border-b border-zinc-800">
              <tr>
                <th className="px-6 py-4 text-start">{t('id')}</th>
                <th className="px-6 py-4 text-start">{t('date')}</th>
                <th className="px-6 py-4 text-start">{t('location')}</th>
                <th className="px-6 py-4 text-start">{t('severity')}</th>
                <th className="px-6 py-4 text-start">{t('status')}</th>
                <th className="px-6 py-4 text-start">{t('duration')}</th>
                <th className="px-6 py-4 text-start">{t('category')}</th>
                <th className="px-6 py-4 text-end">{t('action')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {filteredIncidents.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-12 text-center text-zinc-500">
                    <div className="flex flex-col items-center space-y-2">
                      <Search size={32} className="text-zinc-700" />
                      <p className="text-sm">{t('noResults')}</p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredIncidents.map((incident) => (
                <tr
                  key={incident.id}
                  className="hover:bg-zinc-900/40 transition-colors group cursor-pointer"
                  onClick={() => setSelectedIncident(incident)}
                >
                  <td className="px-6 py-4">
                    <span className="font-mono font-medium text-white group-hover:text-vs-orange transition-colors">{incident.id}</span>
                  </td>
                  <td className="px-6 py-4 font-mono text-xs" dir="ltr">{formatDateTime(incident.createdAt)}</td>
                  <td className="px-6 py-4 text-zinc-300">{incident.zone}</td>
                  <td className="px-6 py-4"><SeverityBadge severity={incident.severity} /></td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-2">
                      <StatusBadge status={incident.status} />
                      <SLABadge incident={incident} />
                    </div>
                  </td>
                  <td className="px-6 py-4 font-mono text-xs text-zinc-400">{formatDuration(incidentDuration(incident))}</td>
                  <td className="px-6 py-4">
                     <Badge>{incident.classification}</Badge>
                  </td>
	                  <td className="px-6 py-4 text-end">
	                    <div className="flex items-center justify-end space-x-1 rtl:space-x-reverse">
	                      {canOperate && incidentView === 'active' && ['New', 'Validating', 'Active'].includes(incident.status) && (
	                        <button
	                          className="text-zinc-500 hover:text-vs-orange transition-colors p-1.5 hover:bg-vs-orange/10 rounded"
	                          title="Acknowledge"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleAcknowledge(incident.id);
                          }}
                        >
	                          <ShieldCheck size={16} />
	                        </button>
	                      )}
		                      {canOperate && incidentView === 'active' && (
		                        <button
	                          className="text-zinc-500 hover:text-red-400 transition-colors p-1.5 hover:bg-red-500/10 rounded"
	                          title="Escalate"
	                          onClick={(event) => {
	                            event.stopPropagation();
	                            handleEscalate(incident.id);
	                          }}
	                        >
	                          <AlertTriangle size={16} />
	                        </button>
	                      )}
	                      {canOperate && incidentView === 'active' && (
	                        <button
	                          className="text-zinc-500 hover:text-emerald-400 transition-colors p-1.5 hover:bg-emerald-500/10 rounded"
	                          title="Resolve"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleResolve(incident.id);
                          }}
                        >
	                          <CheckCircle size={16} />
		                        </button>
		                      )}
                      {isAdmin && incidentView === 'active' && (
                        <button
                          className="text-zinc-500 hover:text-zinc-200 transition-colors p-1.5 hover:bg-zinc-800 rounded"
                          title="Archive"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleArchive(incident.id);
                          }}
                        >
                          <Archive size={16} />
                        </button>
                      )}
		                      {isAdmin && incidentView === 'history' && (
		                        <button
	                          className="text-zinc-500 hover:text-vs-orange transition-colors p-1.5 hover:bg-vs-orange/10 rounded"
	                          title="Reopen"
	                          onClick={(event) => {
	                            event.stopPropagation();
	                            handleReopen(incident.id);
	                          }}
	                        >
	                          <ShieldCheck size={16} />
	                        </button>
	                      )}
	                      <button
	                        className="text-zinc-500 hover:text-vs-orange transition-colors p-1.5 hover:bg-vs-orange/10 rounded"
	                        title="Open related alert"
	                        onClick={(event) => {
	                          event.stopPropagation();
	                          void openRelatedAlert(incident);
	                        }}
	                      >
	                        <Bell size={16} />
	                      </button>
	                      <button
	                        className="text-zinc-500 hover:text-white transition-colors p-1.5 hover:bg-zinc-800 rounded"
	                        title="Open incident"
	                        onClick={(event) => {
	                          event.stopPropagation();
	                          setSelectedIncident(incident);
	                        }}
	                      >
	                        <FileText size={16} />
	                      </button>
	                    </div>
                  </td>
                </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Add Incident Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#0f0f11] border border-zinc-800 rounded-2xl w-full max-w-xl overflow-hidden shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="p-6 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/20">
              <h3 className="text-lg font-bold text-white uppercase tracking-wider">{t('reportIncident')}</h3>
              <button onClick={() => setShowAddModal(false)} className="text-zinc-500 hover:text-white transition-colors">
                <X size={24} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <FieldRoot label={t('category')}>
                  <SelectField
                    value={formCategory} 
                    onChange={(e) => setFormCategory(e.target.value)}
                    className="bg-black"
                  >
                    <option>Near Miss</option>
                    <option>Minor Injury</option>
                    <option>Critical Failure</option>
                    <option>Property Damage</option>
                  </SelectField>
                </FieldRoot>
                <FieldRoot label={t('severity')}>
                  <SelectField
                    value={formSeverity} 
                    onChange={(e) => setFormSeverity(e.target.value as Severity)}
                    className="bg-black"
                  >
                    <option value="High">{t('high')}</option>
                    <option value="Medium">{t('medium')}</option>
                    <option value="Low">{t('low')}</option>
                  </SelectField>
                </FieldRoot>
              </div>
              <FieldRoot label={t('location')}>
                <SelectField
                  value={formZone}
                  onChange={(e) => setFormZone(e.target.value)}
                  className="bg-black"
                >
                  <option>Zone A - Welding</option>
                  <option>Zone B - Forklift</option>
                  <option>Zone C - Loading</option>
                  <option>Zone D - Assembly</option>
                </SelectField>
              </FieldRoot>
              <FieldRoot label={`${t('description')} *`}>
                <TextAreaField
                  rows={2} 
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  className="bg-black"
                  placeholder="Describe what happened..."
                />
              </FieldRoot>
              <div className="grid grid-cols-2 gap-4">
                <FieldRoot label="Root Cause">
                  <TextInput
                    type="text"
                    value={formRootCause}
                    onChange={(e) => setFormRootCause(e.target.value)}
                    className="bg-black"
                    placeholder="e.g. Procedural Error"
                  />
                </FieldRoot>
                <FieldRoot label="Corrective Action">
                  <TextInput
                    type="text"
                    value={formCorrectiveAction}
                    onChange={(e) => setFormCorrectiveAction(e.target.value)}
                    className="bg-black"
                    placeholder="e.g. Additional Training"
                  />
                </FieldRoot>
              </div>
            </div>
            <div className="p-6 bg-zinc-900/30 flex justify-end space-x-3 rtl:space-x-reverse">
              <Button onClick={() => setShowAddModal(false)} variant="ghost">{t('cancel')}</Button>
              <Button
                onClick={handleAddIncident}
                disabled={!formDescription.trim()}
                variant="primary"
                icon={<CheckCircle2 size={16} />}
              >
                {t('submit')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </PageShell>
  );
};

export default Incidents;
