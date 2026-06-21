
export type Severity = 'Critical' | 'High' | 'Medium' | 'Low';
export type Status = 'New' | 'Notified' | 'Acknowledged' | 'In Investigation' | 'Resolved' | 'Archived' | 'False Positive' | 'Dismissed' | 'Active';
export type IncidentStatus = 'New' | 'Validating' | 'Active' | 'Acknowledged' | 'Resolved' | 'False Positive' | 'Archived';
export type HazardType = 'PPE' | 'Fall' | 'Proximity' | 'Overspeed' | 'Ergonomics' | 'Intrusion';
export type UserRole = 'Admin' | 'Safety Engineer' | 'Data Analyst';
export type ErgonomicRiskLevel = 'Low' | 'Medium' | 'High' | 'Critical';
export type SafetyZoneType = 'danger' | 'restricted' | 'forklift_only' | 'pedestrian_only' | 'no_entry' | 'loading' | 'emergency_exit' | 'ppe' | 'ppe_required' | 'maintenance' | 'custom';
export type PPERequirement = 'helmet' | 'vest' | 'gloves' | 'safety_glasses' | 'face_mask' | 'safety_shoes' | 'protective_suit' | 'ear_protection';

export interface ZonePoint {
  x: number;
  y: number;
}

export interface SafetyZoneRule {
  allowedClasses: Array<'person' | 'forklift'>;
  deniedClasses: Array<'person' | 'forklift'>;
  requiredPpe: PPERequirement[];
  occupancyThreshold?: number | null;
  dwellTimeLimitSec?: number | null;
  cooldownSec: number;
  minPersistenceSec: number;
  severity: Severity;
}

export interface CameraSafetyZone {
  id: string;
  cameraId: string;
  name: string;
  zoneType: SafetyZoneType;
  polygon: ZonePoint[];
  coordinateSpace: string;
  sourceWidth: number;
  sourceHeight: number;
  color: string;
  enabled: boolean;
  priority: number;
  rules: SafetyZoneRule;
  description?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface SafetyZoneEvent {
  id: string;
  zoneId: string;
  cameraId: string;
  eventType: string;
  objectClass: string;
  trackId?: number | null;
  stableObjectKey: string;
  severity: Severity;
  occurredAt: string;
  durationInsideSec?: number | null;
  occupancyCount?: number | null;
  frameNumber?: number | null;
  bbox?: unknown;
  anchorPoint?: unknown;
  metadata?: Record<string, unknown> | null;
  alertId?: string | null;
}

export interface SafetyZoneStats {
  zoneId: string;
  cameraId: string;
  eventCount: number;
  violationCount: number;
  currentOccupancy: number;
  avgDwellTimeSec: number;
  maxDwellTimeSec: number;
  lastEventAt?: string | null;
}

export interface Alert {
  id: string;
  incidentId?: string | null;
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
  eventFrame?: string | null;
  videoEvidence?: string | null;
  confidence?: number | null;
  trackId?: number | null;
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
  eventMetadata?: Record<string, unknown> | null;
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

export interface IncidentEvent {
  id: string;
  incidentId: string;
  action: string;
  previousStatus?: string | null;
  newStatus?: string | null;
  actorId?: string | null;
  actorName?: string | null;
  note?: string | null;
  metadata?: Record<string, unknown> | null;
  createdAt: string;
}

export interface NotificationRecord {
  id: string;
  userId?: string | null;
  title: string;
  message: string;
  type: 'info' | 'alert' | 'system' | string;
  isRead: boolean;
  source?: string | null;
  createdAt: string;
}

export type CameraSourceType = 'rtsp' | 'mediamtx' | 'file' | 'webcam' | 'webrtc';

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
  aiAlertCooldownSec?: number | null;
  url?: string;
  stream_url?: string;  // RTSP URL, filename, or webcam-index string
  source_type?: CameraSourceType | null;
  mediamtxPath?: string | null;
  deviceIndex?: number | null;
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
  status: IncidentStatus;
  startedAt?: string | null;
  validatedAt?: string | null;
  acknowledgedAt?: string | null;
  acknowledgedBy?: string | null;
  resolvedAt?: string | null;
  resolvedBy?: string | null;
  archivedAt?: string | null;
  slaBreachedAt?: string | null;
  slaAckBreachedAt?: string | null;
  slaResolutionBreachedAt?: string | null;
  slaBreachCount?: number;
  durationSeconds?: number | null;
  escalationCount?: number;
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
  sourceType?: CameraSourceType;
  cameraId?: string;
  thumbnail?: string;
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
  avgResolutionTimeSeconds: number;
  slaBreachCount: number;
  slaBreachRate: number;
  avgResponseTimeSeconds: number;
  topDangerousZones: Array<{ zone: string; incidentCount: number; riskScore: number }>;
  recurringHazards: Array<{ zone: string; classification: string; count: number }>;
  weeklySummary?: {
    incidents: number;
    previousIncidents: number;
    resolved: number;
    delta: number;
  };
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
  USERS = 'Users'
}
