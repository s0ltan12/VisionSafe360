/**
 * api.ts — Frontend API client
 * Replaces the localStorage db.ts — all calls go to FastAPI backend.
 */

import {Alert, Camera, DemoVideo, Incident, JobStatus, User} from './types';

const env = (import.meta as any).env ?? {};

const BASE_URL = String(env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

function resolveWsBaseUrl(): string {
  const configured = String(env.VITE_WS_BASE_URL || '').trim();
  if (configured) {
    return configured.replace(/\/+$/, '');
  }

  if (BASE_URL.startsWith('https://')) {
    return `wss://${BASE_URL.slice('https://'.length)}`;
  }
  if (BASE_URL.startsWith('http://')) {
    return `ws://${BASE_URL.slice('http://'.length)}`;
  }
  return 'ws://localhost:8000';
}

export const WS_BASE_URL = resolveWsBaseUrl();

const TOKEN_KEY = 'visionsafe360_token';

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getAuthToken(): string | null {
  return getToken();
}

export function setAuthToken(token: string | null) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail?.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Helpers ──────────────────────────────────────────────────────────────────
// The backend uses snake_case (is_privacy_mode, root_cause…).
// The frontend uses camelCase (isPrivacyMode, rootCause…).
// These two helpers convert between them.

function toFrontendCamera(c: any): Camera {
  return {
    id:            c.id,
    name:          c.name,
    zone:          c.zone,
    url:           c.url,
    status:        c.status,
    isPrivacyMode: c.is_privacy_mode,
    thumbnail:     c.thumbnail,
    fps:           c.fps,
    health:        c.health,
  };
}

function toFrontendDemoVideo(v: any): DemoVideo {
  return {
    id: v.id,
    name: v.name,
    fileName: v.file_name,
    zone: v.zone,
    description: v.description,
    streamUrl: v.stream_url,
    streamFeedUrl: v.stream_feed_url,
  };
}

function toFrontendIncident(i: any): Incident {
  return {
    id:               i.id,
    zone:             i.zone,
    classification:   i.classification,
    severity:         i.severity,
    rootCause:        i.root_cause,
    correctiveAction: i.corrective_action,
    createdAt:        i.created_at,
  };
}

function toFrontendJobStatus(s: any): JobStatus {
  return {
    running: s.running,
    pid: s.pid,
    sourceName: s.source_name,
    cameraId: s.camera_id,
    startedAt: s.started_at,
    lastError: s.last_error,
    lastExitCode: s.last_exit_code,
  };
}

// ═══════════════════════════════════════════════════════════════════════════
// ALERTS
// ═══════════════════════════════════════════════════════════════════════════

export const AlertsAPI = {
  getAll: () =>
    request<Alert[]>('/api/alerts'),

  update: (id: string, changes: Partial<Alert>) =>
    request<Alert>(`/api/alerts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),

  create: (alert: Alert) =>
    request<Alert>('/api/alerts', {
      method: 'POST',
      body: JSON.stringify(alert),
    }),

  delete: (id: string) =>
    request<void>(`/api/alerts/${id}`, { method: 'DELETE' }),
};

// ═══════════════════════════════════════════════════════════════════════════
// CAMERAS
// ═══════════════════════════════════════════════════════════════════════════

export const CamerasAPI = {
  getAll: async (): Promise<Camera[]> => {
    const data = await request<any[]>('/api/cameras');
    return data.map(toFrontendCamera);
  },

  add: async (camera: Camera): Promise<Camera> => {
    const body = { ...camera, is_privacy_mode: camera.isPrivacyMode };
    const data = await request<any>('/api/cameras', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    return toFrontendCamera(data);
  },

  update: async (id: string, changes: Partial<Camera>): Promise<Camera> => {
    const body: any = { ...changes };
    if (changes.isPrivacyMode !== undefined) {
      body.is_privacy_mode = changes.isPrivacyMode;
      delete body.isPrivacyMode;
    }
    const data = await request<any>(`/api/cameras/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
    return toFrontendCamera(data);
  },

  delete: (id: string) =>
    request<void>(`/api/cameras/${id}`, { method: 'DELETE' }),
};

// ═══════════════════════════════════════════════════════════════════════════
// INCIDENTS
// ═══════════════════════════════════════════════════════════════════════════

export const IncidentsAPI = {
  getAll: async (): Promise<Incident[]> => {
    const data = await request<any[]>('/api/incidents');
    return data.map(toFrontendIncident);
  },

  create: async (incident: Incident): Promise<Incident> => {
    const body = {
      id:                incident.id,
      zone:              incident.zone,
      classification:    incident.classification,
      severity:          incident.severity,
      root_cause:        incident.rootCause,
      corrective_action: incident.correctiveAction,
      created_at:        incident.createdAt,
    };
    const data = await request<any>('/api/incidents', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    return toFrontendIncident(data);
  },

  delete: (id: string) =>
    request<void>(`/api/incidents/${id}`, { method: 'DELETE' }),
};

// ═══════════════════════════════════════════════════════════════════════════
// USERS
// ═══════════════════════════════════════════════════════════════════════════

export const UsersAPI = {
  getAll: () =>
    request<User[]>('/api/users'),

  create: (user: User) =>
    request<User>('/api/users', {
      method: 'POST',
      body: JSON.stringify(user),
    }),

  update: (id: string, changes: Partial<User>) =>
    request<User>(`/api/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),

  delete: (id: string) =>
    request<void>(`/api/users/${id}`, { method: 'DELETE' }),
};

// ═══════════════════════════════════════════════════════════════════════════
// STATS
// ═══════════════════════════════════════════════════════════════════════════

export const StatsAPI = {
  getAll: () =>
    request<{
      total_alerts: number;
      active_alerts: number;
      resolved_alerts: number;
      total_cameras: number;
      online_cameras: number;
      offline_cameras: number;
      total_incidents: number;
      total_users: number;
    }>('/api/stats'),
};

export const AuthAPI = {
  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  me: () =>
    request<User>('/api/auth/me'),
};

export const DemoVideosAPI = {
  getAll: async () => {
    const data = await request<any[]>('/api/media/videos');
    return data.map(toFrontendDemoVideo);
  },
};

export const JobsAPI = {
  status: async () => {
    const data = await request<any>('/api/jobs/status');
    return toFrontendJobStatus(data);
  },

  start: async (sourceName: string, cameraId: string = 'cam_01') => {
    const data = await request<any>('/api/jobs/start', {
      method: 'POST',
      body: JSON.stringify({ source_name: sourceName, camera_id: cameraId }),
    });
    return toFrontendJobStatus(data);
  },

  stop: async () => {
    const data = await request<any>('/api/jobs/stop', {
      method: 'POST',
    });
    return toFrontendJobStatus(data);
  },
};
