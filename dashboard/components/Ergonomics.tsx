
import React from 'react';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  Legend
} from 'recharts';
import { UserCheck, Activity, Clock, AlertCircle, TrendingUp } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

const ergoData = [
  { name: 'Mon', score: 3.2, highRisk: 45 },
  { name: 'Tue', score: 3.5, highRisk: 52 },
  { name: 'Wed', score: 4.1, highRisk: 68 },
  { name: 'Thu', score: 3.8, highRisk: 55 },
  { name: 'Fri', score: 4.5, highRisk: 82 },
  { name: 'Sat', score: 2.1, highRisk: 12 },
  { name: 'Sun', score: 1.8, highRisk: 8 },
];

const zoneRisk = [
  { name: 'Assembly', value: 75 },
  { name: 'Welding', value: 88 },
  { name: 'Warehouse', value: 32 },
  { name: 'Packing', value: 48 },
];

const Ergonomics = () => {
  const { t, dir } = useLanguage();

  const handleExport = () => {
    const csvHeaders = 'Day,RULA Score,High Risk Events';
    const csvRows = ergoData.map(d => `${d.name},${d.score},${d.highRisk}`).join('\n');
    const csvContent = `${csvHeaders}\n${csvRows}`;
    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'ergonomics_report.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  };

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto bg-[#050505]">
      <div className="flex justify-between items-center">
        <div>
           <h2 className="text-2xl font-bold text-white">{t('ergonomics')}</h2>
           <p className="text-sm text-zinc-500">Postural analysis and skeletal risk factor monitoring.</p>
        </div>
        <button onClick={handleExport} className="px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-xs font-bold text-vs-orange uppercase tracking-wider hover:bg-zinc-800 transition-colors">
           {t('exportCSV')}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-[#0f0f11] p-5 rounded-xl border border-zinc-800">
           <div className="flex justify-between items-start mb-2">
              <UserCheck className="text-vs-orange" size={24} />
              <span className="text-[10px] font-mono text-emerald-400">+4.2%</span>
           </div>
           <p className="text-2xl font-bold text-white">4.2 / 7.0</p>
           <p className="text-xs text-zinc-500 uppercase tracking-widest">{t('rulaScore')}</p>
        </div>
        <div className="bg-[#0f0f11] p-5 rounded-xl border border-zinc-800">
           <div className="flex justify-between items-start mb-2">
              <Clock className="text-vs-orange" size={24} />
              <span className="text-[10px] font-mono text-red-500">+12m</span>
           </div>
           <p className="text-2xl font-bold text-white">124m</p>
           <p className="text-xs text-zinc-500 uppercase tracking-widest">{t('riskyDuration')}</p>
        </div>
        <div className="bg-[#0f0f11] p-5 rounded-xl border border-zinc-800">
           <div className="flex justify-between items-start mb-2">
              <AlertCircle className="text-red-500" size={24} />
              <span className="text-[10px] font-mono text-red-500">High</span>
           </div>
           <p className="text-2xl font-bold text-white">1,420</p>
           <p className="text-xs text-zinc-500 uppercase tracking-widest">{t('badPostures')}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#0f0f11] p-6 rounded-xl border border-zinc-800">
           <h3 className="font-bold text-white mb-6 uppercase text-xs tracking-widest">{t('ergoTrends')}</h3>
           <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                 <AreaChart data={ergoData}>
                    <defs>
                       <linearGradient id="ergoColor" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#FF6A00" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="#FF6A00" stopOpacity={0}/>
                       </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#262626"/>
                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#4b5563', fontSize: 10}} />
                    <YAxis axisLine={false} tickLine={false} tick={{fill: '#4b5563', fontSize: 10}} orientation={dir === 'rtl' ? 'right' : 'left'} />
                    <Tooltip contentStyle={{backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px'}} />
                    <Area type="monotone" dataKey="score" stroke="#FF6A00" fillOpacity={1} fill="url(#ergoColor)" strokeWidth={3} />
                 </AreaChart>
              </ResponsiveContainer>
           </div>
        </div>

        <div className="bg-[#0f0f11] p-6 rounded-xl border border-zinc-800">
           <h3 className="font-bold text-white mb-6 uppercase text-xs tracking-widest">{t('riskByZone')}</h3>
           <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                 <BarChart data={zoneRisk} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#262626"/>
                    <XAxis type="number" hide />
                    <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{fill: '#9CA3AF', fontSize: 10}} width={80} orientation={dir === 'rtl' ? 'right' : 'left'} />
                    <Tooltip contentStyle={{backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px'}} cursor={{fill: 'rgba(255,106,0,0.05)'}} />
                    <Bar dataKey="value" fill="#FF6A00" radius={[0, 4, 4, 0]} barSize={20}>
                       {zoneRisk.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.value > 60 ? '#ef4444' : '#FF6A00'} />
                       ))}
                    </Bar>
                 </BarChart>
              </ResponsiveContainer>
           </div>
        </div>
      </div>
    </div>
  );
};

export default Ergonomics;
