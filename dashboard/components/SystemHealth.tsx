import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Cpu, HardDrive, Wifi, Activity, Server, Radio, Database, Gauge, ShieldCheck } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';
import { SystemHealthAPI } from '../api';
import { SystemHealthCameraNode, SystemHealthSnapshot, SystemHealthWorkerNode } from '../types';

const formatBytes = (bytes: number) => {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, index)).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
};

const formatAge = (seconds?: number | null) => {
  if (seconds == null) return 'no heartbeat';
  if (seconds < 1) return '<1s ago';
  if (seconds < 60) return `${seconds.toFixed(0)}s ago`;
  return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s ago`;
};

const statusTone = (status: string) => {
  const normalized = status.toLowerCase();
  if (normalized === 'online' || normalized === 'alive') return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
  if (normalized === 'stale' || normalized === 'queued') return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
  return 'bg-red-500/10 text-red-400 border-red-500/20';
};

const MetricCard = ({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: string; detail: string }) => (
  <div className="bg-[#0f0f11] p-5 rounded-xl border border-zinc-800 flex items-center gap-4">
    <div className="text-vs-orange">{icon}</div>
    <div className="min-w-0">
      <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-widest">{label}</p>
      <p className="text-xl font-bold text-white truncate">{value}</p>
      <p className="text-[10px] text-zinc-600 font-mono truncate">{detail}</p>
    </div>
  </div>
);

const WorkerCard = ({ node }: { node: SystemHealthWorkerNode }) => {
  const load = Math.max(0, Math.min(100, node.loadPercent));
  return (
    <div className="bg-[#0f0f11] border border-zinc-800 rounded-xl p-5 hover:border-vs-orange/40 transition-colors">
      <div className="flex justify-between items-start gap-4 mb-5">
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2 bg-zinc-900 rounded-lg text-zinc-300">
            <Server size={20} />
          </div>
          <div className="min-w-0">
            <h4 className="font-bold text-white text-sm truncate">{node.name}</h4>
            <p className="text-[10px] text-zinc-600 font-mono truncate">{node.hostname || node.id}</p>
          </div>
        </div>
        <span className={`px-2 py-0.5 rounded border text-[10px] font-bold uppercase ${statusTone(node.status)}`}>
          {node.status}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <p className="text-[10px] text-zinc-500 uppercase font-bold">Heartbeat</p>
          <p className="text-sm font-mono text-zinc-300">{formatAge(node.lastSeenSeconds)}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase font-bold">Jobs</p>
          <p className="text-sm font-mono text-zinc-300">{node.activeJobs} / {node.capacity}</p>
        </div>
      </div>

      <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
        <div className="h-full bg-vs-orange transition-all duration-700" style={{ width: `${load}%` }} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-[10px] text-zinc-600 font-mono">
        <span className="truncate">GPU: {node.gpuId || 'CPU'}</span>
        <span className="truncate text-right">Queue: {node.queue || 'edge-worker'}</span>
      </div>
    </div>
  );
};

const CameraCard = ({ node }: { node: SystemHealthCameraNode }) => {
  const health = Math.max(0, Math.min(100, node.health));
  return (
    <div className="bg-[#0f0f11] border border-zinc-800 rounded-xl p-5">
      <div className="flex justify-between items-start gap-4 mb-5">
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2 bg-zinc-900 rounded-lg text-zinc-300">
            <Radio size={20} />
          </div>
          <div className="min-w-0">
            <h4 className="font-bold text-white text-sm truncate">{node.name}</h4>
            <p className="text-[10px] text-zinc-600 font-mono truncate">{node.id} · {node.zone || 'Unassigned'}</p>
          </div>
        </div>
        <span className={`px-2 py-0.5 rounded border text-[10px] font-bold uppercase ${statusTone(node.running ? 'online' : node.status)}`}>
          {node.running ? 'running' : node.status}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div>
          <p className="text-[10px] text-zinc-500 uppercase font-bold">FPS</p>
          <p className="text-sm font-mono text-zinc-300">{node.fps.toFixed(1)}</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase font-bold">Health</p>
          <p className="text-sm font-mono text-zinc-300">{health.toFixed(0)}%</p>
        </div>
        <div>
          <p className="text-[10px] text-zinc-500 uppercase font-bold">Worker</p>
          <p className="text-sm font-mono text-zinc-300 truncate">{node.workerId || 'idle'}</p>
        </div>
      </div>

      <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
        <div className="h-full bg-vs-orange transition-all duration-700" style={{ width: `${health}%` }} />
      </div>
      <p className="mt-4 text-[10px] text-zinc-600 font-mono truncate">{node.lastError || node.sourceName || 'Ready for stream assignment'}</p>
    </div>
  );
};

const SystemHealth = () => {
  const { t } = useLanguage();
  const [snapshot, setSnapshot] = useState<SystemHealthSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadHealth = useCallback(async () => {
    try {
      const data = await SystemHealthAPI.getSnapshot();
      setSnapshot(data);
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'Failed to load system health data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHealth();
    const timer = window.setInterval(loadHealth, 5000);
    return () => window.clearInterval(timer);
  }, [loadHealth]);

  const summary = snapshot?.summary;
  const serviceRows = useMemo(() => (summary ? [
    { name: 'Backend API', status: summary.backend, detail: `${summary.dbLatencyMs ?? 0} ms DB ping` },
    { name: 'Database', status: summary.database, detail: `${summary.onlineCameras}/${summary.totalCameras} cameras online` },
    { name: 'Redis Fabric', status: summary.redis, detail: `${summary.wsActiveConnections} websocket clients` },
  ] : []), [summary]);

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto bg-[#050505]">
      <div className="flex justify-between items-start gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white">{t('health')}</h2>
          <p className="text-sm text-zinc-500">Live edge infrastructure, workers, cameras, and runtime telemetry.</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-[10px] font-mono uppercase text-zinc-500">
          {loading ? 'syncing' : `updated ${new Date((snapshot?.generatedAt ?? 0) * 1000).toLocaleTimeString()}`}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard icon={<Cpu size={24} />} label="CPU Load" value={`${(summary?.cpuLoadPercent ?? 0).toFixed(1)}%`} detail={`1m load ${summary?.loadAverage1m ?? 0}`} />
        <MetricCard icon={<HardDrive size={24} />} label="Storage Used" value={`${(summary?.diskUsedPercent ?? 0).toFixed(1)}%`} detail={`${formatBytes(summary?.diskUsedBytes ?? 0)} / ${formatBytes(summary?.diskTotalBytes ?? 0)}`} />
        <MetricCard icon={<Activity size={24} />} label="Global FPS" value={`${(summary?.globalFps ?? 0).toFixed(1)} fps`} detail={`${summary?.onlineCameras ?? 0}/${summary?.totalCameras ?? 0} cameras online`} />
        <MetricCard icon={<Wifi size={24} />} label="Event Flow" value={`${summary?.incidentsLast60s ?? 0}/min`} detail={`${summary?.activeWorkers ?? 0} workers · ${summary?.activeJobs ?? 0} jobs`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {serviceRows.map((service) => (
          <div key={service.name} className="bg-[#0f0f11] border border-zinc-800 rounded-xl p-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-zinc-900 text-vs-orange">
                {service.name.includes('Database') ? <Database size={18} /> : service.name.includes('Redis') ? <Gauge size={18} /> : <ShieldCheck size={18} />}
              </div>
              <div>
                <p className="text-sm font-bold text-white">{service.name}</p>
                <p className="text-[10px] font-mono text-zinc-600">{service.detail}</p>
              </div>
            </div>
            <span className={`px-2 py-0.5 rounded border text-[10px] font-bold uppercase ${statusTone(service.status)}`}>{service.status}</span>
          </div>
        ))}
      </div>

      <div>
        <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mt-8 mb-4">{t('edgeNodes')}</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {(snapshot?.workers.length ? snapshot.workers : []).map((node) => (
            <WorkerCard key={node.id} node={node} />
          ))}
          {!loading && snapshot?.workers.length === 0 && (
            <div className="rounded-xl border border-dashed border-zinc-800 bg-[#0f0f11] p-8 text-center text-sm text-zinc-500">
              No live worker heartbeats are registered.
            </div>
          )}
        </div>
      </div>

      <div>
        <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mt-8 mb-4">Camera Processing HUD</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {(snapshot?.cameras ?? []).map((node) => (
            <CameraCard key={node.id} node={node} />
          ))}
        </div>
      </div>
    </div>
  );
};

export default SystemHealth;
