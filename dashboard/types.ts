
export type Severity = 'Critical' | 'High' | 'Medium' | 'Low';
export type Status = 'New' | 'Notified' | 'Acknowledged' | 'In Investigation' | 'Resolved' | 'Archived' | 'False Positive' | 'Dismissed' | 'Active';
export type HazardType = 'PPE' | 'Fall' | 'Proximity' | 'Ergonomics' | 'Intrusion';
export type UserRole = 'Admin' | 'Safety Engineer' | 'Data Analyst';
export type ErgonomicRiskLevel = 'Low' | 'Medium' | 'High' | 'Critical';

export interface Alert {
  id: string;
  type: HazardType;
  severity: Severity;
  zone: string;
  areaId?: string | null;
  areaName?: string | null;
  zoneId?: string | null;
  zoneName?: string | null;
  locationDescription?: string | null;
  camera: string;
  cameraId?: string | null;
  cameraName?: string | null;
  workerId?: string | null;
  workerGpuId?: string | null;
  timestamp: string;
  status: Status;
  description: string;
  thumbnail?: string | null;
  confidence?: number | null;
  frameNumber?: number | null;
  frameWidth?: number | null;
  frameHeight?: number | null;
  evidenceKind?: string | null;
  acknowledgedBy?: string | null;
  acknowledgedById?: string | null;
  acknowledgedAt?: string | null;
  resolvedBy?: string | null;
  resolvedById?: string | null;
  resolvedAt?: string | null;
  archivedBy?: string | null;
  archivedById?: string | null;
  archivedAt?: string | null;
  falsePositiveBy?: string | null;
  falsePositiveById?: string | null;
  falsePositiveAt?: string | null;
}

export interface AlertEvent {
  id: string;
  alertId: string;
  action: string;
  previousStatus?: string | null;
  newStatus?: string | null;
  actorId?: string | null;
  actorName?: string | null;
  note?: string | null;
  metadata?: Record<string, unknown> | null;
  createdAt: string;
}

export interface Camera {
  id: string;
  name: string;
  zone: string;
  areaId?: string | null;
  zoneId?: string | null;
  areaName?: string | null;
  zoneName?: string | null;
  locationDescription?: string | null;
  supportedAiCapabilities?: string[] | null;
  severityProfile?: string | null;
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

export interface ErgonomicRecord {
  id: string;
  cameraId: string;
  zone?: string | null;
  trackId?: number | null;
  riskLevel: ErgonomicRiskLevel;
  rulaScore?: number | null;
  rebaScore?: number | null;
  description?: string | null;
  recordedAt?: string | null;
}

export interface ErgonomicTrendPoint {
  date: string;
  avgRulaScore: number;
  avgRebaScore: number;
  count: number;
}

export interface ErgonomicZoneDistribution {
  zone: string;
  count: number;
  highRiskCount: number;
  avgRulaScore: number;
}

export interface ErgonomicStats {
  totalRecords: number;
  highRiskCount: number;
  avgRulaScore: number;
  avgRebaScore: number;
  trend: ErgonomicTrendPoint[];
  zoneDistribution: ErgonomicZoneDistribution[];
  riskDistribution: Array<{ riskLevel: string; count: number }>;
}

export interface AnalyticsStats {
  totalAlerts: number;
  activeAlerts: number;
  resolvedAlerts: number;
  totalCameras: number;
  onlineCameras: number;
  offlineCameras: number;
  totalIncidents: number;
  totalUsers: number;
  fallsDetected: number;
  safetyScore: number;
  incidentsLast7Days: number;
  incidentsPrevious7Days: number;
}

export interface AnalyticsTimeSeriesPoint {
  date: string;
  count: number;
}

export interface AnalyticsDistributionPoint {
  name: string;
  count: number;
}

export interface SystemHealthSummary {
  backend: string;
  database: string;
  redis: string;
  activeWorkers: number;
  activeJobs: number;
  onlineCameras: number;
  totalCameras: number;
  globalFps: number;
  cpuLoadPercent: number;
  loadAverage1m: number;
  diskUsedBytes: number;
  diskTotalBytes: number;
  diskUsedPercent: number;
  dbLatencyMs?: number | null;
  wsActiveConnections: number;
  incidentsLast60s: number;
  rateLimitedLast60s: number;
}

export interface SystemHealthWorkerNode {
  id: string;
  name: string;
  status: string;
  hostname?: string | null;
  gpuId?: string | null;
  queue?: string | null;
  capacity: number;
  activeJobs: number;
  loadPercent: number;
  latencyMs?: number | null;
  lastSeenSeconds?: number | null;
}

export interface SystemHealthCameraNode {
  id: string;
  name: string;
  status: string;
  zone?: string | null;
  fps: number;
  health: number;
  sourceName?: string | null;
  running: boolean;
  queued: boolean;
  workerId?: string | null;
  workerGpuId?: string | null;
  startedAt?: number | null;
  lastError?: string | null;
}

export interface SystemHealthSnapshot {
  generatedAt: number;
  summary: SystemHealthSummary;
  workers: SystemHealthWorkerNode[];
  cameras: SystemHealthCameraNode[];
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
