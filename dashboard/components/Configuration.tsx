import React, { useState } from 'react';
import { Save, Plus } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

const ToggleSwitch = ({ checked, onChange }: { checked: boolean, onChange: () => void }) => (
  <button 
    onClick={onChange}
    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-vs-orange focus:ring-offset-2 focus:ring-offset-[#141414] ${
      checked ? 'bg-vs-orange' : 'bg-zinc-700'
    }`}
  >
    <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
      checked ? 'translate-x-6 rtl:-translate-x-6' : 'translate-x-1 rtl:-translate-x-1'
    }`} />
  </button>
);

const InputGroup = ({ label, placeholder, defaultValue }: { label: string, placeholder?: string, defaultValue?: string }) => (
  <div className="space-y-1">
    <label className="block text-sm font-medium text-zinc-400">{label}</label>
    <input 
      type="text" 
      className="block w-full rounded border-zinc-800 bg-[#050505] border px-4 py-2 text-white focus:border-vs-orange focus:ring-1 focus:ring-vs-orange sm:text-sm shadow-sm placeholder-zinc-600 transition-colors"
      placeholder={placeholder}
      defaultValue={defaultValue}
    />
  </div>
);

const Configuration = () => {
  const [activeTab, setActiveTab] = useState('Sites & Zones');
  const [privacyMode, setPrivacyMode] = useState(true);
  const [notifications, setNotifications] = useState(true);
  const { t } = useLanguage();

  const tabs = [
    { key: 'Sites & Zones', label: t('sitesZones') },
    { key: 'Cameras', label: t('cameras') },
    { key: 'Policies', label: t('policies') },
    { key: 'Integrations', label: t('integrations') },
  ];

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <h2 className="text-2xl font-bold text-white">{t('systemConfiguration')}</h2>

      {/* Tabs */}
      <div className="border-b border-zinc-800">
        <nav className="-mb-px flex space-x-8 rtl:space-x-reverse">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`
                whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors
                ${activeTab === tab.key 
                  ? 'border-vs-orange text-vs-orange' 
                  : 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-700'}
              `}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="bg-[#0f0f11] rounded-xl shadow-sm border border-zinc-800 p-8 space-y-8">
        {/* Mock Content based on tab */}
        {activeTab === 'Sites & Zones' && (
           <div className="space-y-6">
             <div className="flex justify-between items-center">
               <h3 className="text-lg font-semibold text-white">{t('siteInfo')}</h3>
               <button className="flex items-center text-sm text-vs-orange font-medium hover:text-vs-lightOrange hover:underline">
                 <Plus size={16} className="me-1" /> {t('addNewSite')}
               </button>
             </div>
             
             <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
               <InputGroup label={t('siteName')} defaultValue="Factory Alpha - Main Floor" />
               <InputGroup label={t('locationCode')} defaultValue="NYC-FAC-01" />
               <InputGroup label={t('safetyManager')} defaultValue="Alex Morgan" />
               <InputGroup label={t('emergencyContact')} defaultValue="+1 (555) 012-3456" />
             </div>

             <div className="border-t border-zinc-800 pt-6">
               <h3 className="text-lg font-semibold text-white mb-4">{t('zoneConfigs')}</h3>
               <div className="space-y-4">
                  {[t('zoneA') + ' - Welding', t('zoneB') + ' - Forklift Lane', t('zoneC') + ' - Loading Dock'].map(zone => (
                    <div key={zone} className="flex items-center justify-between p-4 border border-zinc-800 rounded hover:border-vs-orange/50 transition-colors bg-zinc-900/30">
                      <div>
                        <p className="font-medium text-zinc-200">{zone}</p>
                        <p className="text-xs text-zinc-500">Active Cameras: 4 • Rules: PPE, Intrusion</p>
                      </div>
                      <button className="text-zinc-500 hover:text-vs-orange transition-colors">{t('edit')}</button>
                    </div>
                  ))}
               </div>
             </div>
           </div>
        )}

        {activeTab === 'Policies' && (
           <div className="space-y-6">
             <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="me-4">
                    <h4 className="font-medium text-zinc-200">{t('faceBlurring')}</h4>
                    <p className="text-sm text-zinc-500">{t('privacyDesc')}</p>
                  </div>
                  <ToggleSwitch checked={privacyMode} onChange={() => setPrivacyMode(!privacyMode)} />
                </div>
                <div className="border-t border-zinc-800 my-4"></div>
                <div className="flex items-center justify-between">
                  <div className="me-4">
                    <h4 className="font-medium text-zinc-200">{t('pushNotifications')}</h4>
                    <p className="text-sm text-zinc-500">{t('pushDesc')}</p>
                  </div>
                  <ToggleSwitch checked={notifications} onChange={() => setNotifications(!notifications)} />
                </div>
             </div>
           </div>
        )}



        {/* Action Footer */}
        <div className="pt-6 border-t border-zinc-800 flex justify-end">
          <button className="flex items-center space-x-2 rtl:space-x-reverse px-6 py-2.5 bg-vs-orange text-black font-bold rounded hover:bg-vs-lightOrange shadow-glow transition-colors">
            <Save size={18} />
            <span>{t('saveChanges')}</span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default Configuration;