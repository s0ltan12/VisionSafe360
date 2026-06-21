import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { 
  Filter, 
  Search, 
  ChevronDown, 
  X,
  ExternalLink,
  CircleDot,
  AlertOctagon,
  MapPin,
  Download,
  AlertTriangle,
  ImageOff,
  RefreshCw,
  SlidersHorizontal,
  Clock3,
  Camera,
  Link2,
} from 'lucide-react';
import { Alert as AlertType, AlertEvent, CameraSafetyZone, Severity, Status, HazardType } from '../types';
import { useLanguage } from '../contexts/LanguageContext';
import { AlertsAPI } from '../api';
import { a11yClasses } from '../utils/accessibility';
import SafetyZonesOverlay from './SafetyZonesOverlay';

const StatusPill = ({ status }: { status: Status }) => {
  const styles: Record<string, string> = {
    New: 'bg-blue-900/30 text-blue-400 border-blue-800',
    Acknowledged: 'bg-vs-orange/10 text-vs-orange border-vs-orange/30',
    'In Investigation': 'bg-purple-900/30 text-purple-300 border-purple-700',
    Resolved: 'bg-emerald-900/30 text-emerald-400 border-emerald-800',
    Archived: 'bg-zinc-800 text-zinc-400 border-zinc-700',
    'False Positive': 'bg-zinc-800 text-zinc-400 border-zinc-700',
    Dismissed: 'bg-zinc-800 text-zinc-500 border-zinc-700',
  };
  const { t } = useLanguage();
  return (
    <span 
      className={`px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wider ${styles[status] || styles.New}`}
      role="img"
      aria-label={`Status: ${status}`}
    >
      {t(status.toLowerCase() as any)}
    </span>
  );
};

const SeverityBadge = ({ severity }: { severity: Severity }) => {
  const styles: Record<string, string> = {
    Critical: 'text-red-200 bg-red-600/20 border-red-500/40',
    High: 'text-red-400 bg-red-500/10 border-red-500/25',
    Medium: 'text-vs-orange bg-vs-orange/10 border-vs-orange/25',
    Low: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/25',
  };
  return (
    <span className={`px-2 py-1 rounded border text-[10px] uppercase font-bold tracking-wider ${styles[severity] || styles.Medium}`}>
      {severity}
    </span>
  );
};

const formatConfidence = (confidence?: number | null) => {
  if (confidence === null || confidence === undefined || Number.isNaN(Number(confidence))) {
    return '—';
  }
  const value = Number(confidence);
  return `${value > 1 ? value.toFixed(1) : (value * 100).toFixed(1)}%`;
};

const formatDateTime = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const formatShortDateTime = (value?: string | null) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const parseAlertDate = (value?: string | null) => {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const isWithinWindow = (value: string | null | undefined, days: number | 'all') => {
  if (days === 'all') return true;
  const parsed = parseAlertDate(value);
  if (!parsed) return false;
  const cutoff = new Date();
  cutoff.setHours(0, 0, 0, 0);
  cutoff.setDate(cutoff.getDate() - (days - 1));
  return parsed >= cutoff;
};

const alertHasEvidence = (alert: AlertType) => Boolean(alert.thumbnail || alert.eventFrame || alert.videoEvidence);

const alertHasLinkedIncident = (alert: AlertType) => Boolean(alert.incidentId);

const csvEscape = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`;

const formatTimelineAction = (action: string) => {
  const labels: Record<string, string> = {
    created: 'Alert created',
    acknowledged: 'Acknowledged',
    investigating: 'Investigation started',
    resolved: 'Resolved',
    false_positive: 'Marked false positive',
    archived: 'Archived',
  };
  return labels[action] || action.replace(/_/g, ' ');
};

const formatResolution = (alert: AlertType) => {
  if (alert.frameWidth && alert.frameHeight) {
    return `${alert.frameWidth}x${alert.frameHeight}`;
  }
  return 'Captured frame';
};

const formatLocationLine = (alert: AlertType) => {
  const parts = [alert.areaName, alert.zoneName].filter(Boolean);
  if (parts.length > 0) {
    return parts.join(' / ');
  }
  return alert.zone || 'Unassigned';
};

const EvidencePlaceholder = ({ compact = false }: { compact?: boolean }) => (
  <div className={`w-full h-full flex ${compact ? 'items-center justify-center' : 'items-center justify-center flex-col gap-3'} bg-zinc-950 text-zinc-600`}>
    <ImageOff size={compact ? 18 : 40} aria-hidden="true" />
    {!compact && (
      <div className="text-center">
        <p className="text-sm font-semibold text-zinc-400">No evidence frame captured</p>
        <p className="text-xs text-zinc-600 mt-1">New hazard alerts will include the annotated frame.</p>
      </div>
    )}
  </div>
);

const zoneFromSnapshot = (value: unknown, cameraId?: string | null): CameraSafetyZone | null => {
  if (!value || typeof value !== 'object') return null;
  const snapshot = value as Record<string, any>;
  const polygon = Array.isArray(snapshot.polygon)
    ? snapshot.polygon.map((point: any) => ({ x: Number(point?.x), y: Number(point?.y) }))
    : [];
  if (polygon.length < 3 || polygon.some(point => !Number.isFinite(point.x) || !Number.isFinite(point.y))) {
    return null;
  }
  return {
    id: String(snapshot.id ?? 'snapshot-zone'),
    cameraId: String(snapshot.camera_id ?? snapshot.cameraId ?? cameraId ?? ''),
    name: String(snapshot.name ?? 'Safety Zone'),
    zoneType: String(snapshot.zone_type ?? snapshot.zoneType ?? 'custom') as CameraSafetyZone['zoneType'],
    polygon,
    coordinateSpace: String(snapshot.coordinate_space ?? snapshot.coordinateSpace ?? 'source_pixels'),
    sourceWidth: Number(snapshot.source_width ?? snapshot.sourceWidth ?? 1280),
    sourceHeight: Number(snapshot.source_height ?? snapshot.sourceHeight ?? 720),
    color: String(snapshot.color ?? '#f97316'),
    enabled: true,
    priority: Number(snapshot.priority ?? 100),
    rules: {
      allowedClasses: ['person', 'forklift'],
      deniedClasses: [],
      requiredPpe: [],
      cooldownSec: 30,
      minPersistenceSec: 0.5,
      severity: 'High',
    },
  };
};

const AlertDetails = ({
  alert,
  onClose,
  onOpenIncident,
  timeline,
  timelineLoading,
  timelineError,
}: {
  alert: AlertType,
  onClose: () => void,
  onOpenIncident: (incidentId: string) => void,
  timeline: AlertEvent[],
  timelineLoading: boolean,
  timelineError: string | null,
}) => {
	  const { t } = useLanguage();
	  const [videoFailed, setVideoFailed] = useState(false);
	  const [previewFrame, setPreviewFrame] = useState<string | null>(null);
	  const cameraZones = useMemo(() => {
	    const snapshot = zoneFromSnapshot(alert.eventMetadata?.safety_zone_snapshot, alert.cameraId);
	    return snapshot ? [snapshot] : [];
	  }, [alert.eventMetadata, alert.cameraId]);
	  const shouldRenderZoneOverlay = cameraZones.length > 0 && alert.eventMetadata?.evidence_has_safety_zone_overlay !== true;
	  const hasVideoEvidence = Boolean(alert.videoEvidence) && !videoFailed;
	  const exactEventFrame = alert.eventFrame || alert.thumbnail || null;
	  const hasEvidence = hasVideoEvidence || Boolean(exactEventFrame);
	  const confidenceLabel = formatConfidence(alert.confidence);

  useEffect(() => {
    setVideoFailed(false);
  }, [alert.id, alert.videoEvidence]);

  return (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm p-4 animate-in fade-in duration-200" role="dialog" aria-modal="true" aria-label={`Alert details: ${alert.id}`}>
	    <div className="bg-[#0f0f11] rounded-lg border border-zinc-800 shadow-2xl w-full max-w-[min(96vw,96rem)] h-[90vh] flex flex-col overflow-hidden">
	      {previewFrame && (
	        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/95 p-4" role="dialog" aria-modal="true" aria-label="Exact event frame preview">
	          <button
	            type="button"
	            onClick={() => setPreviewFrame(null)}
	            className={`absolute end-5 top-5 rounded border border-zinc-700 bg-zinc-950/90 p-2 text-zinc-300 hover:bg-zinc-900 hover:text-white ${a11yClasses.focusRing}`}
	            aria-label="Close exact event frame preview"
	          >
	            <X size={20} aria-hidden="true" />
	          </button>
	          <div className="relative inline-block max-h-[92vh] max-w-[96vw] bg-black">
	            <img
	              src={previewFrame}
	              alt={`Opened exact event frame: ${alert.type} at ${alert.zone}`}
	              className="block max-h-[92vh] max-w-[96vw] object-contain"
	            />
              {shouldRenderZoneOverlay && <SafetyZonesOverlay zones={cameraZones} />}
	          </div>
	        </div>
	      )}
	      <div className="h-16 px-6 border-b border-zinc-800 flex justify-between items-center bg-[#0f0f11] flex-shrink-0">
        <div className="flex items-center space-x-4 rtl:space-x-reverse">
          <h2 className="text-lg font-bold text-white tracking-tight flex items-center">
            {t('alertDetails')} <span className="mx-2 text-zinc-600">/</span> <span className="font-mono text-vs-orange">{alert.id}</span>
          </h2>
          <StatusPill status={alert.status} />
          <SeverityBadge severity={alert.severity} />
        </div>
        <div className="flex items-center space-x-2 rtl:space-x-reverse">
           <button 
             className={`p-2 hover:bg-zinc-800 rounded text-zinc-400 hover:text-white transition-colors ${a11yClasses.focusRing}`}
             onClick={() => {
             const csvContent = `ID,Type,Severity,Zone,Camera,CameraID,CameraName,WorkerID,WorkerGPU,Time,Status,Description\n"${alert.id}","${alert.type}","${alert.severity}","${alert.zone}","${alert.camera}","${alert.cameraId || ''}","${alert.cameraName || ''}","${alert.workerId || ''}","${alert.workerGpuId || ''}","${alert.timestamp}","${alert.status}","${alert.description}"`;
             const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
             const link = document.createElement('a');
             link.href = URL.createObjectURL(blob);
             link.download = `alert_${alert.id}.csv`;
             document.body.appendChild(link);
             link.click();
             document.body.removeChild(link);
             URL.revokeObjectURL(link.href);
           }}
           aria-label="Download alert details as CSV"
           >
             <Download size={18} aria-hidden="true" />
           </button>
           <button 
             onClick={onClose}
             className={`p-2 hover:bg-zinc-800 rounded text-zinc-400 hover:text-white transition-colors ${a11yClasses.focusRing}`}
             aria-label="Close alert details"
           >
             <X size={20} aria-hidden="true" />
           </button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col bg-black p-6 overflow-y-auto">
             <div className="relative aspect-video bg-zinc-900 rounded-lg overflow-hidden border border-zinc-800 mb-4 group shadow-2xl">
               {hasVideoEvidence ? (
                 <video
                   src={alert.videoEvidence || ''}
                   poster={exactEventFrame || undefined}
                   className="w-full h-full object-contain bg-black"
                   controls
	                   controlsList="nodownload"
	                   autoPlay
	                   muted
	                   playsInline
	                   preload="metadata"
                   aria-label={`3 second alert evidence clip: ${alert.type} incident at ${alert.zone}. Event occurs at the midpoint.`}
                   onError={() => setVideoFailed(true)}
                 />
	               ) : exactEventFrame ? (
	                 <button
	                   type="button"
	                   onClick={() => setPreviewFrame(exactEventFrame)}
	                   className="relative h-full w-full cursor-zoom-in bg-black"
	                   aria-label="Open alert evidence frame"
	                 >
	                   <img
	                     src={exactEventFrame}
	                     alt={`Alert evidence frame: ${alert.type} incident at ${alert.zone}`}
	                     className="h-full w-full object-contain opacity-90"
	                   />
	                 </button>
               ) : (
                 <EvidencePlaceholder />
               )}
               {hasEvidence && shouldRenderZoneOverlay && <SafetyZonesOverlay zones={cameraZones} />}
               <div className="absolute top-4 start-4 bg-black/70 backdrop-blur px-3 py-1.5 rounded border border-white/10 flex items-center space-x-2 rtl:space-x-reverse">
                  <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" aria-hidden="true"></div>
                  <span className="text-white text-xs font-mono uppercase tracking-tighter">{hasVideoEvidence ? '3s Evidence Clip' : hasEvidence ? 'Evidence Capture' : 'Alert Record'} • {alert.timestamp}</span>
               </div>

               {hasVideoEvidence && (
                 <div className="absolute top-4 end-4 rounded border border-white/10 bg-black/70 px-3 py-1.5 text-xs font-mono uppercase tracking-tighter text-zinc-200 backdrop-blur pointer-events-none">
                   Event at 1.5s
                 </div>
               )}
               
               {hasEvidence && !hasVideoEvidence && (
                 <div className="absolute bottom-4 start-4 end-4 pointer-events-none">
                   <div className="inline-flex max-w-full items-center gap-3 rounded border border-vs-orange/40 bg-black/75 px-3 py-2 text-xs font-mono text-zinc-200 backdrop-blur">
                     <span className="font-bold uppercase text-vs-orange">{alert.type}</span>
                     <span className="text-zinc-600">|</span>
                     <span>{alert.cameraName || alert.cameraId || alert.camera}</span>
                     <span className="text-zinc-600">|</span>
                     <span>Confidence {confidenceLabel}</span>
                   </div>
                 </div>
               )}
             </div>
             <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(18rem,0.85fr)_1fr_1fr]">
                <div className="bg-[#0f0f11] border border-zinc-800 rounded overflow-hidden">
	                   <div className="aspect-video bg-black">
	                     {exactEventFrame ? (
	                       <button
	                         type="button"
	                         onClick={() => setPreviewFrame(exactEventFrame)}
	                         className="relative h-full w-full cursor-zoom-in bg-black"
	                         aria-label="Open exact event frame"
	                       >
	                         <img
	                           src={exactEventFrame}
	                           alt={`Exact annotated event frame: ${alert.type} at ${alert.zone}`}
	                           className="h-full w-full object-contain"
	                         />
                          {shouldRenderZoneOverlay && <SafetyZonesOverlay zones={cameraZones} />}
	                       </button>
	                     ) : (
                       <EvidencePlaceholder compact />
                     )}
                   </div>
                   <div className="border-t border-zinc-800 p-4">
                      <h4 className="text-[10px] font-bold text-zinc-500 uppercase mb-2">Exact Event Frame</h4>
                      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] font-mono text-zinc-500">
                        <span>Frame</span><span className="text-right text-zinc-300">{alert.frameNumber ?? '—'}</span>
                        <span>Track</span><span className="text-right text-zinc-300">{alert.trackId ?? alert.workerId ?? '—'}</span>
                        <span>Event Time</span><span className="text-right text-zinc-300">1.5s</span>
                      </div>
                   </div>
                </div>
                <div className="bg-[#0f0f11] border border-zinc-800 rounded p-4 flex items-start space-x-3 rtl:space-x-reverse">
                   <div className="p-2 bg-blue-500/10 rounded border border-blue-500/20 text-blue-500"><AlertOctagon size={18} aria-hidden="true" /></div>
                   <div className="flex-1">
                      <h4 className="text-[10px] font-bold text-zinc-500 uppercase mb-2">AI Analysis Engine</h4>
                      <p className="text-sm text-zinc-200">{alert.description}</p>
                   </div>
                </div>
                <div className="bg-[#0f0f11] border border-zinc-800 rounded p-4 flex items-start space-x-3 rtl:space-x-reverse">
                   <div className="p-2 bg-vs-orange/10 rounded border border-vs-orange/20 text-vs-orange"><MapPin size={18} aria-hidden="true" /></div>
                   <div className="flex-1">
                      <h4 className="text-[10px] font-bold text-zinc-500 uppercase mb-2">Geolocation Data</h4>
                      <p className="text-sm text-zinc-200">{formatLocationLine(alert)}</p>
                      <p className="text-[11px] text-zinc-500 mt-1">{alert.cameraName || alert.camera}</p>
                   </div>
                </div>
             </div>
        </div>
        <div className="w-full max-w-[22rem] bg-[#0f0f11] border-s border-zinc-800 flex flex-col p-4 sm:p-6 shadow-xl">
	           <h3 className="text-sm font-bold text-white uppercase tracking-widest mb-6 opacity-60">Alert Signal</h3>
	           <div className="rounded border border-zinc-800 bg-zinc-950/60 p-4">
	              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Linked Incident</p>
	              <p className="mt-2 font-mono text-sm text-zinc-200">{alert.incidentId || 'Unlinked legacy alert'}</p>
	              {alert.incidentId && (
	                <button
	                  type="button"
	                  onClick={() => onOpenIncident(alert.incidentId as string)}
	                  className={`mt-4 inline-flex items-center gap-2 rounded border border-vs-orange/40 bg-vs-orange/10 px-3 py-2 text-xs font-bold uppercase tracking-wide text-vs-orange transition-colors hover:bg-vs-orange hover:text-black ${a11yClasses.focusRing}`}
	                  aria-label={`Open linked incident ${alert.incidentId}`}
	                >
	                  <ExternalLink size={14} aria-hidden="true" />
	                  <span>Open Incident</span>
	                </button>
	              )}
	              <p className="mt-3 text-xs leading-relaxed text-zinc-500">
	                Incident lifecycle actions are handled from the incident workspace so alert signals cannot diverge from the operational case.
	              </p>
	           </div>
           
           <div className="mt-8 border-t border-zinc-800 pt-6">
              <h4 className="text-[10px] font-bold text-zinc-600 uppercase mb-4 tracking-widest">Metadata</h4>
              <div className="space-y-2 text-[11px] font-mono text-zinc-500">
                 <div className="flex justify-between"><span>Evidence:</span><span className="text-zinc-300">{hasVideoEvidence ? '3 sec clip' : hasEvidence ? 'Captured frame' : 'Not available'}</span></div>
                 <div className="flex justify-between"><span>Frame:</span><span className="text-zinc-300">{alert.frameNumber ?? '—'}</span></div>
                 <div className="flex justify-between"><span>Camera:</span><span className="text-zinc-300">{alert.camera}</span></div>
                 <div className="flex justify-between"><span>Camera ID:</span><span className="text-zinc-300">{alert.cameraId || '—'}</span></div>
                 <div className="flex justify-between"><span>Camera Name:</span><span className="text-zinc-300">{alert.cameraName || '—'}</span></div>
                 <div className="flex justify-between"><span>Worker ID:</span><span className="text-zinc-300">{alert.workerId || '—'}</span></div>
                 <div className="flex justify-between"><span>Worker GPU:</span><span className="text-zinc-300">{alert.workerGpuId || '—'}</span></div>
                 <div className="flex justify-between"><span>Resolution:</span><span className="text-zinc-300">{formatResolution(alert)}</span></div>
                 <div className="flex justify-between"><span>Confidence:</span><span className="text-zinc-300">{confidenceLabel}</span></div>
                 <div className="flex justify-between"><span>Acknowledged By:</span><span className="text-zinc-300">{alert.acknowledgedBy || '—'}</span></div>
                 <div className="flex justify-between"><span>Acknowledged At:</span><span className="text-zinc-300 text-right">{formatDateTime(alert.acknowledgedAt)}</span></div>
                 <div className="flex justify-between"><span>Resolved By:</span><span className="text-zinc-300">{alert.resolvedBy || '—'}</span></div>
                 <div className="flex justify-between"><span>Resolved At:</span><span className="text-zinc-300 text-right">{formatDateTime(alert.resolvedAt)}</span></div>
              </div>
           </div>

           <div className="mt-8 border-t border-zinc-800 pt-6 min-h-0">
              <h4 className="text-[10px] font-bold text-zinc-600 uppercase mb-4 tracking-widest">Lifecycle Timeline</h4>
              {timelineLoading ? (
                <div className="text-xs text-zinc-500">Loading timeline...</div>
              ) : timelineError ? (
                <div className="rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{timelineError}</div>
              ) : timeline.length === 0 ? (
                <div className="text-xs text-zinc-500">No lifecycle events recorded.</div>
              ) : (
                <div className="space-y-4">
                  {timeline.map((event, index) => (
                    <div key={event.id} className="relative flex gap-3">
                      <div className="flex flex-col items-center">
                        <div className="rounded-full border border-vs-orange/40 bg-vs-orange/10 p-1 text-vs-orange">
                          <CircleDot size={12} aria-hidden="true" />
                        </div>
                        {index < timeline.length - 1 && <div className="mt-1 h-full min-h-8 w-px bg-zinc-800" aria-hidden="true" />}
                      </div>
                      <div className="min-w-0 pb-1">
                        <div className="text-xs font-semibold text-zinc-200 capitalize">{formatTimelineAction(event.action)}</div>
                        <div className="mt-1 text-[11px] font-mono text-zinc-500">{formatDateTime(event.createdAt)}</div>
                        <div className="mt-1 text-[11px] text-zinc-400">
                          {event.actorName || 'System'}
                          {event.newStatus ? <span className="text-zinc-600">{` -> ${event.newStatus}`}</span> : null}
                        </div>
                        {event.note && <div className="mt-1 text-[11px] text-zinc-500">{event.note}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
           </div>
        </div>
      </div>
    </div>
  </div>
  );
};

const Alerts = ({
  targetAlertId,
  onTargetAlertOpened,
  onOpenIncident,
}: {
  targetAlertId?: string | null;
  onTargetAlertOpened?: () => void;
  onOpenIncident?: (incidentId: string) => void;
}) => {
  const [alerts, setAlerts] = useState<AlertType[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAlert, setSelectedAlert] = useState<AlertType | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [zoneFilter, setZoneFilter] = useState<string>('all');
  const [timeWindow, setTimeWindow] = useState<'all' | number>(7);
  const [evidenceFilter, setEvidenceFilter] = useState<'all' | 'withEvidence' | 'withoutEvidence' | 'linkedIncident'>('all');
  const [sortMode, setSortMode] = useState<'newest' | 'oldest' | 'severity' | 'confidence'>('newest');
  const [density, setDensity] = useState<'comfortable' | 'compact'>('comfortable');
  const [selectedAlertIds, setSelectedAlertIds] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const [timelineByAlertId, setTimelineByAlertId] = useState<Record<string, AlertEvent[]>>({});
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const { t } = useLanguage();

  const fetchAlerts = useCallback(async () => {
    try {
      setLoading(true);
      const data = await AlertsAPI.getAll();
      setAlerts(data);
    } catch (e) {
      console.error('Failed to fetch alerts:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  useEffect(() => {
    if (!targetAlertId) return;
    let cancelled = false;
    (async () => {
      try {
        const full = await AlertsAPI.getById(targetAlertId);
        if (cancelled) return;
        setAlerts(prev => {
          const exists = prev.some(alert => alert.id === full.id);
          return exists
            ? prev.map(alert => alert.id === full.id ? { ...alert, ...full } : alert)
            : [full, ...prev];
        });
        setSelectedAlert(full);
        onTargetAlertOpened?.();
      } catch (e) {
        console.error(`Failed to open alert ${targetAlertId}:`, e);
      }
    })();
    return () => { cancelled = true; };
  }, [targetAlertId, onTargetAlertOpened]);

  useEffect(() => {
    if (!selectedAlert) return;
    let cancelled = false;

    const loadTimeline = async () => {
      setTimelineError(null);
      setTimelineLoading(true);
      try {
        const events = await AlertsAPI.getEvents(selectedAlert.id);
        if (!cancelled) {
          setTimelineByAlertId(prev => ({ ...prev, [selectedAlert.id]: events }));
        }
      } catch (e) {
        console.error(`Failed to fetch alert timeline ${selectedAlert.id}:`, e);
        if (!cancelled) {
          setTimelineError('Failed to load lifecycle timeline.');
        }
      } finally {
        if (!cancelled) {
          setTimelineLoading(false);
        }
      }
    };

    void loadTimeline();
    return () => {
      cancelled = true;
    };
  }, [selectedAlert?.id]);

  useEffect(() => {
    if (!selectedAlert || selectedAlert.videoEvidence) return;
    let cancelled = false;
    (async () => {
      try {
        const full = await AlertsAPI.getById(selectedAlert.id);
        if (cancelled || !full.videoEvidence) return;
        setAlerts(prev => prev.map(a => a.id === full.id ? { ...a, videoEvidence: full.videoEvidence } : a));
        setSelectedAlert(prev => prev && prev.id === full.id ? { ...prev, videoEvidence: full.videoEvidence } : prev);
      } catch (e) {
        console.error(`Failed to fetch alert detail ${selectedAlert.id}:`, e);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedAlert?.id]);

  const filteredAlerts = useMemo(() => {
    let result = alerts;

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(alert =>
        alert.id.toLowerCase().includes(query) ||
        alert.type.toLowerCase().includes(query) ||
        alert.zone.toLowerCase().includes(query) ||
        (alert.zoneName || '').toLowerCase().includes(query) ||
        (alert.areaName || '').toLowerCase().includes(query) ||
        (alert.cameraId || '').toLowerCase().includes(query) ||
        (alert.cameraName || '').toLowerCase().includes(query) ||
        (alert.workerId || '').toLowerCase().includes(query) ||
        alert.description.toLowerCase().includes(query)
      );
    }

    result = result.filter(alert => isWithinWindow(alert.timestamp, timeWindow));

    if (severityFilter !== 'all') {
      result = result.filter(alert => alert.severity.toLowerCase() === severityFilter.toLowerCase());
    }

    if (typeFilter !== 'all') {
      result = result.filter(alert => alert.type.toLowerCase() === typeFilter.toLowerCase());
    }

    if (statusFilter !== 'all') {
      result = result.filter(alert => alert.status.toLowerCase() === statusFilter.toLowerCase());
    }

    if (zoneFilter !== 'all') {
      result = result.filter(alert => {
        const zones = [alert.zone, alert.zoneName, alert.areaName].filter(Boolean).map(value => String(value).toLowerCase());
        return zones.includes(zoneFilter.toLowerCase());
      });
    }

    if (evidenceFilter === 'withEvidence') {
      result = result.filter(alertHasEvidence);
    } else if (evidenceFilter === 'withoutEvidence') {
      result = result.filter(alert => !alertHasEvidence(alert));
    } else if (evidenceFilter === 'linkedIncident') {
      result = result.filter(alertHasLinkedIncident);
    }

    const severityRank: Record<Severity, number> = { Critical: 4, High: 3, Medium: 2, Low: 1 };
    return [...result].sort((a, b) => {
      if (sortMode === 'oldest') {
        return (parseAlertDate(a.timestamp)?.getTime() ?? 0) - (parseAlertDate(b.timestamp)?.getTime() ?? 0);
      }
      if (sortMode === 'severity') {
        return severityRank[b.severity] - severityRank[a.severity] || (parseAlertDate(b.timestamp)?.getTime() ?? 0) - (parseAlertDate(a.timestamp)?.getTime() ?? 0);
      }
      if (sortMode === 'confidence') {
        return Number(b.confidence ?? -1) - Number(a.confidence ?? -1);
      }
      return (parseAlertDate(b.timestamp)?.getTime() ?? 0) - (parseAlertDate(a.timestamp)?.getTime() ?? 0);
    });
  }, [alerts, evidenceFilter, searchQuery, severityFilter, sortMode, statusFilter, timeWindow, typeFilter, zoneFilter]);

  const severityOptions: Severity[] = ['Critical', 'High', 'Medium', 'Low'];
  const statusOptions: Status[] = Array.from(new Set(alerts.map(a => a.status))).sort() as Status[];
  const typeOptions: HazardType[] = Array.from(new Set(alerts.map(a => a.type))).sort() as HazardType[];
  const zoneOptions = Array.from(new Set(alerts.flatMap(alert => [alert.areaName, alert.zoneName, alert.zone]).filter(Boolean) as string[])).sort();
  const activeAlerts = alerts.filter(alert => ['New', 'Notified', 'Acknowledged', 'In Investigation', 'Active'].includes(alert.status)).length;
  const criticalAlerts = alerts.filter(alert => alert.severity === 'Critical').length;
  const linkedIncidents = alerts.filter(alertHasLinkedIncident).length;
  const alertsWithEvidence = alerts.filter(alertHasEvidence).length;
  const selectedAlerts = filteredAlerts.filter(alert => selectedAlertIds.includes(alert.id));
  const allFilteredSelected = filteredAlerts.length > 0 && filteredAlerts.every(alert => selectedAlertIds.includes(alert.id));

  const clearFilters = () => {
    setSeverityFilter('all');
    setTypeFilter('all');
    setStatusFilter('all');
    setZoneFilter('all');
    setTimeWindow(7);
    setEvidenceFilter('all');
    setSortMode('newest');
    setSearchQuery('');
    setSelectedAlertIds([]);
  };

  const toggleSelectedAlert = (id: string) => {
    setSelectedAlertIds(prev => prev.includes(id) ? prev.filter(item => item !== id) : [...prev, id]);
  };

  const toggleSelectAllFiltered = () => {
    setSelectedAlertIds(allFilteredSelected ? [] : filteredAlerts.map(alert => alert.id));
  };

  const exportAlerts = (rows: AlertType[]) => {
    const csvHeaders = 'ID,Type,Severity,Status,Zone,Area,Camera ID,Camera Name,Worker ID,Time,Confidence,Linked Incident,Evidence,Description';
    const csvRows = rows.map(alert => [
      alert.id,
      alert.type,
      alert.severity,
      alert.status,
      alert.zoneName || alert.zone,
      alert.areaName || '',
      alert.cameraId || '',
      alert.cameraName || alert.camera,
      alert.workerId || '',
      alert.timestamp,
      formatConfidence(alert.confidence),
      alert.incidentId || '',
      alertHasEvidence(alert) ? 'yes' : 'no',
      alert.description,
    ].map(csvEscape).join(',')).join('\n');
    const csvContent = `${csvHeaders}\n${csvRows}`;
    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = rows.length === selectedAlerts.length && selectedAlerts.length > 0 ? 'selected_alerts.csv' : 'filtered_alerts.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  };

  return (
    <div className="flex flex-col h-full">
      {selectedAlert && (
        <AlertDetails
          alert={selectedAlert}
          onClose={() => setSelectedAlert(null)}
          onOpenIncident={(incidentId) => onOpenIncident?.(incidentId)}
          timeline={timelineByAlertId[selectedAlert.id] || []}
          timelineLoading={timelineLoading}
          timelineError={timelineError}
        />
      )}

      <div className="px-6 pt-6 pb-4 bg-gradient-to-b from-[#050505] to-transparent">
        <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white">{t('alerts')}</h2>
            <p className="text-sm text-zinc-500">{filteredAlerts.length} shown of {alerts.length} total alert signals</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="mr-2 flex items-center space-x-2 text-xs font-mono text-zinc-500 rtl:space-x-reverse">
              <span className="inline-flex h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true"></span>
              <span>{t('systemActive')}</span>
            </div>
            <button
              type="button"
              onClick={fetchAlerts}
              disabled={loading}
              className={`inline-flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs font-bold uppercase tracking-wide text-zinc-300 transition-colors hover:bg-zinc-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-50 ${a11yClasses.focusRing}`}
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
            <button
              type="button"
              onClick={() => exportAlerts(selectedAlerts.length > 0 ? selectedAlerts : filteredAlerts)}
              disabled={filteredAlerts.length === 0}
              className={`inline-flex items-center gap-2 rounded-lg border border-vs-orange/30 bg-vs-orange px-3 py-2 text-xs font-bold uppercase tracking-wide text-black transition-colors hover:bg-vs-lightOrange disabled:cursor-not-allowed disabled:opacity-50 ${a11yClasses.focusRing}`}
            >
              <Download size={14} />
              Export {selectedAlerts.length > 0 ? selectedAlerts.length : 'view'}
            </button>
          </div>
        </div>

        <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div className="rounded-lg border border-zinc-800 bg-[#0f0f11] p-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Active signals</p>
            <p className="mt-2 text-2xl font-bold text-white">{activeAlerts}</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-[#0f0f11] p-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Critical</p>
            <p className={criticalAlerts > 0 ? 'mt-2 text-2xl font-bold text-red-400' : 'mt-2 text-2xl font-bold text-white'}>{criticalAlerts}</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-[#0f0f11] p-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Linked incidents</p>
            <p className="mt-2 text-2xl font-bold text-white">{linkedIncidents}</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-[#0f0f11] p-4">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Evidence ready</p>
            <p className="mt-2 text-2xl font-bold text-white">{alertsWithEvidence}</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <div className="relative min-w-0 flex-1 sm:min-w-[280px]">
            <Search size={16} className="absolute start-3 top-1/2 -translate-y-1/2 text-zinc-600" aria-hidden="true" />
            <input
              type="text"
              placeholder="Search ID, type, zone, camera, worker, description"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={`w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-9 pr-4 py-2 text-zinc-200 placeholder-zinc-600 text-sm ${a11yClasses.focusRing}`}
              aria-label="Search alerts"
            />
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-sm font-medium text-zinc-400 hover:text-white flex items-center space-x-2 rtl:space-x-reverse transition-colors ${a11yClasses.focusRing}`}
            aria-expanded={showFilters}
            aria-controls="filter-panel"
          >
            <Filter size={16} aria-hidden="true" />
            <span>{t('filters')}</span>
            <ChevronDown size={16} className={`transition-transform ${showFilters ? 'rotate-180' : ''}`} aria-hidden="true" />
            </button>
          <select
            value={sortMode}
            onChange={(event) => setSortMode(event.target.value as typeof sortMode)}
            className={`rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-300 ${a11yClasses.focusRing}`}
            aria-label="Sort alerts"
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="severity">Highest severity</option>
            <option value="confidence">Highest confidence</option>
          </select>
          <button
            type="button"
            onClick={() => setDensity(density === 'comfortable' ? 'compact' : 'comfortable')}
            className={`inline-flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm font-medium text-zinc-400 transition-colors hover:text-white ${a11yClasses.focusRing}`}
            aria-label="Toggle alert list density"
          >
            <SlidersHorizontal size={16} />
            {density === 'comfortable' ? 'Compact' : 'Comfort'}
          </button>
        </div>

        {showFilters && (
          <div id="filter-panel" className="mt-3 grid grid-cols-1 gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4 sm:grid-cols-2 xl:grid-cols-6">
            <div>
              <label htmlFor="time-filter" className="text-xs font-bold text-zinc-400 uppercase mb-2 block">Time</label>
              <select
                id="time-filter"
                value={String(timeWindow)}
                onChange={(e) => setTimeWindow(e.target.value === 'all' ? 'all' : Number(e.target.value))}
                className={`w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-zinc-200 text-sm ${a11yClasses.focusRing}`}
                aria-label="Filter by alert time window"
              >
                <option value="7">Last 7 days</option>
                <option value="14">Last 14 days</option>
                <option value="30">Last 30 days</option>
                <option value="90">Last 90 days</option>
                <option value="all">All time</option>
              </select>
            </div>
            <div className="flex-1 min-w-0 sm:min-w-[150px]">
              <label htmlFor="severity-filter" className="text-xs font-bold text-zinc-400 uppercase mb-2 block">Severity</label>
              <select
                id="severity-filter"
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                className={`w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-zinc-200 text-sm ${a11yClasses.focusRing}`}
                aria-label="Filter by severity"
              >
                <option value="all">All</option>
                {severityOptions.map(s => (
                  <option key={s} value={s.toLowerCase()}>{s}</option>
                ))}
              </select>
            </div>
            <div className="flex-1 min-w-0 sm:min-w-[150px]">
              <label htmlFor="type-filter" className="text-xs font-bold text-zinc-400 uppercase mb-2 block">Type</label>
              <select
                id="type-filter"
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className={`w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-zinc-200 text-sm ${a11yClasses.focusRing}`}
                aria-label="Filter by alert type"
              >
                <option value="all">All</option>
                {typeOptions.map(t => (
                  <option key={t} value={t.toLowerCase()}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="status-filter" className="text-xs font-bold text-zinc-400 uppercase mb-2 block">Status</label>
              <select
                id="status-filter"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className={`w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-zinc-200 text-sm ${a11yClasses.focusRing}`}
                aria-label="Filter by status"
              >
                <option value="all">All</option>
                {statusOptions.map(status => (
                  <option key={status} value={status.toLowerCase()}>{status}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="zone-filter" className="text-xs font-bold text-zinc-400 uppercase mb-2 block">Zone</label>
              <select
                id="zone-filter"
                value={zoneFilter}
                onChange={(e) => setZoneFilter(e.target.value)}
                className={`w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-zinc-200 text-sm ${a11yClasses.focusRing}`}
                aria-label="Filter by zone"
              >
                <option value="all">All</option>
                {zoneOptions.map(zone => (
                  <option key={zone} value={zone.toLowerCase()}>{zone}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="evidence-filter" className="text-xs font-bold text-zinc-400 uppercase mb-2 block">Evidence</label>
              <select
                id="evidence-filter"
                value={evidenceFilter}
                onChange={(e) => setEvidenceFilter(e.target.value as typeof evidenceFilter)}
                className={`w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-zinc-200 text-sm ${a11yClasses.focusRing}`}
                aria-label="Filter by evidence availability"
              >
                <option value="all">All</option>
                <option value="withEvidence">With evidence</option>
                <option value="withoutEvidence">Missing evidence</option>
                <option value="linkedIncident">Linked incident</option>
              </select>
            </div>
            <div className="flex items-end">
              <button
                onClick={clearFilters}
                className={`px-3 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded text-xs font-medium text-zinc-300 transition-colors ${a11yClasses.focusRing}`}
                aria-label="Clear all filters"
              >
                {t('clearAll')}
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-hidden">
        <div 
          className="h-full overflow-y-auto custom-scrollbar"
          role="region"
          aria-label="Alerts list"
          aria-live="polite"
          aria-atomic="false"
        >
          <div className="px-6 py-4 space-y-3">
            {!loading && filteredAlerts.length > 0 && (
              <div className="flex flex-col gap-3 rounded-lg border border-zinc-800 bg-[#0f0f11] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <label className="inline-flex items-center gap-3 text-xs font-medium text-zinc-400">
                  <input
                    type="checkbox"
                    checked={allFilteredSelected}
                    onChange={toggleSelectAllFiltered}
                    className="h-4 w-4 rounded border-zinc-700 bg-zinc-950 accent-vs-orange"
                  />
                  Select all {filteredAlerts.length} filtered alerts
                </label>
                <div className="flex flex-wrap gap-2 text-xs text-zinc-500">
                  <span>{selectedAlerts.length} selected</span>
                  {selectedAlerts.length > 0 && (
                    <>
                      <button
                        type="button"
                        onClick={() => exportAlerts(selectedAlerts)}
                        className={`rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 font-bold uppercase tracking-wide text-zinc-300 hover:border-vs-orange/50 hover:text-vs-orange ${a11yClasses.focusRing}`}
                      >
                        Export selected
                      </button>
                      <button
                        type="button"
                        onClick={() => setSelectedAlertIds([])}
                        className={`rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 font-bold uppercase tracking-wide text-zinc-300 hover:text-white ${a11yClasses.focusRing}`}
                      >
                        Clear selection
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}

            {loading ? (
              <div className="flex items-center justify-center h-48">
                <div className="text-center">
                  <div className="w-8 h-8 border-2 border-vs-orange border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                  <p className="text-zinc-500 text-sm">{t('loading')}...</p>
                </div>
              </div>
            ) : filteredAlerts.length === 0 ? (
              <div className="flex min-h-[320px] flex-col items-center justify-center rounded-lg border border-dashed border-zinc-800 bg-zinc-950/30 px-6 text-center">
                <AlertTriangle size={36} className="mb-4 text-zinc-700" aria-hidden="true" />
                <p className="text-sm font-semibold text-zinc-300">{alerts.length === 0 ? 'No alert signals available yet' : 'No alerts match these controls'}</p>
                <p className="mt-2 max-w-md text-xs leading-relaxed text-zinc-500">
                  {alerts.length === 0
                    ? 'When the edge AI pipeline detects hazards, alert records and evidence controls will appear here.'
                    : 'Clear filters, expand the time window, or search a different camera, zone, worker, or hazard type.'}
                </p>
                {(alerts.length > 0 || searchQuery || severityFilter !== 'all' || typeFilter !== 'all' || statusFilter !== 'all' || zoneFilter !== 'all' || evidenceFilter !== 'all') && (
                  <button
                    type="button"
                    onClick={clearFilters}
                    className={`mt-5 rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2 text-xs font-bold uppercase tracking-wide text-vs-orange hover:bg-zinc-800 ${a11yClasses.focusRing}`}
                  >
                    Reset controls
                  </button>
                )}
              </div>
            ) : (
              filteredAlerts.map((alert) => (
                <div
                  key={alert.id}
                  className={`bg-[#0f0f11] border border-zinc-800 rounded-lg ${density === 'compact' ? 'p-3' : 'p-4'} hover:border-zinc-700 transition-colors cursor-pointer group`}
                  onClick={() => setSelectedAlert(alert)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelectedAlert(alert);
                    }
                  }}
                  aria-label={`Alert: ${alert.type} - ${alert.severity} severity - ${alert.status} status`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3 rtl:space-x-reverse flex-1 min-w-0">
                      <input
                        type="checkbox"
                        checked={selectedAlertIds.includes(alert.id)}
                        onClick={(event) => event.stopPropagation()}
                        onChange={() => toggleSelectedAlert(alert.id)}
                        className="mt-3 h-4 w-4 rounded border-zinc-700 bg-zinc-950 accent-vs-orange"
                        aria-label={`Select alert ${alert.id}`}
                      />
                      <div className={`${density === 'compact' ? 'h-10 w-10' : 'w-12 h-12'} rounded-lg bg-black overflow-hidden border border-zinc-800 flex-shrink-0`}>
                        {alert.thumbnail ? (
                          <img
                            src={alert.thumbnail}
                            alt={`Alert thumbnail: ${alert.type}`}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <EvidencePlaceholder compact />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-white font-semibold group-hover:text-vs-orange transition-colors truncate">{alert.type}</span>
                          <StatusPill status={alert.status} />
                          {alertHasEvidence(alert) && <span className="rounded border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-emerald-400">Evidence</span>}
                        </div>
                        <div className="mb-1 flex flex-wrap gap-1 text-[9px] font-mono uppercase tracking-wide text-zinc-500">
                          {alert.cameraId && <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5">Cam {alert.cameraId}</span>}
                          {alert.cameraName && <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5">{alert.cameraName}</span>}
                          {alert.workerId && <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5">Worker {alert.workerId}</span>}
                          {alert.trackId && <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5">Track {alert.trackId}</span>}
                        </div>
                        <p className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
                          <span className="inline-flex items-center gap-1"><MapPin size={12} />{formatLocationLine(alert)}</span>
                          <span className="inline-flex items-center gap-1"><Clock3 size={12} />{formatShortDateTime(alert.timestamp)}</span>
                          <span className="inline-flex items-center gap-1"><Camera size={12} />{alert.cameraName || alert.cameraId || alert.camera || 'Unknown camera'}</span>
                        </p>
                        {density === 'comfortable' && <p className="text-sm text-zinc-300 line-clamp-2">{alert.description}</p>}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-2 flex-shrink-0">
                      <SeverityBadge severity={alert.severity} />
                      <span className="text-[10px] font-mono text-zinc-500">Conf {formatConfidence(alert.confidence)}</span>
                      <div className="flex flex-wrap justify-end gap-1">
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            setSelectedAlert(alert);
                          }}
                          className={`rounded border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[9px] font-mono uppercase tracking-wide text-zinc-500 transition-colors hover:border-vs-orange/50 hover:text-vs-orange ${a11yClasses.focusRing}`}
                          aria-label={`Open alert details ${alert.id}`}
                        >
                          Details
                        </button>
                        {alert.incidentId && (
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              onOpenIncident?.(alert.incidentId as string);
                            }}
                            className={`inline-flex items-center gap-1 rounded border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[9px] font-mono uppercase tracking-wide text-zinc-500 transition-colors hover:border-vs-orange/50 hover:text-vs-orange ${a11yClasses.focusRing}`}
                            aria-label={`Open linked incident ${alert.incidentId}`}
                          >
                            <Link2 size={10} />
                            {alert.incidentId}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Alerts;
