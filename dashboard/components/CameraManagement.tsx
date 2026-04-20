
import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Camera, Globe, Activity, Trash2, Edit2, Target, CheckCircle2, X } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';
import { CamerasAPI } from '../api';
import { Camera as CameraType } from '../types';

const CameraManagement = () => {
  const { t } = useLanguage();
  const [cameras, setCameras] = useState<CameraType[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);

  const fetchCameras = useCallback(async () => {
    try {
      setLoading(true);
      const data = await CamerasAPI.getAll();
      setCameras(data);
    } catch (e) {
      console.error('Failed to fetch cameras:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCameras();
  }, [fetchCameras]);
  
  // Form state
  const [formName, setFormName] = useState('');
  const [formUrl, setFormUrl] = useState('');
  const [formZone, setFormZone] = useState('Zone A');

  const handleAddCamera = async () => {
    if (!formName.trim()) return;
    const newCamera: CameraType = {
      id: `CAM-${String(cameras.length + 1).padStart(2, '0')}`,
      name: formName,
      zone: formZone,
      url: formUrl || undefined,
      status: 'Online',
      isPrivacyMode: false,
      thumbnail: 'https://images.unsplash.com/photo-1557804506-669a67965ba0?q=80&w=800',
      fps: 30,
      health: 100,
    };
    try {
      const created = await CamerasAPI.add(newCamera);
      setCameras(prev => [...prev, created]);
      setShowAddModal(false);
      setFormName('');
      setFormUrl('');
      setFormZone('Zone A');
    } catch (e) {
      console.error('Failed to add camera:', e);
    }
  };

  const handleDeleteCamera = async (id: string) => {
    if (window.confirm(t('confirmDelete'))) {
      try {
        await CamerasAPI.delete(id);
        setCameras(prev => prev.filter(c => c.id !== id));
      } catch (e) {
        console.error('Failed to delete camera:', e);
      }
    }
  };

  const handleToggleStatus = async (id: string) => {
    const cam = cameras.find(c => c.id === id);
    if (!cam) return;
    const newStatus = cam.status === 'Online' ? 'Offline' : 'Online';
    try {
      const updated = await CamerasAPI.update(id, { status: newStatus });
      setCameras(prev => prev.map(c => c.id === id ? updated : c));
    } catch (e) {
      console.error('Failed to toggle camera status:', e);
    }
  };

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto">
      <div className="flex justify-between items-center">
        <div>
           <h2 className="text-2xl font-bold text-white">{t('cameras')}</h2>
           <p className="text-sm text-zinc-500">Configure factory IP streams and detection zones.</p>
        </div>
        <button 
           onClick={() => setShowAddModal(true)}
           className="flex items-center space-x-2 rtl:space-x-reverse px-4 py-2 bg-vs-orange text-black rounded-lg hover:bg-vs-lightOrange text-sm font-bold shadow-glow transition-colors"
        >
            <Plus size={18} />
            <span>{t('addCamera')}</span>
        </button>
      </div>

      {cameras.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
          <Camera size={48} className="mb-4 text-zinc-700" />
          <p className="text-sm">{t('noResults')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {cameras.map((cam) => (
            <div key={cam.id} className="bg-[#0f0f11] border border-zinc-800 rounded-xl overflow-hidden group hover:border-vs-orange/50 transition-all">
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
               </div>
               
               <div className="p-5 space-y-4">
                  <div>
                     <h3 className="text-white font-bold">{cam.name}</h3>
                     <p className="text-xs text-zinc-500 uppercase tracking-wider">{cam.zone}</p>
                  </div>
                  
                  <div className="grid grid-cols-3 gap-2">
                     <button className="flex items-center justify-center space-x-1 rtl:space-x-reverse p-2 bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-400 hover:text-white transition-colors" onClick={() => window.alert('ROI Editor active')}>
                        <Target size={14} />
                        <span>{t('editRoi')}</span>
                     </button>
                     <button className="flex items-center justify-center space-x-1 rtl:space-x-reverse p-2 bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-400 hover:text-white transition-colors" onClick={() => window.alert('Editing camera config...')}>
                        <Edit2 size={14} />
                        <span>{t('edit')}</span>
                     </button>
                     <button 
                       className="flex items-center justify-center space-x-1 rtl:space-x-reverse p-2 bg-zinc-900 border border-zinc-800 rounded text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors"
                       onClick={() => handleDeleteCamera(cam.id)}
                     >
                        <Trash2 size={14} />
                        <span>{t('delete')}</span>
                     </button>
                  </div>
               </div>
            </div>
          ))}
        </div>
      )}

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
                      onChange={(e) => setFormName(e.target.value)}
                      className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none" 
                      placeholder="e.g. Loading Dock North" 
                    />
                 </div>
                 <div className="space-y-2">
                    <label className="text-xs font-bold text-zinc-500 uppercase">{t('rtspUrl')}</label>
                    <input 
                      type="text" 
                      value={formUrl}
                      onChange={(e) => setFormUrl(e.target.value)}
                      className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none" 
                      placeholder="rtsp://192.168.1.100:554/ch0" 
                    />
                 </div>
                 <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                       <label className="text-xs font-bold text-zinc-500 uppercase">{t('location')}</label>
                       <select 
                         value={formZone}
                         onChange={(e) => setFormZone(e.target.value)}
                         className="w-full bg-black border border-zinc-800 rounded-lg p-3 text-white focus:border-vs-orange outline-none"
                       >
                          <option>{t('zoneA')}</option>
                          <option>{t('zoneB')}</option>
                          <option>{t('zoneC')}</option>
                          <option>{t('zoneD')}</option>
                       </select>
                    </div>
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
