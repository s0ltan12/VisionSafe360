
export type Severity = 'High' | 'Medium' | 'Low';
export type Status = 'New' | 'Notified' | 'Acknowledged' | 'In Investigation' | 'Resolved' | 'Dismissed' | 'Active';
export type HazardType = 'PPE' | 'Fall' | 'Proximity' | 'Ergonomics' | 'Intrusion';
export type UserRole = 'Admin' | 'Safety Engineer' | 'Data Analyst';

export interface Alert {
  id: string;
  type: HazardType;
  severity: Severity;
  zone: string;
  camera: string;
  cameraId?: string | null;
  cameraName?: string | null;
  workerId?: string | null;
  workerGpuId?: string | null;
  timestamp: string;
  status: Status;
  description: string;
  thumbnail: string;
  confidence?: number;
}

export interface Camera {
  id: string;
  name: string;
  zone: string;
  url?: string;
  stream_url?: string;  // RTSP/live stream source for AI detection
  status: 'Online' | 'Offline';
  isPrivacyMode: boolean;
  thumbnail: string;
  fps?: number;
  health?: number;
}

export interface Incident {
  id: string;
  zone: string;
  classification: string;
  severity: Severity;
  cameraId?: string | null;
  cameraName?: string | null;
  workerId?: string | null;
  workerGpuId?: string | null;
  rootCause: string;
  correctiveAction: string;
  createdAt: string;
}

export interface DemoVideo {
  id: string;
  name: string;
  fileName: string;
  type?: 'demo' | 'upload';
  zone: string;
  description: string;
  streamUrl: string;
}

export interface JobStatus {
  running: boolean;
  pid?: number | null;
  sourceName?: string | null;
  cameraId?: string | null;
  startedAt?: number | null;
  lastError?: string | null;
  lastExitCode?: number | null;
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  status: 'Active' | 'Inactive';
}

export enum Page {
  DASHBOARD = 'Dashboard',
  LIVE_MONITORING = 'Live Monitoring',
  ALERTS = 'Alerts',
  INCIDENTS = 'Incidents',
  ERGONOMICS = 'Ergonomics',
  REPORTS = 'Analytics',
  CAMERAS = 'Cameras',
  HEALTH = 'System Health',
  USERS = 'Users',
  CONFIGURATION = 'Configuration'
}
