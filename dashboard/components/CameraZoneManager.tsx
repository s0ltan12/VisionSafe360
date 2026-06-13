import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  Eye,
  EyeOff,
  Loader2,
  Plus,
  Save,
  Trash2,
  X,
} from 'lucide-react';
import { SafetyZonesAPI } from '../api';
import {
  Camera,
  CameraSafetyZone,
  SafetyZoneEvent,
  SafetyZoneRule,
  SafetyZoneStats,
  SafetyZoneType,
  Severity,
  ZonePoint,
} from '../types';

const ZONE_TYPES: Array<{ value: SafetyZoneType; label: string }> = [
  { value: 'danger', label: 'Danger Zone' },
  { value: 'restricted', label: 'Restricted Area' },
  { value: 'forklift_only', label: 'Forklift Only' },
  { value: 'pedestrian_only', label: 'Pedestrian Only' },
  { value: 'no_entry', label: 'No Entry' },
  { value: 'loading', label: 'Loading Area' },
  { value: 'emergency_exit', label: 'Emergency Exit' },
  { value: 'custom', label: 'Custom' },
];

const DEFAULT_RULES: SafetyZoneRule = {
  allowedClasses: ['person', 'forklift'],
  deniedClasses: [],
  occupancyThreshold: null,
  dwellTimeLimitSec: null,
  cooldownSec: 30,
  minPersistenceSec: 0.5,
  severity: 'High',
};

const inputClass = 'w-full rounded-lg border border-zinc-800 bg-black px-3 py-2 text-sm text-white outline-none focus:border-vs-orange';

interface Props {
  camera: Camera;
  onClose: () => void;
}

const sourceWidth = 1280;
const sourceHeight = 720;

const emptyDraft = (cameraId: string): Partial<CameraSafetyZone> => ({
  cameraId,
  name: 'New Safety Zone',
  zoneType: 'danger',
  polygon: [],
  coordinateSpace: 'source_pixels',
  sourceWidth,
  sourceHeight,
  color: '#f97316',
  enabled: true,
  priority: 100,
  rules: DEFAULT_RULES,
});

const CameraZoneManager = ({ camera, onClose }: Props) => {
  const [zones, setZones] = useState<CameraSafetyZone[]>([]);
  const [events, setEvents] = useState<SafetyZoneEvent[]>([]);
  const [stats, setStats] = useState<SafetyZoneStats[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Partial<CameraSafetyZone>>(emptyDraft(camera.id));
  const [drawing, setDrawing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = useMemo(() => zones.find(zone => zone.id === selectedId) ?? null, [zones, selectedId]);
  const selectedStats = useMemo(() => stats.find(item => item.zoneId === selectedId) ?? null, [stats, selectedId]);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const [zoneRows, eventRows, statRows] = await Promise.all([
        SafetyZonesAPI.listForCamera(camera.id),
        SafetyZonesAPI.eventsForCamera(camera.id),
        SafetyZonesAPI.statsForCamera(camera.id),
      ]);
      setZones(zoneRows);
      setEvents(eventRows);
      setStats(statRows);
      if (!selectedId && zoneRows.length > 0) {
        setSelectedId(zoneRows[0].id);
        setDraft(zoneRows[0]);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load safety zones');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void refresh(); }, [camera.id]);

  useEffect(() => {
    if (selected) setDraft(selected);
  }, [selected?.id]);

  const startNewZone = () => {
    setSelectedId(null);
    setDraft(emptyDraft(camera.id));
    setDrawing(true);
  };

  const handleCanvasClick = (event: React.MouseEvent<SVGSVGElement>) => {
    if (!drawing) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * sourceWidth;
    const y = ((event.clientY - rect.top) / rect.height) * sourceHeight;
    setDraft(prev => ({ ...prev, polygon: [...(prev.polygon ?? []), { x, y }] }));
  };

  const removeLastPoint = () => {
    setDraft(prev => ({ ...prev, polygon: (prev.polygon ?? []).slice(0, -1) }));
  };

  const saveDraft = async () => {
    if (!draft.name || !draft.zoneType || !draft.polygon || draft.polygon.length < 3) {
      setError('A zone needs a name, type, and at least 3 polygon points.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = {
        ...draft,
        sourceWidth,
        sourceHeight,
        coordinateSpace: 'source_pixels',
        rules: draft.rules ?? DEFAULT_RULES,
      };
      const saved = draft.id
        ? await SafetyZonesAPI.update(draft.id, payload)
        : await SafetyZonesAPI.create(camera.id, payload);
      setSelectedId(saved.id);
      setDraft(saved);
      setDrawing(false);
      await refresh();
    } catch (err: any) {
      setError(err.message || 'Failed to save zone');
    } finally {
      setSaving(false);
    }
  };

  const deleteZone = async (zone: CameraSafetyZone) => {
    if (!window.confirm(`Delete ${zone.name}?`)) return;
    await SafetyZonesAPI.delete(zone.id);
    setSelectedId(null);
    setDraft(emptyDraft(camera.id));
    await refresh();
  };

  const toggleZone = async (zone: CameraSafetyZone) => {
    const updated = await SafetyZonesAPI.setEnabled(zone.id, !zone.enabled);
    setZones(prev => prev.map(item => item.id === updated.id ? updated : item));
    if (selectedId === updated.id) setDraft(updated);
  };

  const updateRules = (patch: Partial<SafetyZoneRule>) => {
    setDraft(prev => ({ ...prev, rules: { ...(prev.rules ?? DEFAULT_RULES), ...patch } }));
  };

  const polygonPoints = (points: ZonePoint[] = []) => points.map(point => `${point.x},${point.y}`).join(' ');

  return (
    <div className="p-6 h-full overflow-y-auto space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <button onClick={onClose} className="mb-3 inline-flex items-center gap-2 text-xs text-zinc-500 hover:text-white">
            <ChevronLeft size={14} /> Back to cameras
          </button>
          <h2 className="text-2xl font-bold text-white truncate">{camera.name} Safety Zones</h2>
          <p className="text-sm text-zinc-500">{camera.areaName || 'Area'} / {camera.zoneName || camera.zone}</p>
        </div>
        <button onClick={startNewZone} className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-vs-orange text-black rounded-lg text-sm font-bold hover:bg-vs-lightOrange">
          <Plus size={16} /> New Zone
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          <AlertTriangle size={15} /> {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24 text-vs-orange">
          <Loader2 className="animate-spin" size={30} />
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_380px] gap-5">
          <div className="space-y-4">
            <div className="relative aspect-video overflow-hidden rounded-xl border border-zinc-800 bg-black">
              {camera.thumbnail && (
                <img src={camera.thumbnail} alt={camera.name} className="absolute inset-0 h-full w-full object-cover opacity-60" />
              )}
              <svg
                viewBox={`0 0 ${sourceWidth} ${sourceHeight}`}
                className="absolute inset-0 h-full w-full cursor-crosshair"
                onClick={handleCanvasClick}
              >
                {zones.map(zone => (
                  <g key={zone.id} opacity={zone.enabled ? 1 : 0.35}>
                    <polygon
                      points={polygonPoints(zone.polygon)}
                      fill={`${zone.color}33`}
                      stroke={zone.color}
                      strokeWidth={selectedId === zone.id ? 5 : 3}
                    />
                    {zone.polygon.map((point, index) => (
                      <circle key={`${zone.id}-${index}`} cx={point.x} cy={point.y} r={7} fill={zone.color} />
                    ))}
                  </g>
                ))}
                {(draft.polygon?.length ?? 0) > 0 && (
                  <g>
                    <polyline
                      points={polygonPoints(draft.polygon)}
                      fill="none"
                      stroke={draft.color || '#f97316'}
                      strokeDasharray={drawing ? '12 8' : undefined}
                      strokeWidth={4}
                    />
                    {draft.polygon?.map((point, index) => (
                      <circle key={index} cx={point.x} cy={point.y} r={8} fill={draft.color || '#f97316'} />
                    ))}
                  </g>
                )}
              </svg>
              <div className="absolute bottom-3 left-3 flex gap-2">
                <button onClick={() => setDrawing(prev => !prev)} className="rounded-md bg-black/80 border border-zinc-700 px-3 py-1.5 text-xs font-bold text-zinc-200 hover:text-white">
                  {drawing ? 'Stop Drawing' : 'Draw Points'}
                </button>
                <button onClick={removeLastPoint} className="rounded-md bg-black/80 border border-zinc-700 px-3 py-1.5 text-xs font-bold text-zinc-400 hover:text-white">
                  Undo Point
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Metric label="Events" value={selectedStats?.eventCount ?? 0} />
              <Metric label="Violations" value={selectedStats?.violationCount ?? 0} />
              <Metric label="Occupancy" value={selectedStats?.currentOccupancy ?? 0} />
            </div>

            <div className="rounded-xl border border-zinc-800 bg-[#0f0f11] overflow-hidden">
              <div className="px-4 py-3 border-b border-zinc-800 text-sm font-bold text-white">Recent Zone Events</div>
              <div className="divide-y divide-zinc-900">
                {events.slice(0, 8).map(event => (
                  <div key={event.id} className="grid grid-cols-[1fr_auto] gap-3 px-4 py-3 text-sm">
                    <div>
                      <p className="text-zinc-200">{event.eventType.replaceAll('_', ' ')}</p>
                      <p className="text-xs text-zinc-500">{event.objectClass} · {event.occurredAt ? new Date(event.occurredAt).toLocaleString() : 'unknown time'}</p>
                    </div>
                    <span className="text-xs text-zinc-500">{event.severity}</span>
                  </div>
                ))}
                {events.length === 0 && <div className="px-4 py-8 text-sm text-zinc-600">No zone events yet.</div>}
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-zinc-800 bg-[#0f0f11]">
              <div className="px-4 py-3 border-b border-zinc-800 text-sm font-bold text-white">Zone List</div>
              <div className="max-h-64 overflow-y-auto">
                {zones.map(zone => (
                  <button
                    key={zone.id}
                    onClick={() => { setSelectedId(zone.id); setDrawing(false); }}
                    className={`w-full flex items-center gap-3 px-4 py-3 text-left border-b border-zinc-900 hover:bg-zinc-900/70 ${selectedId === zone.id ? 'bg-vs-orange/10' : ''}`}
                  >
                    <span className="h-3 w-3 rounded-full" style={{ backgroundColor: zone.color }} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-bold text-zinc-100">{zone.name}</span>
                      <span className="block text-xs text-zinc-500">{zone.zoneType.replaceAll('_', ' ')}</span>
                    </span>
                    {zone.enabled ? <Eye size={15} className="text-emerald-400" /> : <EyeOff size={15} className="text-zinc-600" />}
                  </button>
                ))}
                {zones.length === 0 && <div className="px-4 py-8 text-sm text-zinc-600">No zones configured.</div>}
              </div>
            </div>

            <div className="rounded-xl border border-zinc-800 bg-[#0f0f11] p-4 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-white">Zone Settings</h3>
                {draft.id && (
                  <button onClick={() => toggleZone(draft as CameraSafetyZone)} className="text-zinc-500 hover:text-white">
                    {draft.enabled ? <Eye size={17} /> : <EyeOff size={17} />}
                  </button>
                )}
              </div>
              <Field label="Name">
                <input value={draft.name ?? ''} onChange={e => setDraft(prev => ({ ...prev, name: e.target.value }))} className={inputClass} />
              </Field>
              <Field label="Type">
                <select value={draft.zoneType ?? 'danger'} onChange={e => setDraft(prev => ({ ...prev, zoneType: e.target.value as SafetyZoneType }))} className={inputClass}>
                  {ZONE_TYPES.map(type => <option key={type.value} value={type.value}>{type.label}</option>)}
                </select>
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Color">
                  <input type="color" value={draft.color ?? '#f97316'} onChange={e => setDraft(prev => ({ ...prev, color: e.target.value }))} className="h-10 w-full rounded bg-black border border-zinc-800" />
                </Field>
                <Field label="Severity">
                  <select value={draft.rules?.severity ?? 'High'} onChange={e => updateRules({ severity: e.target.value as Severity })} className={inputClass}>
                    {['Low', 'Medium', 'High', 'Critical'].map(level => <option key={level}>{level}</option>)}
                  </select>
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Occupancy">
                  <input type="number" value={draft.rules?.occupancyThreshold ?? ''} onChange={e => updateRules({ occupancyThreshold: e.target.value ? Number(e.target.value) : null })} className={inputClass} />
                </Field>
                <Field label="Dwell Sec">
                  <input type="number" value={draft.rules?.dwellTimeLimitSec ?? ''} onChange={e => updateRules({ dwellTimeLimitSec: e.target.value ? Number(e.target.value) : null })} className={inputClass} />
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Cooldown">
                  <input type="number" value={draft.rules?.cooldownSec ?? 30} onChange={e => updateRules({ cooldownSec: Number(e.target.value) })} className={inputClass} />
                </Field>
                <Field label="Priority">
                  <input type="number" value={draft.priority ?? 100} onChange={e => setDraft(prev => ({ ...prev, priority: Number(e.target.value) }))} className={inputClass} />
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <ClassToggle label="Allow People" checked={draft.rules?.allowedClasses?.includes('person') ?? true} onChange={checked => updateRules({ allowedClasses: toggleClass(draft.rules?.allowedClasses ?? [], 'person', checked) })} />
                <ClassToggle label="Allow Forklifts" checked={draft.rules?.allowedClasses?.includes('forklift') ?? true} onChange={checked => updateRules({ allowedClasses: toggleClass(draft.rules?.allowedClasses ?? [], 'forklift', checked) })} />
              </div>
              <div className="flex gap-2 pt-2">
                <button onClick={saveDraft} disabled={saving} className="flex-1 inline-flex items-center justify-center gap-2 rounded-lg bg-vs-orange px-4 py-2 text-sm font-bold text-black disabled:opacity-60">
                  {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />} Save
                </button>
                {draft.id && (
                  <button onClick={() => deleteZone(draft as CameraSafetyZone)} className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 text-red-300 hover:bg-red-500/20">
                    <Trash2 size={16} />
                  </button>
                )}
                <button onClick={() => { setDraft(emptyDraft(camera.id)); setSelectedId(null); setDrawing(false); }} className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 text-zinc-400 hover:text-white">
                  <X size={16} />
                </button>
              </div>
              <p className="text-[11px] text-zinc-600">{draft.polygon?.length ?? 0} polygon points, source space {sourceWidth}x{sourceHeight}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const Metric = ({ label, value }: { label: string; value: number }) => (
  <div className="rounded-xl border border-zinc-800 bg-[#0f0f11] px-4 py-3">
    <p className="text-xs uppercase tracking-wider text-zinc-600">{label}</p>
    <p className="mt-1 text-2xl font-bold text-white">{value}</p>
  </div>
);

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="block space-y-1">
    <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-600">{label}</span>
    {children}
  </label>
);

const ClassToggle = ({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) => (
  <button
    type="button"
    onClick={() => onChange(!checked)}
    className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-bold ${checked ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-zinc-800 bg-black text-zinc-500'}`}
  >
    {checked && <Check size={13} />} {label}
  </button>
);

function toggleClass(values: Array<'person' | 'forklift'>, item: 'person' | 'forklift', enabled: boolean) {
  const set = new Set(values);
  if (enabled) set.add(item);
  else set.delete(item);
  return Array.from(set);
}

export default CameraZoneManager;
