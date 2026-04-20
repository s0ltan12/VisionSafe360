
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

const StatusPill = ({ status }: { status: Status }) => {
  const styles: Record<string, string> = {
    New: 'bg-blue-900/30 text-blue-400 border-blue-800',
    Acknowledged: 'bg-vs-orange/10 text-vs-orange border-vs-orange/30',
    Resolved: 'bg-emerald-900/30 text-emerald-400 border-emerald-800',
    Dismissed: 'bg-zinc-800 text-zinc-500 border-zinc-700',
  };
  const { t } = useLanguage();
  return (
    <span className={`px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wider ${styles[status] || styles.New}`}>
      {t(status.toLowerCase() as any)}
    </span>
  );
};

const AlertDetails = ({ alert, onClose, onAcknowledge, onResolve, onEscalate }: { alert: AlertType, onClose: () => void, onAcknowledge: () => void, onResolve: () => void, onEscalate: () => void }) => {
  const { t } = useLanguage();
  
  return (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm p-4 animate-in fade-in duration-200">
    <div className="bg-[#0f0f11] rounded-lg border border-zinc-800 shadow-2xl w-full max-w-6xl h-[90vh] flex flex-col overflow-hidden">
      <div className="h-16 px-6 border-b border-zinc-800 flex justify-between items-center bg-[#0f0f11] flex-shrink-0">
        <div className="flex items-center space-x-4 rtl:space-x-reverse">
          <h2 className="text-lg font-bold text-white tracking-tight flex items-center">
            {t('alertDetails')} <span className="mx-2 text-zinc-600">/</span> <span className="font-mono text-vs-orange">{alert.id}</span>
          </h2>
          <StatusPill status={alert.status} />
        </div>
        <div className="flex items-center space-x-2 rtl:space-x-reverse">
           <button className="p-2 hover:bg-zinc-800 rounded text-zinc-400 hover:text-white transition-colors" onClick={() => {
             const csvContent = `ID,Type,Severity,Zone,Camera,Time,Status,Description\n"${alert.id}","${alert.type}","${alert.severity}","${alert.zone}","${alert.camera}","${alert.timestamp}","${alert.status}","${alert.description}"`;
             const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
             const link = document.createElement('a');
             link.href = URL.createObjectURL(blob);
             link.download = `alert_${alert.id}.csv`;
             document.body.appendChild(link);
             link.click();
             document.body.removeChild(link);
             URL.revokeObjectURL(link.href);
           }}><Download size={18} /></button>
           <button onClick={onClose} className="p-2 hover:bg-zinc-800 rounded text-zinc-400 hover:text-white transition-colors"><X size={20} /></button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col bg-black p-6 overflow-y-auto">
             <div className="relative aspect-video bg-zinc-900 rounded-lg overflow-hidden border border-zinc-800 mb-4 group shadow-2xl">
               <img src={alert.thumbnail} alt="Evidence" className="w-full h-full object-cover opacity-90" />
               <div className="absolute top-4 start-4 bg-black/70 backdrop-blur px-3 py-1.5 rounded border border-white/10 flex items-center space-x-2 rtl:space-x-reverse">
                  <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
                  <span className="text-white text-xs font-mono uppercase tracking-tighter">Event Capture • {alert.timestamp}</span>
               </div>
               
               {/* Realistic Bounding Box Simulation */}
               <div className="absolute inset-0 pointer-events-none">
                  <div className="absolute top-1/4 left-1/3 w-32 h-48 border-2 border-vs-orange/80 shadow-[0_0_15px_rgba(255,106,0,0.5)]">
                     <div className="bg-vs-orange text-black text-[9px] font-bold px-1.5 py-0.5 absolute -top-5 left-0">Violation: {alert.type} {alert.confidence}%</div>
                  </div>
               </div>
             </div>
             <div className="grid grid-cols-2 gap-4">
                <div className="bg-[#0f0f11] border border-zinc-800 rounded p-4 flex items-start space-x-3 rtl:space-x-reverse">
                   <div className="p-2 bg-blue-500/10 rounded border border-blue-500/20 text-blue-500"><AlertOctagon size={18} /></div>
                   <div className="flex-1">
                      <h4 className="text-[10px] font-bold text-zinc-500 uppercase mb-2">AI Analysis Engine</h4>
                      <p className="text-sm text-zinc-200">{alert.description}</p>
                   </div>
                </div>
                <div className="bg-[#0f0f11] border border-zinc-800 rounded p-4 flex items-start space-x-3 rtl:space-x-reverse">
                   <div className="p-2 bg-vs-orange/10 rounded border border-vs-orange/20 text-vs-orange"><MapPin size={18} /></div>
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
                <button className="w-full py-3 bg-vs-orange hover:bg-vs-lightOrange text-black font-bold rounded text-xs uppercase tracking-widest transition-all shadow-glow flex items-center justify-center space-x-2 rtl:space-x-reverse" onClick={onAcknowledge}>
                   <CheckCircle size={16} />
                   <span>{t('acknowledge')}</span>
                </button>
              )}
              {(alert.status === 'New' || alert.status === 'Acknowledged') && (
                <button className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded text-xs uppercase tracking-widest transition-all flex items-center justify-center space-x-2 rtl:space-x-reverse" onClick={onResolve}>
                   <CheckCircle size={16} />
                   <span>{t('resolve')}</span>
                </button>
              )}
              <button className="w-full py-3 bg-zinc-800 hover:bg-zinc-700 text-white font-bold rounded text-xs uppercase tracking-widest transition-all border border-zinc-700 flex items-center justify-center space-x-2 rtl:space-x-reverse" onClick={onEscalate}>
                 <FileText size={16} />
                 <span>{t('escalate')}</span>
              </button>
           </div>
           
           <div className="mt-8 border-t border-zinc-800 pt-6">
              <h4 className="text-[10px] font-bold text-zinc-600 uppercase mb-4 tracking-widest">Metadata</h4>
              <div className="space-y-2 text-[11px] font-mono text-zinc-500">
                 <div className="flex justify-between"><span>Frame ID:</span><span className="text-zinc-300">FR-{Math.floor(Math.random() * 99999)}-X</span></div>
                 <div className="flex justify-between"><span>Camera:</span><span className="text-zinc-300">{alert.camera}</span></div>
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
      setLoading(true);
      const data = await AlertsAPI.getAll();
      setAlerts(data);
    } catch (err) {
      console.error('Failed to fetch alerts:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  const filteredAlerts = useMemo(() => {
    return alerts.filter(alert => {
      const matchesSearch = searchQuery === '' ||
        alert.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        alert.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        alert.zone.toLowerCase().includes(searchQuery.toLowerCase()) ||
        alert.type.toLowerCase().includes(searchQuery.toLowerCase()) ||
        alert.camera.toLowerCase().includes(searchQuery.toLowerCase());
      
      const matchesSeverity = severityFilter === 'all' || alert.severity === severityFilter;
      const matchesType = typeFilter === 'all' || alert.type === typeFilter;
      
      return matchesSearch && matchesSeverity && matchesType;
    });
  }, [alerts, searchQuery, severityFilter, typeFilter]);

  const handleAcknowledge = async (alertId: string) => {
    await AlertsAPI.update(alertId, { status: 'Acknowledged' as Status });
    setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, status: 'Acknowledged' as Status } : a));
    setSelectedAlert(null);
  };

  const handleResolve = async (alertId: string) => {
    await AlertsAPI.update(alertId, { status: 'Resolved' as Status });
    setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, status: 'Resolved' as Status } : a));
    setSelectedAlert(null);
  };

  const handleDismiss = async (alertId: string) => {
    await AlertsAPI.update(alertId, { status: 'Dismissed' as Status });
    setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, status: 'Dismissed' as Status } : a));
  };

  const handleDelete = async (alertId: string) => {
    if (window.confirm(t('confirmDelete'))) {
      await AlertsAPI.delete(alertId);
      setAlerts(prev => prev.filter(a => a.id !== alertId));
    }
  };

  const handleExportCSV = () => {
    const headers = 'ID,Type,Severity,Zone,Camera,Timestamp,Status,Description';
    const rows = filteredAlerts.map(a => `"${a.id}","${a.type}","${a.severity}","${a.zone}","${a.camera}","${a.timestamp}","${a.status}","${a.description}"`).join('\n');
    const csvContent = `${headers}\n${rows}`;
    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'alerts_export.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  };

  const uniqueTypes = [...new Set(alerts.map(a => a.type))];

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto">
      {selectedAlert && (
        <AlertDetails 
          alert={selectedAlert} 
          onClose={() => setSelectedAlert(null)} 
          onAcknowledge={() => handleAcknowledge(selectedAlert.id)}
          onResolve={() => handleResolve(selectedAlert.id)}
          onEscalate={() => { setSelectedAlert(null); }}
        />
      )}
      <div className="flex flex-col sm:flex-row justify-between items-center gap-4">
        <div>
           <h2 className="text-2xl font-bold text-white">{t('alerts')}</h2>
           <p className="text-sm text-zinc-500">History of AI-detected safety violations.</p>
        </div>
        <div className="flex space-x-3 rtl:space-x-reverse">
           <div className="relative group">
             <Search className="absolute start-3 top-1/2 -translate-y-1/2 text-zinc-600 group-focus-within:text-vs-orange transition-colors" size={16} />
             <input 
               type="text" 
               placeholder={t('searchPlaceholder')} 
               value={searchQuery}
               onChange={(e) => setSearchQuery(e.target.value)}
               className="px-9 py-2 bg-[#0f0f11] border border-zinc-800 rounded text-sm text-white focus:outline-none focus:border-vs-orange transition-colors w-64 shadow-sm placeholder-zinc-600" 
             />
             {searchQuery && (
               <button onClick={() => setSearchQuery('')} className="absolute end-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-white">
                 <X size={14} />
               </button>
             )}
           </div>
           <button onClick={() => setShowFilters(!showFilters)} className={`flex items-center space-x-2 rtl:space-x-reverse px-4 py-2 bg-[#0f0f11] border rounded text-sm font-medium transition-colors ${showFilters ? 'border-vs-orange text-vs-orange' : 'border-zinc-800 text-zinc-300 hover:bg-zinc-800'}`}>
             <Filter size={16} />
             <span>{t('filter')}</span>
             {showFilters ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
           </button>
           <button onClick={handleExportCSV} className="flex items-center space-x-2 rtl:space-x-reverse px-4 py-2 bg-vs-orange text-black rounded text-sm font-bold shadow-glow hover:bg-vs-lightOrange transition-colors">
             <Download size={16} />
             <span>{t('exportCSV')}</span>
           </button>
        </div>
      </div>

      {/* Filter Panel */}
      {showFilters && (
        <div className="bg-[#0f0f11] border border-zinc-800 rounded-lg p-4 flex flex-wrap gap-4 items-center animate-in slide-in-from-top-2 duration-200">
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">{t('severity')}</label>
            <select 
              value={severityFilter} 
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="bg-[#050505] border border-zinc-800 text-zinc-300 text-sm rounded px-3 py-2 focus:outline-none focus:border-vs-orange"
            >
              <option value="all">{t('allSeverities')}</option>
              <option value="High">{t('high')}</option>
              <option value="Medium">{t('medium')}</option>
              <option value="Low">{t('low')}</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">{t('alertType')}</label>
            <select 
              value={typeFilter} 
              onChange={(e) => setTypeFilter(e.target.value)}
              className="bg-[#050505] border border-zinc-800 text-zinc-300 text-sm rounded px-3 py-2 focus:outline-none focus:border-vs-orange"
            >
              <option value="all">{t('allTypes')}</option>
              {uniqueTypes.map(type => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </div>
          {(severityFilter !== 'all' || typeFilter !== 'all') && (
            <button 
              onClick={() => { setSeverityFilter('all'); setTypeFilter('all'); }}
              className="mt-5 text-xs text-vs-orange hover:text-vs-lightOrange font-medium flex items-center space-x-1"
            >
              <X size={12} />
              <span>Clear Filters</span>
            </button>
          )}
        </div>
      )}

      <div className="bg-[#0f0f11] border border-zinc-800 rounded-lg overflow-hidden shadow-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-start text-sm text-zinc-400">
            <thead className="bg-zinc-900/50 text-zinc-500 uppercase text-[10px] font-bold tracking-wider border-b border-zinc-800">
              <tr>
                <th className="px-6 py-4 text-start">{t('id')}</th>
                <th className="px-6 py-4 text-start">{t('alertType')}</th>
                <th className="px-6 py-4 text-start">{t('severity')}</th>
                <th className="px-6 py-4 text-start">{t('location')}</th>
                <th className="px-6 py-4 text-start">{t('status')}</th>
                <th className="px-6 py-4 text-end">{t('action')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {filteredAlerts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-zinc-500">
                    <div className="flex flex-col items-center space-y-2">
                      <Search size={32} className="text-zinc-700" />
                      <p className="text-sm">{t('noResults')}</p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredAlerts.map((alert) => (
                <tr key={alert.id} onClick={() => setSelectedAlert(alert)} className="hover:bg-zinc-900/40 transition-colors cursor-pointer group">
                  <td className="px-6 py-4 font-mono font-medium text-white group-hover:text-vs-orange transition-colors">{alert.id}</td>
                  <td className="px-6 py-4">
                    <div className="flex items-center space-x-3 rtl:space-x-reverse">
                       <div className="w-12 h-12 rounded bg-black overflow-hidden border border-zinc-800">
                          <img src={alert.thumbnail} className="w-full h-full object-cover opacity-80" />
                       </div>
                       <span className="font-semibold text-zinc-200">{alert.type}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                     <span className={`font-bold text-[10px] uppercase px-2 py-0.5 rounded border ${alert.severity === 'High' ? 'text-red-500 bg-red-500/10 border-red-500/20' : alert.severity === 'Medium' ? 'text-vs-orange bg-vs-orange/10 border-vs-orange/20' : 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20'}`}>
                        {t(alert.severity.toLowerCase() as any)}
                     </span>
                  </td>
                  <td className="px-6 py-4 text-zinc-300">{alert.zone}</td>
                  <td className="px-6 py-4"><StatusPill status={alert.status} /></td>
                  <td className="px-6 py-4 text-end">
                    <div className="flex items-center justify-end space-x-1 rtl:space-x-reverse">
                      {alert.status === 'New' && (
                        <button className="p-1.5 hover:bg-emerald-500/10 rounded text-zinc-500 hover:text-emerald-400 transition-colors" title={t('acknowledge')} onClick={(e) => { e.stopPropagation(); handleAcknowledge(alert.id); }}>
                          <CheckCircle size={16} />
                        </button>
                      )}
                      {alert.status !== 'Dismissed' && alert.status !== 'Resolved' && (
                        <button className="p-1.5 hover:bg-zinc-800 rounded text-zinc-500 hover:text-zinc-300 transition-colors" title={t('dismissed')} onClick={(e) => { e.stopPropagation(); handleDismiss(alert.id); }}>
                          <X size={16} />
                        </button>
                      )}
                      <button className="p-1.5 hover:bg-red-500/10 rounded text-zinc-500 hover:text-red-400 transition-colors" title={t('delete')} onClick={(e) => { e.stopPropagation(); handleDelete(alert.id); }}>
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Alerts;
