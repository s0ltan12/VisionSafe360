import React, { useState, useRef } from 'react';
import { User, Lock, ArrowRight } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';
import VisionSafeLogo from './VisionSafeLogo';
import { UserRole } from '../types';
import { AuthAPI, setAuthToken } from '../api';
import { AccessibleErrorMessage, announceToScreenReader } from '../utils/accessibility';
import { Button, FieldRoot, TextInput } from './ui';

interface LoginProps {
   onLogin: (user: {name: string, role: UserRole}, token: string) => void;
}

const Login: React.FC<LoginProps> = ({ onLogin }) => {
  const { t, dir } = useLanguage();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [usernameError, setUsernameError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const formRef = useRef<HTMLFormElement>(null);
  const submitButtonRef = useRef<HTMLButtonElement>(null);

  const validateForm = (): boolean => {
    let isValid = true;
    setUsernameError('');
    setPasswordError('');

    if (!username.trim()) {
      setUsernameError('Username is required');
      isValid = false;
    }
    if (!password.trim()) {
      setPasswordError('Password is required');
      isValid = false;
    }

    return isValid;
  };

  const resolveCredentials = (value: string) => {
    // Require full email address; no shortcuts.
    return { email: value.trim() };
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateForm()) {
      announceToScreenReader('Form validation errors. Please correct them and try again.', 'assertive');
      return;
    }

    setLoading(true);
    setError('');
    const { email } = resolveCredentials(username);

    AuthAPI.login(email, password)
      .then((result) => {
        setAuthToken(result.access_token);
        return AuthAPI.me().then((user) => ({ user, token: result.access_token }));
      })
      .then(({ user, token }) => {
        announceToScreenReader('Login successful. Redirecting to dashboard.', 'polite');
        onLogin({ name: user.name, role: user.role }, token);
      })
      .catch((err: any) => {
        setAuthToken(null);
        const message = String(err?.message || '');
        let errorMsg = '';
        if (message.includes('Failed to fetch') || message.includes('NetworkError') || message.includes('HTTP 502')) {
          errorMsg = 'Cannot reach backend service. Please verify API is up and reachable.';
        } else {
          errorMsg = 'Invalid credentials. Use the seeded demo accounts or a valid email/password pair.';
        }
        setError(errorMsg);
        announceToScreenReader(errorMsg, 'assertive');
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
          <form ref={formRef} onSubmit={handleSubmit} className="space-y-6" noValidate aria-label="Login form">
            {error && (
              <AccessibleErrorMessage 
                id="login-error" 
                message={error} 
                role="alert" 
              />
            )}

            <FieldRoot label="Username" htmlFor="username-input" error={usernameError} errorId="username-error">
              <TextInput
                id="username-input"
                type="text"
                required
                value={username}
                onChange={(e) => {
                  setUsername(e.target.value);
                  setUsernameError('');
                }}
                onBlur={() => {
                  if (!username.trim()) {
                    setUsernameError('Username is required');
                  }
                }}
                leadingIcon={<User size={18} />}
                className="rounded-xl bg-black py-3 ps-10 pe-4 placeholder-zinc-800"
                placeholder="e.g. admin or email"
                error={!!usernameError}
                aria-describedby={usernameError ? 'username-error' : undefined}
              />
            </FieldRoot>

            <FieldRoot
              label="Password"
              htmlFor="password-input"
              error={passwordError}
              errorId="password-error"
              helpId="password-help"
              helpText="Use your company email and password."
            >
              <TextInput
                id="password-input"
                type="password"
                required
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setPasswordError('');
                }}
                onBlur={() => {
                  if (!password.trim()) {
                    setPasswordError('Password is required');
                  }
                }}
                leadingIcon={<Lock size={18} />}
                className="rounded-xl bg-black py-3 ps-10 pe-4 placeholder-zinc-800"
                placeholder="Password"
                error={!!passwordError}
                aria-describedby={passwordError ? 'password-error' : 'password-help'}
              />
            </FieldRoot>

            <Button
              ref={submitButtonRef}
              type="submit" 
              disabled={loading}
              isLoading={loading}
              variant="primary"
              size="lg"
              aria-busy={loading}
              aria-label={loading ? 'Signing in, please wait' : 'Sign in to VisionSafe 360'}
              trailingIcon={!loading ? <ArrowRight size={18} className="group-hover:translate-x-1 rtl:group-hover:-translate-x-1 transition-transform" /> : undefined}
              className="group w-full"
            >
              {loading ? 'Signing In' : 'Sign In'}
            </Button>
          </form>
          <div className="mt-8 pt-6 border-t border-zinc-800 text-center">
            <p className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">
              Secure operator access
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
