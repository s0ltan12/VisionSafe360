
import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus, Camera, Activity, Trash2, Edit2, CheckCircle2, X,
  Play, Square, Wifi, WifiOff, Link, Loader2, Radio, Map,
} from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';
import { CamerasAPI } from '../api';
import { Camera as CameraType } from '../types';
import CameraZoneManager from './CameraZoneManager';

type StreamState = 'idle' | 'starting' | 'streaming' | 'stopping' | 'error';

interface CameraCardState {
  streamState: StreamState;
  editingUrl: boolean;
  pendingUrl: string;
  savingUrl: boolean;
  errorMsg: string | null;
}

const defaultCardState = (): CameraCardState => ({
  streamState: 'idle',
  editingUrl: false,
  pendingUrl: '',
  savingUrl: false,
  errorMsg: null,
});

const CameraManagement = () => {
  const { t } = useLanguage();
  const [cameras, setCameras] = useState<CameraType[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [cardStates, setCardStates] = useState<Record<string, CameraCardState>>({});
  const [zoneCamera, setZoneCamera] = useState<CameraType | null>(null);

  const fetchCameras = useCallback(async () => {
    try {
      setLoading(true);
      const data = await CamerasAPI.getAll();
      setCameras(data);
      // Initialize card states for new cameras
      setCardStates(prev => {
        const next = { ...prev };
        data.forEach(c => { if (!next[c.id]) next[c.id] = defaultCardState(); });
        return next;
      });
    } catch (e) {
      console.error('Failed to fetch cameras:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchCameras(); }, [fetchCameras]);

  const setCardField = (id: string, patch: Partial<CameraCardState>) => {
    setCardStates(prev => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  };

  // ── Form state ─────────────────────────────────────────────────────
  const [formName, setFormName] = useState('');
  const [formUrl, setFormUrl] = useState('');
  const [formStreamUrl, setFormStreamUrl] = useState('');
  const [formAreaName, setFormAreaName] = useState('Factory Hall');
  const [formZoneName, setFormZoneName] = useState('Production Line A');
  const [formLocationDescription, setFormLocationDescription] = useState('');

  const handleAddCamera = async () => {
    if (!formName.trim()) return;
    const newCamera: CameraType = {
      id: `CAM-${String(cameras.length + 1).padStart(2, '0')}`,
      name: formName,
      zone: `${formAreaName} / ${formZoneName}`,
      areaName: formAreaName,
      zoneName: formZoneName,
      locationDescription: formLocationDescription || undefined,
      url: formUrl || undefined,
      stream_url: formStreamUrl || undefined,
      status: 'Online',
      isPrivacyMode: false,
      thumbnail: 'https://images.unsplash.com/photo-1557804506-669a67965ba0?q=80&w=800',
      fps: 30,
      health: 100,
    };
    try {
      const created = await CamerasAPI.add(newCamera);
      setCameras(prev => [...prev, created]);
      setCardStates(prev => ({ ...prev, [created.id]: defaultCardState() }));
      setShowAddModal(false);
      setFormName(''); setFormUrl(''); setFormStreamUrl(''); setFormAreaName('Factory Hall'); setFormZoneName('Production Line A'); setFormLocationDescription('');
    } catch (e) {
      console.error('Failed to add camera:', e);
    }
  };

  const handleDeleteCamera = async (id: string) => {
    if (window.confirm(t('confirmDelete'))) {
      try {
        await CamerasAPI.delete(id);
        setCameras(prev => prev.filter(c => c.id !== id));
      } catch (e) { console.error('Failed to delete camera:', e); }
    }
  };

  const handleToggleStatus = async (id: string) => {
    const cam = cameras.find(c => c.id === id);
    if (!cam) return;
    const newStatus = cam.status === 'Online' ? 'Offline' : 'Online';
    try {
      const updated = await CamerasAPI.update(id, { status: newStatus });
      setCameras(prev => prev.map(c => c.id === id ? updated : c));
    } catch (e) { console.error('Failed to toggle camera status:', e); }
  };

  // ── Stream URL editing ─────────────────────────────────────────────
  const handleStartEditUrl = (cam: CameraType) => {
    setCardField(cam.id, { editingUrl: true, pendingUrl: cam.stream_url || '' });
  };

  const handleSaveUrl = async (cam: CameraType) => {
    const state = cardStates[cam.id];
    if (!state) return;
    setCardField(cam.id, { savingUrl: true });
    try {
      const updated = await CamerasAPI.update(cam.id, { stream_url: state.pendingUrl });
      setCameras(prev => prev.map(c => c.id === cam.id ? updated : c));
      setCardField(cam.id, { editingUrl: false, savingUrl: false, errorMsg: null });
    } catch (e: any) {
      setCardField(cam.id, { savingUrl: false, errorMsg: e.message || 'Save failed' });
    }
  };

  // ── Stream control ─────────────────────────────────────────────────
  const handleStartStream = async (cam: CameraType) => {
    setCardField(cam.id, { streamState: 'starting', errorMsg: null });
    try {
      await CamerasAPI.startStream(cam.id);
      setCardField(cam.id, { streamState: 'streaming' });
      setCameras(prev => prev.map(c => c.id === cam.id ? { ...c, status: 'Online' } : c));
    } catch (e: any) {
      setCardField(cam.id, { streamState: 'error', errorMsg: e.message || 'Failed to start stream' });
    }
  };

  const handleStopStream = async (cam: CameraType) => {
    setCardField(cam.id, { streamState: 'stopping', errorMsg: null });
    try {
      await CamerasAPI.stopStream(cam.id);
      setCardField(cam.id, { streamState: 'idle' });
    } catch (e: any) {
      setCardField(cam.id, { streamState: 'error', errorMsg: e.message || 'Failed to stop stream' });
    }
  };

  const getStreamBadge = (state: StreamState) => {
    switch (state) {
      case 'streaming':
        return <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 animate-pulse"><Radio size={8} />STREAMING</span>;
      case 'starting':
        return <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30"><Loader2 size={8} className="animate-spin" />STARTING</span>;
      case 'stopping':
        return <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-zinc-500/20 text-zinc-400 border border-zinc-500/30"><Loader2 size={8} className="animate-spin" />STOPPING</span>;
      case 'error':
        return <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">ERROR</span>;
      default:
        return <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-zinc-800 text-zinc-500 border border-zinc-700">IDLE</span>;
    }
  };

  if (zoneCamera) {
    return <CameraZoneManager camera={zoneCamera} onClose={() => setZoneCamera(null)} />;
  }

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-white">{t('cameras')}</h2>
          <p className="text-sm text-zinc-500">Configure RTSP streams and AI detection sources.</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center space-x-2 rtl:space-x-reverse px-4 py-2 bg-vs-orange text-black rounded-lg hover:bg-vs-lightOrange text-sm font-bold shadow-glow transition-colors"
        >
          <Plus size={18} />
          <span>{t('addCamera')}</span>
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={32} className="animate-spin text-vs-orange" />
        </div>
      ) : cameras.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
          <Camera size={48} className="mb-4 text-zinc-700" />
          <p className="text-sm">{t('noResults')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {cameras.map((cam) => {
            const cs = cardStates[cam.id] || defaultCardState();
            return (
              <div key={cam.id} className="bg-[#0f0f11] border border-zinc-800 rounded-xl overflow-hidden group hover:border-vs-orange/50 transition-all">
                {/* Thumbnail */}
                <div className="aspect-video bg-black relative">
                  {cam.thumbnail ? (
                    <img src={cam.thumbnail} alt={cam.name} className="w-full h-full object-cover opacity-60 group-hover:opacity-80 transition-opacity" />
                  ) : (
                    <div className="absolute inset-0 flex items-center justify-center">
                      <Camera className="text-zinc-800" size={48} />
                    </div>
                  )}
                  <div className="absolute top-3 start-3 px-2 py-1 bg-black/70 backdrop-blur rounded text-[10px] font-mono text-zinc-300 border border-white/10">
                    {cam.id}
                  </div>
                  <button
                    onClick={() => handleToggleStatus(cam.id)}
                    className={`absolute top-3 end-3 flex items-center space-x-1 rtl:space-x-reverse px-2 py-1 rounded text-[10px] font-bold uppercase cursor-pointer hover:opacity-80 transition-opacity ${cam.status === 'Online' ? 'bg-emerald-500/20 text-emerald-500 border border-emerald-500/30' : 'bg-red-500/20 text-red-500 border border-red-500/30'}`}
                  >
                    <Activity size={10} />
                    <span>{t(cam.status.toLowerCase() as any)}</span>
                  </button>
                  {/* Stream state badge overlay */}
                  {cs.streamState !== 'idle' && (
                    <div className="absolute bottom-2 start-2">
                      {getStreamBadge(cs.streamState)}
                    </div>
                  )}
                </div>

                {/* Info */}
                <div className="p-5 space-y-4">
                  <div>
                    <h3 className="text-white font-bold">{cam.name}</h3>
                    <p className="text-xs text-zinc-500 uppercase tracking-wider">{cam.areaName || 'Area'} / {cam.zoneName || cam.zone}</p>
                    {cam.locationDescription && (
                      <p className="text-[11px] text-zinc-600 mt-1">{cam.locationDescription}</p>
                    )}
                  </div>

                  {/* RTSP URL display / editor */}
                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-zinc-600 uppercase tracking-wider flex items-center gap-1">
                      <Link size={9} />RTSP Stream URL
                    </label>
                    {cs.editingUrl ? (
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={cs.pendingUrl}
                          onChange={e => setCardField(cam.id, { pendingUrl: e.target.value })}
                          className="flex-1 bg-black border border-vs-orange/50 rounded px-2 py-1 text-xs text-white outline-none font-mono"
                          placeholder="rtsp://host:8554/path"
                          autoFocus
                        />
                        <button
                          onClick={() => handleSaveUrl(cam)}
                          disabled={cs.savingUrl}
                          className="px-2 py-1 bg-vs-orange text-black rounded text-xs font-bold disabled:opacity-50"
                        >
                          {cs.savingUrl ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
                        </button>
                        <button
                          onClick={() => setCardField(cam.id, { editingUrl: false })}
                          className="px-2 py-1 bg-zinc-800 text-zinc-400 rounded text-xs"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <span className="flex-1 text-xs font-mono text-zinc-400 truncate bg-black/40 border border-zinc-800 rounded px-2 py-1">
                          {cam.stream_url || <span className="text-zinc-600 italic">not configured</span>}
                        </span>
                        <button
                          onClick={() => handleStartEditUrl(cam)}
                          className="p-1 text-zinc-500 hover:text-vs-orange transition-colors"
                          title="Edit stream URL"
                        >
                          <Edit2 size={12} />
                        </button>
                      </div>
                    )}
                    {cs.errorMsg && (
                      <p className="text-[10px] text-red-400">{cs.errorMsg}</p>
                    )}
                  </div>

                  {/* Stream Controls */}
                  <div className="grid grid-cols-[1fr_auto] gap-2">
                    {cs.streamState === 'streaming' ? (
                      <button
                        onClick={() => handleStopStream(cam)}
                        disabled={cs.streamState === 'stopping'}
                        className="flex-1 flex items-center justify-center gap-2 py-2 bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg text-xs font-bold hover:bg-red-500/20 transition-colors disabled:opacity-50"
                      >
                        <Square size={13} />
                        Stop Stream
                      </button>
                    ) : (
                      <button
                        onClick={() => handleStartStream(cam)}
                        disabled={!cam.stream_url || cs.streamState === 'starting'}
                        className="flex-1 flex items-center justify-center gap-2 py-2 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-lg text-xs font-bold hover:bg-emerald-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        title={!cam.stream_url ? 'Set a stream URL first' : 'Start AI stream'}
                      >
                        {cs.streamState === 'starting' ? (
                          <Loader2 size={13} className="animate-spin" />
                        ) : (
                          <Play size={13} />
                        )}
                        Start Stream
                      </button>
                    )}
                    <button
                      className="p-2 bg-zinc-900 border border-zinc-800 rounded-lg text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors"
                      onClick={() => handleDeleteCamera(cam.id)}
                      title="Delete camera"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>

                  <button
                    className="w-full flex items-center justify-center gap-2 py-2 bg-vs-orange/10 border border-vs-orange/30 text-vs-orange rounded-lg text-xs font-bold hover:bg-vs-orange/20 transition-colors"
                    onClick={() => setZoneCamera(cam)}
                    title="Manage Safety Zones"
                  >
                    <Map size={14} />
                    Manage Safety Zones
                  </button>

                  {/* Stream state badge (below controls) */}
                  <div className="flex items-center justify-between text-[10px] text-zinc-600">
                    {getStreamBadge(cs.streamState)}
                    {cam.stream_url && (
                      <span className="flex items-center gap-1">
                        {cam.stream_url.startsWith('rtsp://') ? (
                          <><Wifi size={9} className="text-zinc-500" /><span>RTSP</span></>
                        ) : (
                          <><WifiOff size={9} /><span>Unknown</span></>
                        )}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add Camera Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#0f0f11] border border-zinc-800 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="p-6 border-b border-zinc-800 flex justify-between items-center">
              <h3 className="text-lg font-bold text-white">{t('addCamera')}</h3>
              <button onClick={() => setShowAddModal(false)} className="text-zinc-500 hover:text-white">
                <X size={24} />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div className="space-y-2">
                <label className="text-xs font-bold text-zinc-500 uppercase">{t('cameraName')} *</label>
                <input
                  type="text"
                  value={formName}
                  onChange={e => setFormName(e.target.value)}
                  className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none"
                  placeholder="e.g. Loading Dock North"
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-bold text-zinc-500 uppercase">RTSP Stream URL (AI Detection)</label>
                <input
                  type="text"
                  value={formStreamUrl}
                  onChange={e => setFormStreamUrl(e.target.value)}
                  className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none font-mono text-sm"
                  placeholder="rtsp://192.168.1.100:554/ch0"
                />
                <p className="text-[10px] text-zinc-600">The RTSP URL the AI worker will connect to for live detection.</p>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-bold text-zinc-500 uppercase">{t('rtspUrl')} (Display)</label>
                <input
                  type="text"
                  value={formUrl}
                  onChange={e => setFormUrl(e.target.value)}
                  className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none"
                  placeholder="Optional display URL"
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-bold text-zinc-500 uppercase">{t('location')}</label>
                <div className="grid grid-cols-2 gap-3">
                  <input
                    type="text"
                    value={formAreaName}
                    onChange={e => setFormAreaName(e.target.value)}
                    className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none"
                    placeholder="Factory Hall"
                  />
                  <input
                    type="text"
                    value={formZoneName}
                    onChange={e => setFormZoneName(e.target.value)}
                    className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none"
                    placeholder="Production Line A"
                  />
                </div>
                <p className="text-[10px] text-zinc-600">Area and zone appear on alerts and camera cards.</p>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-bold text-zinc-500 uppercase">Location Description</label>
                <input
                  type="text"
                  value={formLocationDescription}
                  onChange={e => setFormLocationDescription(e.target.value)}
                  className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none"
                  placeholder="Mounted above conveyor entrance, facing worker lane"
                />
              </div>
            </div>
            <div className="p-6 bg-zinc-900/30 flex justify-end space-x-3 rtl:space-x-reverse">
              <button onClick={() => setShowAddModal(false)} className="px-4 py-2 text-zinc-400 hover:text-white font-medium">{t('cancel')}</button>
              <button
                disabled={!formName.trim()}
                className="px-6 py-2 bg-vs-orange text-black font-bold rounded-lg shadow-glow hover:bg-vs-lightOrange transition-colors flex items-center space-x-2 rtl:space-x-reverse disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={handleAddCamera}
              >
                <CheckCircle2 size={18} />
                <span>{t('saveChanges')}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CameraManagement;
