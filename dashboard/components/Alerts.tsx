import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { 
  Filter, 
  Search, 
  ChevronDown, 
  X,
  PlayCircle,
  MessageSquare,
  CheckCircle,
  AlertOctagon,
  Clock,
  MapPin,
  Share2,
  Download,
  AlertTriangle,
  FileText,
  MoreHorizontal,
  ChevronUp,
  Trash2
} from 'lucide-react';
import { Alert as AlertType, Severity, Status, HazardType } from '../types';
import { useLanguage } from '../contexts/LanguageContext';
import { AlertsAPI } from '../api';
import { a11yClasses } from '../utils/accessibility';

const StatusPill = ({ status }: { status: Status }) => {
  const styles: Record<string, string> = {
    New: 'bg-blue-900/30 text-blue-400 border-blue-800',
    Acknowledged: 'bg-vs-orange/10 text-vs-orange border-vs-orange/30',
    Resolved: 'bg-emerald-900/30 text-emerald-400 border-emerald-800',
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

const AlertDetails = ({ alert, onClose, onAcknowledge, onResolve, onEscalate }: { alert: AlertType, onClose: () => void, onAcknowledge: () => void, onResolve: () => void, onEscalate: () => void }) => {
  const { t } = useLanguage();
  
  return (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm p-4 animate-in fade-in duration-200" role="dialog" aria-modal="true" aria-label={`Alert details: ${alert.id}`}>
    <div className="bg-[#0f0f11] rounded-lg border border-zinc-800 shadow-2xl w-full max-w-6xl h-[90vh] flex flex-col overflow-hidden">
      <div className="h-16 px-6 border-b border-zinc-800 flex justify-between items-center bg-[#0f0f11] flex-shrink-0">
        <div className="flex items-center space-x-4 rtl:space-x-reverse">
          <h2 className="text-lg font-bold text-white tracking-tight flex items-center">
            {t('alertDetails')} <span className="mx-2 text-zinc-600">/</span> <span className="font-mono text-vs-orange">{alert.id}</span>
          </h2>
          <StatusPill status={alert.status} />
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
               <img 
                 src={alert.thumbnail} 
                 alt={`Alert evidence frame: ${alert.type} incident at ${alert.zone}`}
                 className="w-full h-full object-cover opacity-90" 
               />
               <div className="absolute top-4 start-4 bg-black/70 backdrop-blur px-3 py-1.5 rounded border border-white/10 flex items-center space-x-2 rtl:space-x-reverse">
                  <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" aria-hidden="true"></div>
                  <span className="text-white text-xs font-mono uppercase tracking-tighter">Event Capture • {alert.timestamp}</span>
               </div>
               
               <div className="absolute inset-0 pointer-events-none">
                  <div className="absolute top-1/4 left-1/3 w-32 h-48 border-2 border-vs-orange/80 shadow-[0_0_15px_rgba(255,106,0,0.5)]">
                     <div className="bg-vs-orange text-black text-[9px] font-bold px-1.5 py-0.5 absolute -top-5 left-0">Violation: {alert.type} {alert.confidence}%</div>
                  </div>
               </div>
             </div>
             <div className="grid grid-cols-2 gap-4">
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
                      <p className="text-sm text-zinc-200">{alert.zone}</p>
                   </div>
                </div>
             </div>
        </div>
        <div className="w-96 bg-[#0f0f11] border-s border-zinc-800 flex flex-col p-6 shadow-xl">
           <h3 className="text-sm font-bold text-white uppercase tracking-widest mb-6 opacity-60">System Actions</h3>
           <div className="space-y-3">
              {alert.status === 'New' && (
                <button 
                  className={`w-full py-3 bg-vs-orange hover:bg-vs-lightOrange text-black font-bold rounded text-xs uppercase tracking-widest transition-all shadow-glow flex items-center justify-center space-x-2 rtl:space-x-reverse ${a11yClasses.focusRing}`}
                  onClick={onAcknowledge}
                  aria-label="Acknowledge this alert"
                >
                   <CheckCircle size={16} aria-hidden="true" />
                   <span>{t('acknowledge')}</span>
                </button>
              )}
              {(alert.status === 'New' || alert.status === 'Acknowledged') && (
                <button 
                  className={`w-full py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded text-xs uppercase tracking-widest transition-all flex items-center justify-center space-x-2 rtl:space-x-reverse ${a11yClasses.focusRing}`}
                  onClick={onResolve}
                  aria-label="Resolve this alert"
                >
                   <CheckCircle size={16} aria-hidden="true" />
                   <span>{t('resolve')}</span>
                </button>
              )}
              <button 
                className={`w-full py-3 bg-zinc-800 hover:bg-zinc-700 text-white font-bold rounded text-xs uppercase tracking-widest transition-all border border-zinc-700 flex items-center justify-center space-x-2 rtl:space-x-reverse ${a11yClasses.focusRing}`}
                onClick={onEscalate}
                aria-label="Escalate this alert"
              >
                 <FileText size={16} aria-hidden="true" />
                 <span>{t('escalate')}</span>
              </button>
           </div>
           
           <div className="mt-8 border-t border-zinc-800 pt-6">
              <h4 className="text-[10px] font-bold text-zinc-600 uppercase mb-4 tracking-widest">Metadata</h4>
              <div className="space-y-2 text-[11px] font-mono text-zinc-500">
                 <div className="flex justify-between"><span>Frame ID:</span><span className="text-zinc-300">FR-{Math.floor(Math.random() * 99999)}-X</span></div>
                 <div className="flex justify-between"><span>Camera:</span><span className="text-zinc-300">{alert.camera}</span></div>
                 <div className="flex justify-between"><span>Camera ID:</span><span className="text-zinc-300">{alert.cameraId || '—'}</span></div>
                 <div className="flex justify-between"><span>Camera Name:</span><span className="text-zinc-300">{alert.cameraName || '—'}</span></div>
                 <div className="flex justify-between"><span>Worker ID:</span><span className="text-zinc-300">{alert.workerId || '—'}</span></div>
                 <div className="flex justify-between"><span>Worker GPU:</span><span className="text-zinc-300">{alert.workerGpuId || '—'}</span></div>
                 <div className="flex justify-between"><span>Resolution:</span><span className="text-zinc-300">1920x1080</span></div>
                 <div className="flex justify-between"><span>Confidence:</span><span className="text-zinc-300">{alert.confidence}%</span></div>
              </div>
           </div>
        </div>
      </div>
    </div>
  </div>
  );
};

const Alerts = () => {
  const [alerts, setAlerts] = useState<AlertType[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAlert, setSelectedAlert] = useState<AlertType | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [showFilters, setShowFilters] = useState(false);
  const { t } = useLanguage();

  const fetchAlerts = useCallback(async () => {
    try {
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

  const filteredAlerts = useMemo(() => {
    let result = alerts;

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      result = result.filter(alert =>
        alert.id.toLowerCase().includes(query) ||
        alert.type.toLowerCase().includes(query) ||
        alert.zone.toLowerCase().includes(query)
      );
    }

    if (severityFilter !== 'all') {
      result = result.filter(alert => alert.severity.toLowerCase() === severityFilter.toLowerCase());
    }

    if (typeFilter !== 'all') {
      result = result.filter(alert => alert.type.toLowerCase() === typeFilter.toLowerCase());
    }

    return result;
  }, [alerts, searchQuery, severityFilter, typeFilter]);

  const severityOptions: Severity[] = ['High', 'Medium', 'Low'];
  const typeOptions: HazardType[] = Array.from(new Set(alerts.map(a => a.type)));

  const handleAcknowledge = () => {
    if (!selectedAlert) return;
    setAlerts(prev => prev.map(a => a.id === selectedAlert.id ? { ...a, status: 'Acknowledged' } : a));
    setSelectedAlert(prev => prev ? { ...prev, status: 'Acknowledged' } : null);
  };

  const handleResolve = () => {
    if (!selectedAlert) return;
    setAlerts(prev => prev.map(a => a.id === selectedAlert.id ? { ...a, status: 'Resolved' } : a));
    setSelectedAlert(prev => prev ? { ...prev, status: 'Resolved' } : null);
  };

  const handleEscalate = () => {
    if (!selectedAlert) return;
    alert(`Escalating alert ${selectedAlert.id} to incident management`);
  };

  const handleDelete = (id: string) => {
    setAlerts(prev => prev.filter(a => a.id !== id));
  };

  return (
    <div className="flex flex-col h-full">
      {selectedAlert && (
        <AlertDetails
          alert={selectedAlert}
          onClose={() => setSelectedAlert(null)}
          onAcknowledge={handleAcknowledge}
          onResolve={handleResolve}
          onEscalate={handleEscalate}
        />
      )}

      <div className="px-6 pt-6 pb-4 bg-gradient-to-b from-[#050505] to-transparent">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h2 className="text-2xl font-bold text-white">{t('alerts')}</h2>
            <p className="text-sm text-zinc-500">{filteredAlerts.length} {t('alerts')} total</p>
          </div>
          <div className="text-xs text-zinc-500 font-mono flex items-center space-x-2 rtl:space-x-reverse">
            <span className="inline-flex h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true"></span>
            <span>{t('systemActive')}</span>
          </div>
        </div>

        <div className="flex gap-3 flex-wrap">
          <div className="flex-1 min-w-[240px] relative">
            <Search size={16} className="absolute start-3 top-1/2 -translate-y-1/2 text-zinc-600" aria-hidden="true" />
            <input
              type="text"
              placeholder={t('search')}
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
        </div>

        {showFilters && (
          <div id="filter-panel" className="mt-3 p-4 bg-zinc-900 border border-zinc-800 rounded-lg flex gap-4 flex-wrap">
            <div className="flex-1 min-w-[150px]">
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
            <div className="flex-1 min-w-[150px]">
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
            <div className="flex items-end">
              <button
                onClick={() => {
                  setSeverityFilter('all');
                  setTypeFilter('all');
                  setSearchQuery('');
                }}
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
            {loading ? (
              <div className="flex items-center justify-center h-48">
                <div className="text-center">
                  <div className="w-8 h-8 border-2 border-vs-orange border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                  <p className="text-zinc-500 text-sm">{t('loading')}...</p>
                </div>
              </div>
            ) : filteredAlerts.length === 0 ? (
              <div className="text-center py-12">
                <AlertTriangle size={32} className="mx-auto mb-3 text-zinc-700" aria-hidden="true" />
                <p className="text-zinc-500 text-sm">{t('noAlerts')}</p>
              </div>
            ) : (
              filteredAlerts.map((alert) => (
                <div
                  key={alert.id}
                  className="bg-[#0f0f11] border border-zinc-800 rounded-lg p-4 hover:border-zinc-700 transition-colors cursor-pointer group"
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
                      <div className="w-12 h-12 rounded-lg bg-black overflow-hidden border border-zinc-800 flex-shrink-0">
                        <img 
                          src={alert.thumbnail} 
                          alt={`Alert thumbnail: ${alert.type}`}
                          className="w-full h-full object-cover" 
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-white font-semibold group-hover:text-vs-orange transition-colors truncate">{alert.type}</span>
                          <StatusPill status={alert.status} />
                        </div>
                        <div className="mb-1 flex flex-wrap gap-1 text-[9px] font-mono uppercase tracking-wide text-zinc-500">
                          {alert.cameraId && <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5">Cam {alert.cameraId}</span>}
                          {alert.workerId && <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5">Worker {alert.workerId}</span>}
                        </div>
                        <p className="text-xs text-zinc-500 mb-1">{alert.zone} • {alert.timestamp}</p>
                        <p className="text-sm text-zinc-300 line-clamp-2">{alert.description}</p>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-2 flex-shrink-0">
                      <div className={`px-2 py-1 rounded text-[10px] uppercase font-bold tracking-wider border ${
                        alert.severity === 'High' ? 'text-red-500 bg-red-500/10 border-red-500/20' :
                        alert.severity === 'Medium' ? 'text-vs-orange bg-vs-orange/10 border-vs-orange/20' :
                        'text-yellow-500 bg-yellow-500/10 border-yellow-500/20'
                      }`}
                      role="img"
                      aria-label={`Severity: ${alert.severity}`}
                      >
                        {alert.severity}
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(alert.id);
                        }}
                        className={`p-1.5 hover:bg-red-500/20 rounded text-zinc-500 hover:text-red-500 transition-colors ${a11yClasses.focusRing}`}
                        aria-label={`Delete alert ${alert.id}`}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
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
