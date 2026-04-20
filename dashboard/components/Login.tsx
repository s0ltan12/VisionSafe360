
import React, { useState } from 'react';
import { User, Lock, AlertCircle, ArrowRight } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';
import VisionSafeLogo from './VisionSafeLogo';
import { UserRole } from '../types';
import { AuthAPI, setAuthToken } from '../api';

interface LoginProps {
   onLogin: (user: {name: string, role: UserRole}, token: string) => void;
}

const Login: React.FC<LoginProps> = ({ onLogin }) => {
  const { t, dir } = useLanguage();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

   const resolveCredentials = (value: string) => {
      const lower = value.toLowerCase().trim();
      if (lower === 'admin') return { email: 'alex.m@visionsafe.co' };
      if (lower === 'safety') return { email: 'sarah.c@visionsafe.co' };
      if (lower === 'analyst') return { email: 'analyst@visionsafe.co' };
      return { email: value.trim() };
   };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

      const { email } = resolveCredentials(username);

      AuthAPI.login(email, password)
         .then((result) => {
            setAuthToken(result.access_token);
            return AuthAPI.me().then((user) => ({ user, token: result.access_token }));
         })
         .then(({ user, token }) => {
            onLogin({ name: user.name, role: user.role }, token);
         })
         .catch(() => {
            setAuthToken(null);
            setError('Invalid credentials. Use the seeded demo accounts or a valid email/password pair.');
         })
         .finally(() => setLoading(false));
  };

  return (
    <div dir={dir} className="min-h-screen bg-[#050505] flex items-center justify-center p-6 font-sans">
      <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-20">
         <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-vs-orange blur-[120px] rounded-full opacity-30"></div>
         <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-blue-900 blur-[120px] rounded-full opacity-20"></div>
      </div>

      <div className="w-full max-w-md z-10 animate-in fade-in slide-in-from-bottom-8 duration-700">
        <div className="flex flex-col items-center mb-8">
           <VisionSafeLogo className="w-24 h-24 mb-4" />
           <h1 className="text-2xl font-bold text-white tracking-tight uppercase">VisionSafe <span className="text-vs-orange">360</span></h1>
           <p className="text-zinc-500 text-sm mt-1">Industrial Intelligence & Safety Monitoring</p>
        </div>

        <div className="bg-[#0f0f11] border border-zinc-800 rounded-2xl p-8 shadow-2xl backdrop-blur-md">
           <form onSubmit={handleSubmit} className="space-y-6">
              {error && (
                <div className="bg-red-500/10 border border-red-500/50 p-3 rounded-lg flex items-center space-x-3 rtl:space-x-reverse text-red-500 text-[11px] animate-shake">
                   <AlertCircle size={18} />
                   <span>{error}</span>
                </div>
              )}

              <div className="space-y-2">
                 <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Username</label>
                 <div className="relative">
                    <User className="absolute start-3 top-1/2 -translate-y-1/2 text-zinc-600" size={18} />
                    <input 
                       type="text" 
                       required
                       value={username}
                       onChange={(e) => setUsername(e.target.value)}
                       className="w-full bg-black border border-zinc-800 rounded-xl py-3 ps-10 pe-4 text-white focus:outline-none focus:border-vs-orange transition-all placeholder-zinc-800 text-sm"
                       placeholder="e.g. admin or email"
                    />
                 </div>
              </div>

              <div className="space-y-2">
                 <label className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Password</label>
                 <div className="relative">
                    <Lock className="absolute start-3 top-1/2 -translate-y-1/2 text-zinc-600" size={18} />
                    <input 
                       type="password" 
                       required
                       value={password}
                       onChange={(e) => setPassword(e.target.value)}
                       className="w-full bg-black border border-zinc-800 rounded-xl py-3 ps-10 pe-4 text-white focus:outline-none focus:border-vs-orange transition-all placeholder-zinc-800 text-sm"
                       placeholder="Demo password"
                    />
                 </div>
              </div>

              <button 
                 type="submit" 
                 disabled={loading}
                 className="w-full bg-vs-orange hover:bg-vs-lightOrange text-black font-bold py-3.5 rounded-xl transition-all shadow-glow flex items-center justify-center space-x-2 rtl:space-x-reverse group disabled:opacity-50 uppercase text-xs tracking-widest"
              >
                 {loading ? (
                    <div className="w-5 h-5 border-2 border-black border-t-transparent rounded-full animate-spin"></div>
                 ) : (
                    <>
                      <span>Sign In</span>
                      <ArrowRight size={18} className="group-hover:translate-x-1 rtl:group-hover:-translate-x-1 transition-transform" />
                    </>
                 )}
              </button>
           </form>
           <div className="mt-8 pt-6 border-t border-zinc-800 text-center">
                 <p className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">
                 V4.5.0-STABLE • JWT SESSION ACTIVE
              </p>
           </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
