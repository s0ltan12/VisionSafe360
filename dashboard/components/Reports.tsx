
import React, { useState } from 'react';
import { 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer, 
  PieChart, 
  Pie, 
  Cell,
  Legend,
  AreaChart,
  Area
} from 'recharts';
import { Download, Calendar, TrendingUp, ShieldAlert, Activity, UserCheck, CheckCircle2 } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

const KPICard = ({ label, value, trend, icon: Icon }: any) => {
  return (
    <div className="bg-[#0f0f11] p-5 rounded-xl border border-zinc-800 hover:border-zinc-700 transition-colors">
       <div className="flex justify-between items-start mb-4">
          <div className="p-2 bg-zinc-900 rounded-lg border border-zinc-800 text-vs-orange">
             <Icon size={20} />
          </div>
          {trend && (
             <div className="text-[10px] font-bold text-emerald-400 flex items-center space-x-1 rtl:space-x-reverse">
                <TrendingUp size={12} />
                <span>{trend}</span>
             </div>
          )}
       </div>
       <p className="text-2xl font-bold text-white mb-1">{value}</p>
       <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-widest">{label}</p>
    </div>
  )
}

const Reports = () => {
  const { t, dir } = useLanguage();
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = () => {
    setIsExporting(true);
    setTimeout(() => {
      const csvHeaders = 'Day,Alerts,Safety Score';
      const csvRows = trendData.map(d => `${d.name},${d.alerts},${d.score}`).join('\n');
      const csvContent = `${csvHeaders}\n${csvRows}`;
      const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'safety_analytics_report.csv';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(link.href);
      setIsExporting(false);
    }, 1000);
  };

  const trendData = [
    { name: 'Mon', alerts: 24, score: 92 },
    { name: 'Tue', alerts: 18, score: 94 },
    { name: 'Wed', alerts: 32, score: 89 },
    { name: 'Thu', alerts: 28, score: 91 },
    { name: 'Fri', alerts: 45, score: 85 },
    { name: 'Sat', alerts: 10, score: 96 },
    { name: 'Sun', alerts: 5, score: 98 },
  ];

  const hazardData = [
    { name: 'PPE Compliance', value: 45 },
    { name: 'Restricted Zones', value: 25 },
    { name: 'Falls', value: 15 },
    { name: 'Other', value: 15 },
  ];

  const COLORS = ['#FF6A00', '#FF8A3A', '#3b82f6', '#4b5563'];

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto">
      <div className="flex flex-col sm:flex-row justify-between items-center gap-4">
        <div>
           <h2 className="text-2xl font-bold text-white">{t('reports')}</h2>
           <p className="text-sm text-zinc-500">Global safety trends and AI performance analytics.</p>
        </div>
        <div className="flex space-x-3 rtl:space-x-reverse">
          <button onClick={() => alert('Opening range selector...')} className="flex items-center space-x-2 rtl:space-x-reverse px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-300 hover:bg-zinc-800 text-sm transition-colors uppercase text-xs font-bold tracking-wider">
            <Calendar size={18} />
            <span>Last 7 Days</span>
          </button>
          <button 
            disabled={isExporting}
            onClick={handleExport} 
            className="flex items-center space-x-2 rtl:space-x-reverse px-4 py-2 bg-vs-orange text-black rounded-lg hover:bg-vs-lightOrange text-sm font-bold shadow-glow transition-all disabled:opacity-50 uppercase text-xs tracking-wider"
          >
            {isExporting ? <Activity size={18} className="animate-spin" /> : <Download size={18} />}
            <span>{isExporting ? 'Generating...' : t('exportCSV')}</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
         <KPICard label="Total Incidents" value="162" trend="+12%" icon={ShieldAlert} />
         <KPICard label="Safety Score" value="92.4%" trend="+1.2%" icon={UserCheck} />
         <KPICard label="Falls Detected" value="8" trend="-2" icon={Activity} />
         <KPICard label="Active Alerts" value="14" icon={ShieldAlert} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-[#0f0f11] p-6 rounded-xl border border-zinc-800">
          <h3 className="font-bold text-white mb-6 uppercase text-[10px] tracking-widest opacity-60">Weekly Incident Trend</h3>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendData}>
                <defs>
                  <linearGradient id="colorAlerts" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#FF6A00" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#FF6A00" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#262626"/>
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#4b5563', fontSize: 10}} />
                <YAxis axisLine={false} tickLine={false} tick={{fill: '#4b5563', fontSize: 10}} orientation={dir === 'rtl' ? 'right' : 'left'} />
                <Tooltip contentStyle={{backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px'}} />
                <Area type="monotone" dataKey="alerts" stroke="#FF6A00" fillOpacity={1} fill="url(#colorAlerts)" strokeWidth={3} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-[#0f0f11] p-6 rounded-xl border border-zinc-800">
          <h3 className="font-bold text-white mb-6 uppercase text-[10px] tracking-widest opacity-60">Violation Distribution</h3>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={hazardData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={8}
                  dataKey="value"
                >
                  {hazardData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{backgroundColor: '#0a0a0a', border: '1px solid #262626', borderRadius: '8px'}} />
                <Legend verticalAlign="bottom" height={36} wrapperStyle={{fontSize: '11px'}}/>
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Reports;
