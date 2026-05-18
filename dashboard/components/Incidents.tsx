
import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { 
  Plus, 
  Search, 
  FileText, 
  AlertTriangle, 
  Clock, 
  CheckCircle,
  ArrowRight,
  Download,
  X,
  CheckCircle2,
  Trash2
} from 'lucide-react';
import { Incident, Severity } from '../types';
import { useLanguage } from '../contexts/LanguageContext';
import { IncidentsAPI } from '../api';
import { Badge, Button, FieldRoot, PageShell, Panel, SelectField, TextAreaField, TextInput } from './ui';



const SeverityBadge = ({ severity }: { severity: Severity }) => {
  const tones = {
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

const Incidents = () => {
  const { t } = useLanguage();
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [zoneFilter, setZoneFilter] = useState('all');

  const fetchIncidents = useCallback(async () => {
    try {
      setLoading(true);
      const data = await IncidentsAPI.getAll();
      setIncidents(data);
    } catch (error) {
      console.error('Failed to fetch incidents:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIncidents();
  }, [fetchIncidents]);

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

  const activeCount = incidents.filter(i => i.severity === 'High').length;
  const resolvedCount = incidents.filter(i => i.severity === 'Low').length;

  const handleExport = () => {
    const headers = 'ID,Date,Zone,Severity,Category,Root Cause,Corrective Action';
    const rows = filteredIncidents.map(i => `"${i.id}","${i.createdAt}","${i.zone}","${i.severity}","${i.classification}","${i.rootCause}","${i.correctiveAction}"`).join('\n');
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

  const handleDelete = async (id: string) => {
    if (window.confirm(t('confirmDelete'))) {
      try {
        await IncidentsAPI.delete(id);
        setIncidents(prev => prev.filter(i => i.id !== id));
      } catch (e) {
        console.error('Failed to delete incident:', e);
      }
    }
  };

  return (
    <PageShell
      title={t('incidents')}
      description="Review and manage reported workplace incidents."
      actions={
        <>
          <Button onClick={handleExport} icon={<Download size={16} />}>{t('exportCSV')}</Button>
          <Button onClick={() => setShowAddModal(true)} variant="primary" icon={<Plus size={16} />}>{t('reportIncident')}</Button>
        </>
      }
    >

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard label="Active Cases" value={String(activeCount)} icon={AlertTriangle} colorClass="text-red-500" />
        <StatCard label="Avg. Resolution" value="4.2d" icon={Clock} colorClass="text-vs-orange" />
        <StatCard label="Total Reports" value={String(incidents.length)} icon={FileText} colorClass="text-blue-500" />
        <StatCard label="Resolved" value={String(resolvedCount)} icon={CheckCircle} colorClass="text-emerald-500" />
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
                <th className="px-6 py-4 text-start">{t('category')}</th>
                <th className="px-6 py-4 text-end">{t('action')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {filteredIncidents.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-zinc-500">
                    <div className="flex flex-col items-center space-y-2">
                      <Search size={32} className="text-zinc-700" />
                      <p className="text-sm">{t('noResults')}</p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredIncidents.map((incident) => (
                <tr key={incident.id} className="hover:bg-zinc-900/40 transition-colors group cursor-pointer">
                  <td className="px-6 py-4">
                    <span className="font-mono font-medium text-white group-hover:text-vs-orange transition-colors">{incident.id}</span>
                  </td>
                  <td className="px-6 py-4 font-mono text-xs">{incident.createdAt}</td>
                  <td className="px-6 py-4 text-zinc-300">{incident.zone}</td>
                  <td className="px-6 py-4"><SeverityBadge severity={incident.severity} /></td>
                  <td className="px-6 py-4">
                     <Badge>{incident.classification}</Badge>
                  </td>
                  <td className="px-6 py-4 text-end">
                    <div className="flex items-center justify-end space-x-1 rtl:space-x-reverse">
                      <button 
                        className="text-zinc-500 hover:text-red-400 transition-colors p-1.5 hover:bg-red-500/10 rounded"
                        title={t('delete')}
                        onClick={() => handleDelete(incident.id)}
                      >
                        <Trash2 size={16} />
                      </button>
                      <button className="text-zinc-500 hover:text-white transition-colors p-1 hover:bg-zinc-800 rounded">
                          <ArrowRight className="rtl:rotate-180" size={18} />
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
