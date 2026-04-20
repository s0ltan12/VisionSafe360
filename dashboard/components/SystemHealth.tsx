
import React from 'react';
import { Cpu, HardDrive, Wifi, Activity, Server, Thermometer } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

const NodeCard = ({ name, status, latency, cpu, uptime }: any) => {
  const { t } = useLanguage();
  return (
    <div className="bg-[#0f0f11] border border-zinc-800 rounded-xl p-5 hover:border-vs-orange/50 transition-all group">
       <div className="flex justify-between items-center mb-4">
          <div className="flex items-center space-x-3 rtl:space-x-reverse">
             <div className="p-2 bg-zinc-900 rounded-lg group-hover:text-vs-orange transition-colors">
                <Server size={20} />
             </div>
             <h4 className="font-bold text-white text-sm">{name}</h4>
          </div>
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${status === 'online' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500'}`}>
             {status}
          </span>
       </div>
       
       <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
             <p className="text-[10px] text-zinc-500 uppercase font-bold">{t('latency')}</p>
             <p className="text-sm font-mono text-zinc-300">{latency}ms</p>
          </div>
          <div>
             <p className="text-[10px] text-zinc-500 uppercase font-bold">{t('cpuUsage')}</p>
             <p className="text-sm font-mono text-zinc-300">{cpu}%</p>
          </div>
       </div>

       <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
          <div className="h-full bg-vs-orange transition-all duration-1000" style={{ width: `${cpu}%` }}></div>
       </div>
       <p className="mt-4 text-[10px] text-zinc-600 font-mono">{t('uptime')}: {uptime}</p>
    </div>
  );
};

const SystemHealth = () => {
  const { t } = useLanguage();

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto bg-[#050505]">
      <div className="flex justify-between items-center">
        <div>
           <h2 className="text-2xl font-bold text-white">{t('health')}</h2>
           <p className="text-sm text-zinc-500">Edge infrastructure and processing node metrics.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
         <div className="bg-[#0f0f11] p-5 rounded-xl border border-zinc-800 flex items-center space-x-4 rtl:space-x-reverse">
            <Wifi className="text-vs-orange" size={24} />
            <div>
               <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-widest">Network Load</p>
               <p className="text-xl font-bold text-white">42.8 Mbps</p>
            </div>
         </div>
         <div className="bg-[#0f0f11] p-5 rounded-xl border border-zinc-800 flex items-center space-x-4 rtl:space-x-reverse">
            <HardDrive className="text-vs-orange" size={24} />
            <div>
               <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-widest">Storage Used</p>
               <p className="text-xl font-bold text-white">1.2 TB / 4 TB</p>
            </div>
         </div>
         <div className="bg-[#0f0f11] p-5 rounded-xl border border-zinc-800 flex items-center space-x-4 rtl:space-x-reverse">
            <Thermometer className="text-emerald-500" size={24} />
            <div>
               <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-widest">Avg Temp</p>
               <p className="text-xl font-bold text-white">42°C</p>
            </div>
         </div>
         <div className="bg-[#0f0f11] p-5 rounded-xl border border-zinc-800 flex items-center space-x-4 rtl:space-x-reverse">
            <Activity className="text-vs-orange" size={24} />
            <div>
               <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-widest">Global FPS</p>
               <p className="text-xl font-bold text-white">24.2 fps</p>
            </div>
         </div>
      </div>

      <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mt-8 mb-4">{t('edgeNodes')}</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
         <NodeCard name="Edge-A-Production" status="online" latency="12" cpu="45" uptime="12d 4h" />
         <NodeCard name="Edge-B-Warehouse" status="online" latency="18" cpu="32" uptime="4d 21h" />
         <NodeCard name="Edge-C-Loading" status="online" latency="14" cpu="88" uptime="2d 12h" />
         <NodeCard name="Edge-D-Storage" status="offline" latency="--" cpu="--" uptime="0" />
      </div>
    </div>
  );
};

export default SystemHealth;
