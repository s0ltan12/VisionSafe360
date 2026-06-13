
import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus, Camera, Activity, Trash2, Edit2, CheckCircle2, X,
  Play, Square, Wifi, WifiOff, Link, Loader2, Radio, Map,
  Upload, Video, Globe, FileVideo,
} from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';
import { CamerasAPI } from '../api';
import { Camera as CameraType, CameraSourceType } from '../types';
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

const SOURCE_TYPE_STYLES: Record<CameraSourceType, { label: string; Icon: any; cls: string }> = {
  rtsp:     { label: 'RTSP',     Icon: Wifi,      cls: 'text-sky-400 border-sky-500/30 bg-sky-500/10' },
  mediamtx: { label: 'MEDIAMTX', Icon: Radio,     cls: 'text-purple-400 border-purple-500/30 bg-purple-500/10' },
  file:     { label: 'FILE',     Icon: FileVideo, cls: 'text-amber-400 border-amber-500/30 bg-amber-500/10' },
  webcam:   { label: 'WEBCAM',   Icon: Video,     cls: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' },
  webrtc:   { label: 'WEBRTC',   Icon: Globe,     cls: 'text-zinc-400 border-zinc-500/30 bg-zinc-500/10' },
};

const resolveSourceType = (cam: CameraType): CameraSourceType => {
  if (cam.source_type) return cam.source_type;
  const url = cam.stream_url || '';
  if (url.startsWith('rtsp://')) return 'rtsp';
  if (url && !url.includes('://') && !/^\d+$/.test(url)) return 'file';
  if (/^\d+$/.test(url)) return 'webcam';
  return 'rtsp';
};

const SourceTypeBadge: React.FC<{ cam: CameraType }> = ({ cam }) => {
  if (!cam.stream_url && !cam.source_type) return null;
  const style = SOURCE_TYPE_STYLES[resolveSourceType(cam)];
  const Icon = style.Icon;
  return (
    <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded border font-mono ${style.cls}`}>
      <Icon size={9} />
      <span>{style.label}</span>
    </span>
  );
};

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
  const [formAreaName, setFormAreaName] = useState('Factory Hall');
  const [formZoneName, setFormZoneName] = useState('Production Line A');
  const [formLocationDescription, setFormLocationDescription] = useState('');
  const [sourceType, setSourceType] = useState<CameraSourceType>('rtsp');
  const [formRtspUrl, setFormRtspUrl] = useState('');
  const [formMediamtxPath, setFormMediamtxPath] = useState('');
  const [formDeviceIndex, setFormDeviceIndex] = useState<number>(0);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const resetForm = () => {
    setFormName('');
    setFormAreaName('Factory Hall');
    setFormZoneName('Production Line A');
    setFormLocationDescription('');
    setSourceType('rtsp');
    setFormRtspUrl('');
    setFormMediamtxPath('');
    setFormDeviceIndex(0);
    setUploadFile(null);
    setUploadProgress(0);
    setSubmitError(null);
    setSubmitting(false);
  };

  const closeAddModal = () => {
    setShowAddModal(false);
    resetForm();
  };

  const canSubmit = (() => {
    if (!formName.trim() || submitting) return false;
    switch (sourceType) {
      case 'rtsp':     return formRtspUrl.trim().startsWith('rtsp://');
      case 'mediamtx': return /^[a-zA-Z0-9_\-]+$/.test(formMediamtxPath.trim());
      case 'file':     return uploadFile !== null;
      case 'webcam':   return formDeviceIndex >= 0;
      case 'webrtc':   return false;
    }
    return false;
  })();

  const handleAddCamera = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      let created: CameraType;
      if (sourceType === 'file' && uploadFile) {
        created = await CamerasAPI.uploadAndCreate(
          {
            file: uploadFile,
            name: formName,
            areaName: formAreaName,
            zoneName: formZoneName,
            locationDescription: formLocationDescription || undefined,
          },
          setUploadProgress,
        );
      } else {
        const next: CameraType = {
          id: `CAM-${String(cameras.length + 1).padStart(2, '0')}`,
          name: formName,
          zone: `${formAreaName} / ${formZoneName}`,
          areaName: formAreaName,
          zoneName: formZoneName,
          locationDescription: formLocationDescription || undefined,
          source_type: sourceType,
          status: 'Online',
          isPrivacyMode: false,
          thumbnail: 'https://images.unsplash.com/photo-1557804506-669a67965ba0?q=80&w=800',
          fps: 30,
          health: 100,
        };
        if (sourceType === 'rtsp') {
          next.stream_url = formRtspUrl.trim();
        } else if (sourceType === 'mediamtx') {
          const path = formMediamtxPath.trim();
          next.mediamtxPath = path;
          next.stream_url = `rtsp://mediamtx:8554/${path}`;
        } else if (sourceType === 'webcam') {
          next.deviceIndex = formDeviceIndex;
          next.stream_url = String(formDeviceIndex);
        }
        created = await CamerasAPI.add(next);
      }
      setCameras(prev => [...prev, created]);
      setCardStates(prev => ({ ...prev, [created.id]: defaultCardState() }));
      closeAddModal();
    } catch (e: any) {
      setSubmitError(e?.message || 'Failed to add source');
    } finally {
      setSubmitting(false);
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
                    <SourceTypeBadge cam={cam} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add Source Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#0f0f11] border border-zinc-800 rounded-2xl w-full max-w-xl overflow-hidden shadow-2xl animate-in zoom-in-95 duration-200 max-h-[90vh] flex flex-col">
            <div className="p-6 border-b border-zinc-800 flex justify-between items-center shrink-0">
              <h3 className="text-lg font-bold text-white">{t('addSource')}</h3>
              <button onClick={closeAddModal} className="text-zinc-500 hover:text-white">
                <X size={24} />
              </button>
            </div>
            <div className="p-6 space-y-5 overflow-y-auto">
              {/* Source type segmented control */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-zinc-500 uppercase">{t('sourceType')}</label>
                <div className="grid grid-cols-5 gap-1 p-1 bg-zinc-950 border border-zinc-800 rounded-lg">
                  {([
                    { key: 'rtsp',     label: t('sourceTypeRtsp'),     Icon: Wifi },
                    { key: 'mediamtx', label: t('sourceTypeMediaMtx'), Icon: Radio },
                    { key: 'file',     label: t('sourceTypeFile'),     Icon: FileVideo },
                    { key: 'webcam',   label: t('sourceTypeWebcam'),   Icon: Video },
                    { key: 'webrtc',   label: t('sourceTypeWebRTC'),   Icon: Globe, disabled: true },
                  ] as { key: CameraSourceType; label: string; Icon: any; disabled?: boolean }[]).map(opt => {
                    const active = sourceType === opt.key && !opt.disabled;
                    return (
                      <button
                        key={opt.key}
                        type="button"
                        disabled={opt.disabled || submitting}
                        title={opt.disabled ? t('webRTCComingSoon') : ''}
                        onClick={() => !opt.disabled && setSourceType(opt.key)}
                        className={`flex flex-col items-center justify-center gap-1 py-2 px-1 rounded-md text-[10px] font-bold uppercase tracking-wider transition-colors ${
                          active
                            ? 'bg-vs-orange/20 text-vs-orange border border-vs-orange/40'
                            : opt.disabled
                              ? 'text-zinc-700 cursor-not-allowed'
                              : 'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900 border border-transparent'
                        }`}
                      >
                        <opt.Icon size={16} />
                        <span>{opt.label}</span>
                      </button>
                    );
                  })}
                </div>
                {sourceType === 'webrtc' && (
                  <p className="text-[10px] text-zinc-600">{t('webRTCComingSoon')}</p>
                )}
              </div>

              {/* Name + Area/Zone (always shown) */}
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

              {/* Conditional per-type fields */}
              {sourceType === 'rtsp' && (
                <div className="space-y-2">
                  <label className="text-xs font-bold text-zinc-500 uppercase flex items-center gap-2">
                    <Wifi size={11} /> RTSP URL
                  </label>
                  <input
                    type="text"
                    value={formRtspUrl}
                    onChange={e => setFormRtspUrl(e.target.value)}
                    className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none font-mono text-sm"
                    placeholder="rtsp://192.168.1.100:554/ch0"
                  />
                  <p className="text-[10px] text-zinc-600">The RTSP URL the AI worker will connect to for live detection.</p>
                </div>
              )}

              {sourceType === 'mediamtx' && (
                <div className="space-y-2">
                  <label className="text-xs font-bold text-zinc-500 uppercase flex items-center gap-2">
                    <Radio size={11} /> {t('mediamtxPath')}
                  </label>
                  <input
                    type="text"
                    value={formMediamtxPath}
                    onChange={e => setFormMediamtxPath(e.target.value)}
                    className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none font-mono text-sm"
                    placeholder="cam_01"
                  />
                  <p className="text-[10px] text-zinc-600">{t('mediamtxPathHelp')}</p>
                  <div className="text-[11px] font-mono text-zinc-500 bg-black/60 border border-zinc-900 rounded-md px-2 py-1.5">
                    rtsp://mediamtx:8554/{formMediamtxPath || '<path>'}
                  </div>
                </div>
              )}

              {sourceType === 'file' && (
                <div className="space-y-2">
                  <label className="text-xs font-bold text-zinc-500 uppercase flex items-center gap-2">
                    <FileVideo size={11} /> {t('uploadFile')}
                  </label>
                  <label className="flex flex-col items-center justify-center gap-2 py-6 bg-black border-2 border-dashed border-zinc-800 rounded-lg cursor-pointer hover:border-vs-orange/40 transition-colors">
                    <input
                      type="file"
                      accept="video/mp4,video/avi,video/quicktime,video/x-matroska"
                      className="hidden"
                      onChange={e => {
                        const file = e.target.files?.[0] || null;
                        setUploadFile(file);
                        setUploadProgress(0);
                      }}
                      disabled={submitting}
                    />
                    <Upload size={22} className="text-zinc-600" />
                    {uploadFile ? (
                      <div className="text-center">
                        <p className="text-sm font-mono text-white truncate max-w-xs">{uploadFile.name}</p>
                        <p className="text-[10px] text-zinc-600">{(uploadFile.size / (1024 * 1024)).toFixed(1)} MB</p>
                      </div>
                    ) : (
                      <>
                        <p className="text-sm text-zinc-400">{t('dropVideoHere')}</p>
                        <p className="text-[10px] text-zinc-600">{t('videoFileTypes')}</p>
                      </>
                    )}
                  </label>
                  {submitting && uploadFile && (
                    <div className="space-y-1">
                      <div className="h-1.5 bg-zinc-900 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-vs-orange transition-[width] duration-150"
                          style={{ width: `${uploadProgress}%` }}
                        />
                      </div>
                      <p className="text-[10px] text-zinc-500 text-end">{t('uploading')} · {uploadProgress}%</p>
                    </div>
                  )}
                </div>
              )}

              {sourceType === 'webcam' && (
                <div className="space-y-2">
                  <label className="text-xs font-bold text-zinc-500 uppercase flex items-center gap-2">
                    <Video size={11} /> {t('deviceIndex')}
                  </label>
                  <select
                    value={formDeviceIndex}
                    onChange={e => setFormDeviceIndex(Number(e.target.value))}
                    className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none font-mono text-sm"
                  >
                    {[0, 1, 2, 3].map(i => (
                      <option key={i} value={i}>/dev/video{i} (index {i})</option>
                    ))}
                  </select>
                  <p className="text-[10px] text-zinc-600">{t('deviceIndexHelp')}</p>
                </div>
              )}

              {sourceType === 'webrtc' && (
                <div className="rounded-lg border border-zinc-800 bg-black/40 p-4 text-center text-zinc-500">
                  <Globe size={22} className="mx-auto mb-2 text-zinc-700" />
                  <p className="text-sm">{t('webRTCComingSoon')}</p>
                </div>
              )}

              {submitError && (
                <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-md px-3 py-2">
                  {submitError}
                </div>
              )}
            </div>
            <div className="p-6 bg-zinc-900/30 flex justify-end space-x-3 rtl:space-x-reverse shrink-0 border-t border-zinc-800">
              <button onClick={closeAddModal} className="px-4 py-2 text-zinc-400 hover:text-white font-medium">{t('cancel')}</button>
              <button
                disabled={!canSubmit}
                className="px-6 py-2 bg-vs-orange text-black font-bold rounded-lg shadow-glow hover:bg-vs-lightOrange transition-colors flex items-center space-x-2 rtl:space-x-reverse disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={handleAddCamera}
              >
                {submitting ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle2 size={18} />}
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
