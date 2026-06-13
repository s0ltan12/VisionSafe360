/**
 * api.ts — Frontend API client
 * Replaces the localStorage db.ts — all calls go to FastAPI backend.
 */

import {
  Alert,
  AlertEvent,
  AnalyticsDistributionPoint,
  AnalyticsStats,
  AnalyticsTimeSeriesPoint,
  Camera,
  CameraSourceType,
  DemoVideo,
  ErgonomicRecord,
  ErgonomicStats,
  Incident,
  IncidentEvent,
  JobStatus,
  NotificationRecord,
  CameraSafetyZone,
  SafetyZoneEvent,
  SafetyZoneRule,
  SafetyZoneStats,
  SystemHealthSnapshot,
  User,
  ZonePoint,
} from './types';

const env = (import.meta as any).env ?? {};

const BASE_URL = String(env.VITE_API_BASE_URL || '').replace(/\/+$/, '');

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

  if (typeof window !== 'undefined') {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${wsProtocol}://${window.location.host}`;
  }

  return 'ws://localhost:8000';
}

export const WS_BASE_URL = resolveWsBaseUrl();

const TOKEN_KEY = 'visionsafe360_token';
const EVIDENCE_ASSET_VERSION = '2';

function isOverspeedRecord(...values: unknown[]): boolean {
  return values.some(value => /overspeed/i.test(String(value ?? '')));
}

function displayAlertType(record: any): Alert['type'] {
  if (isOverspeedRecord(record.type, record.description, record.classification, record.root_cause)) {
    return 'Overspeed';
  }
  return String(record.type ?? 'Intrusion') as Alert['type'];
}

function displayIncidentClassification(record: any): string {
  if (isOverspeedRecord(record.classification, record.root_cause, record.description)) {
    return 'Forklift Overspeed';
  }
  return String(record.classification ?? 'Hazard');
}

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
    areaId:        c.area_id ?? c.areaId ?? null,
    zoneId:        c.zone_id ?? c.zoneId ?? null,
    areaName:      c.area_name ?? c.areaName ?? null,
    zoneName:      c.zone_name ?? c.zoneName ?? null,
    locationDescription: c.location_description ?? c.locationDescription ?? null,
    supportedAiCapabilities: Array.isArray(c.supported_ai_capabilities) ? c.supported_ai_capabilities : (Array.isArray(c.supportedAiCapabilities) ? c.supportedAiCapabilities : null),
    severityProfile: c.severity_profile ?? c.severityProfile ?? null,
    url:           c.url,
    stream_url:    c.stream_url,
    source_type:   c.source_type ?? c.sourceType ?? null,
    mediamtxPath:  c.mediamtx_path ?? c.mediamtxPath ?? null,
    deviceIndex:   c.device_index ?? c.deviceIndex ?? null,
    status:        c.status,
    isPrivacyMode: c.is_privacy_mode,
    thumbnail:     c.thumbnail,
    fps:           c.fps,
    health:        c.health,
  };
}

function toFrontendZoneRule(rule: any): SafetyZoneRule {
  return {
    allowedClasses: Array.isArray(rule?.allowed_classes) ? rule.allowed_classes : (Array.isArray(rule?.allowedClasses) ? rule.allowedClasses : ['person', 'forklift']),
    deniedClasses: Array.isArray(rule?.denied_classes) ? rule.denied_classes : (Array.isArray(rule?.deniedClasses) ? rule.deniedClasses : []),
    occupancyThreshold: rule?.occupancy_threshold ?? rule?.occupancyThreshold ?? null,
    dwellTimeLimitSec: rule?.dwell_time_limit_sec ?? rule?.dwellTimeLimitSec ?? null,
    cooldownSec: Number(rule?.cooldown_sec ?? rule?.cooldownSec ?? 30),
    minPersistenceSec: Number(rule?.min_persistence_sec ?? rule?.minPersistenceSec ?? 0.5),
    severity: rule?.severity ?? 'High',
  };
}

function toBackendZoneRule(rule: SafetyZoneRule): any {
  return {
    allowed_classes: rule.allowedClasses,
    denied_classes: rule.deniedClasses,
    occupancy_threshold: rule.occupancyThreshold ?? null,
    dwell_time_limit_sec: rule.dwellTimeLimitSec ?? null,
    cooldown_sec: rule.cooldownSec,
    min_persistence_sec: rule.minPersistenceSec,
    severity: rule.severity,
  };
}

function toFrontendSafetyZone(zone: any): CameraSafetyZone {
  return {
    id: String(zone.id ?? ''),
    cameraId: String(zone.camera_id ?? zone.cameraId ?? ''),
    name: String(zone.name ?? ''),
    zoneType: zone.zone_type ?? zone.zoneType ?? 'custom',
    polygon: Array.isArray(zone.polygon) ? zone.polygon.map((point: any): ZonePoint => ({ x: Number(point.x), y: Number(point.y) })) : [],
    coordinateSpace: String(zone.coordinate_space ?? zone.coordinateSpace ?? 'source_pixels'),
    sourceWidth: Number(zone.source_width ?? zone.sourceWidth ?? 1280),
    sourceHeight: Number(zone.source_height ?? zone.sourceHeight ?? 720),
    color: String(zone.color ?? '#f97316'),
    enabled: Boolean(zone.enabled ?? true),
    priority: Number(zone.priority ?? 100),
    rules: toFrontendZoneRule(zone.rules ?? {}),
    description: zone.description ?? null,
    createdAt: zone.created_at ?? zone.createdAt ?? null,
    updatedAt: zone.updated_at ?? zone.updatedAt ?? null,
  };
}

function toBackendSafetyZone(zone: Partial<CameraSafetyZone>): any {
  const body: any = {};
  if (zone.id !== undefined) body.id = zone.id;
  if (zone.name !== undefined) body.name = zone.name;
  if (zone.zoneType !== undefined) body.zone_type = zone.zoneType;
  if (zone.polygon !== undefined) body.polygon = zone.polygon;
  if (zone.coordinateSpace !== undefined) body.coordinate_space = zone.coordinateSpace;
  if (zone.sourceWidth !== undefined) body.source_width = zone.sourceWidth;
  if (zone.sourceHeight !== undefined) body.source_height = zone.sourceHeight;
  if (zone.color !== undefined) body.color = zone.color;
  if (zone.enabled !== undefined) body.enabled = zone.enabled;
  if (zone.priority !== undefined) body.priority = zone.priority;
  if (zone.rules !== undefined) body.rules = toBackendZoneRule(zone.rules);
  if (zone.description !== undefined) body.description = zone.description;
  return body;
}

function toFrontendSafetyZoneEvent(event: any): SafetyZoneEvent {
  return {
    id: String(event.id ?? ''),
    zoneId: String(event.zone_id ?? event.zoneId ?? ''),
    cameraId: String(event.camera_id ?? event.cameraId ?? ''),
    eventType: String(event.event_type ?? event.eventType ?? ''),
    objectClass: String(event.object_class ?? event.objectClass ?? ''),
    trackId: event.track_id ?? event.trackId ?? null,
    stableObjectKey: String(event.stable_object_key ?? event.stableObjectKey ?? ''),
    severity: event.severity ?? 'Medium',
    occurredAt: String(event.occurred_at ?? event.occurredAt ?? ''),
    durationInsideSec: event.duration_inside_sec ?? event.durationInsideSec ?? null,
    occupancyCount: event.occupancy_count ?? event.occupancyCount ?? null,
    frameNumber: event.frame_number ?? event.frameNumber ?? null,
    bbox: event.bbox ?? null,
    anchorPoint: event.anchor_point ?? event.anchorPoint ?? null,
    metadata: event.event_metadata ?? event.metadata ?? null,
    alertId: event.alert_id ?? event.alertId ?? null,
  };
}

function toFrontendSafetyZoneStats(stats: any): SafetyZoneStats {
  return {
    zoneId: String(stats.zone_id ?? stats.zoneId ?? ''),
    cameraId: String(stats.camera_id ?? stats.cameraId ?? ''),
    eventCount: Number(stats.event_count ?? stats.eventCount ?? 0),
    violationCount: Number(stats.violation_count ?? stats.violationCount ?? 0),
    currentOccupancy: Number(stats.current_occupancy ?? stats.currentOccupancy ?? 0),
    avgDwellTimeSec: Number(stats.avg_dwell_time_sec ?? stats.avgDwellTimeSec ?? 0),
    maxDwellTimeSec: Number(stats.max_dwell_time_sec ?? stats.maxDwellTimeSec ?? 0),
    lastEventAt: stats.last_event_at ?? stats.lastEventAt ?? null,
  };
}

function appendAuthToken(url: string | null | undefined): string {
  if (!url) return '';
  const token = getToken();
  if (!token) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}token=${encodeURIComponent(token)}`;
}

function appendQueryParam(url: string, key: string, value: string): string {
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
}

function toAssetUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  if (value.startsWith('data:') || value.startsWith('http://') || value.startsWith('https://')) {
    return value;
  }
  const evidencePath = '/storage/evidence/';
  const evidenceIndex = value.indexOf(evidencePath);
  if (evidenceIndex >= 0) {
    return appendQueryParam(`${BASE_URL}${value.slice(evidenceIndex)}`, 'ev', EVIDENCE_ASSET_VERSION);
  }
  return value;
}

function toEvidenceUrl(value: string | null | undefined): string | null {
  const url = toAssetUrl(value);
  if (!url || url.startsWith('data:')) return url;
  return appendQueryParam(url, 'codec', 'h264');
}

function toFrontendDemoVideo(v: any): DemoVideo {
  return {
    id: v.id,
    name: v.name,
    fileName: v.file_name,
    zone: v.zone,
    description: v.description,
    streamUrl: appendAuthToken(v.stream_url),
  };
}

function toFrontendIncident(i: any): Incident {
  return {
    id:               i.id,
    zone:             i.zone,
    classification:   displayIncidentClassification(i),
    severity:         i.severity,
    cameraId:         i.camera_id ?? i.cameraId ?? null,
    cameraName:       i.camera_name ?? i.cameraName ?? null,
    workerId:         i.worker_id ?? i.workerId ?? null,
    workerGpuId:      i.worker_gpu_id ?? i.workerGpuId ?? null,
    status:           i.status ?? 'New',
    startedAt:        i.started_at ?? i.startedAt ?? null,
    validatedAt:      i.validated_at ?? i.validatedAt ?? null,
    acknowledgedAt:   i.acknowledged_at ?? i.acknowledgedAt ?? null,
    acknowledgedBy:   i.acknowledged_by ?? i.acknowledgedBy ?? null,
    resolvedAt:       i.resolved_at ?? i.resolvedAt ?? null,
    resolvedBy:       i.resolved_by ?? i.resolvedBy ?? null,
    archivedAt:       i.archived_at ?? i.archivedAt ?? null,
    slaBreachedAt:    i.sla_breached_at ?? i.slaBreachedAt ?? null,
    slaAckBreachedAt: i.sla_ack_breached_at ?? i.slaAckBreachedAt ?? null,
    slaResolutionBreachedAt: i.sla_resolution_breached_at ?? i.slaResolutionBreachedAt ?? null,
    slaBreachCount:   Number(i.sla_breach_count ?? i.slaBreachCount ?? 0),
    durationSeconds:  i.duration_seconds ?? i.durationSeconds ?? null,
    escalationCount:  Number(i.escalation_count ?? i.escalationCount ?? 0),
    rootCause:        i.root_cause,
    correctiveAction: i.corrective_action,
    createdAt:        i.created_at,
  };
}

function toFrontendIncidentEvent(event: any): IncidentEvent {
  return {
    id: String(event.id ?? ''),
    incidentId: String(event.incident_id ?? event.incidentId ?? ''),
    action: String(event.action ?? ''),
    previousStatus: event.previous_status ?? event.previousStatus ?? null,
    newStatus: event.new_status ?? event.newStatus ?? null,
    actorId: event.actor_id ?? event.actorId ?? null,
    actorName: event.actor_name ?? event.actorName ?? null,
    note: event.note ?? null,
    metadata: event.event_metadata ?? event.metadata ?? null,
    createdAt: String(event.created_at ?? event.createdAt ?? ''),
  };
}

function toFrontendNotification(record: any): NotificationRecord {
  return {
    id: String(record.id ?? ''),
    userId: record.user_id ?? record.userId ?? null,
    title: String(record.title ?? ''),
    message: String(record.message ?? ''),
    type: String(record.type ?? 'info'),
    isRead: Boolean(record.is_read ?? record.isRead ?? false),
    source: record.source ?? null,
    createdAt: String(record.created_at ?? record.createdAt ?? ''),
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

function toFrontendAlert(a: any): Alert {
  return {
    id:          a.id,
    incidentId:  a.incident_id ?? a.incidentId ?? null,
    type:        displayAlertType(a),
    severity:    a.severity,
    zone:        a.zone,
    areaId:      a.area_id ?? a.areaId ?? null,
    areaName:    a.area_name ?? a.areaName ?? null,
    zoneId:      a.zone_id ?? a.zoneId ?? null,
    zoneName:    a.zone_name ?? a.zoneName ?? null,
    locationDescription: a.location_description ?? a.locationDescription ?? null,
    camera:      a.camera,
    cameraId:    a.camera_id ?? a.cameraId ?? null,
    cameraName:  a.camera_name ?? a.cameraName ?? null,
    workerId:    a.worker_id ?? a.workerId ?? null,
    workerGpuId: a.worker_gpu_id ?? a.workerGpuId ?? null,
    timestamp:   a.occurred_at || a.timestamp || a.created_at || '',
    status:      a.status,
    description: a.description,
    thumbnail:   toAssetUrl(a.thumbnail ?? null),
    eventFrame:  toAssetUrl(a.event_frame ?? a.eventFrame ?? null),
    videoEvidence: toEvidenceUrl(a.video_evidence ?? a.videoEvidence ?? null),
    confidence:  a.confidence ?? null,
    trackId:     a.track_id ?? a.trackId ?? null,
    frameNumber: a.frame_number ?? a.frameNumber ?? null,
    frameWidth:  a.frame_width ?? a.frameWidth ?? null,
    frameHeight: a.frame_height ?? a.frameHeight ?? null,
    evidenceKind: a.evidence_kind ?? a.evidenceKind ?? null,
    acknowledgedBy: a.acknowledged_by ?? a.acknowledgedBy ?? null,
    acknowledgedById: a.acknowledged_by_id ?? a.acknowledgedById ?? null,
    acknowledgedAt: a.acknowledged_at ?? a.acknowledgedAt ?? null,
    resolvedBy: a.resolved_by ?? a.resolvedBy ?? null,
    resolvedById: a.resolved_by_id ?? a.resolvedById ?? null,
    resolvedAt: a.resolved_at ?? a.resolvedAt ?? null,
    archivedBy: a.archived_by ?? a.archivedBy ?? null,
    archivedById: a.archived_by_id ?? a.archivedById ?? null,
    archivedAt: a.archived_at ?? a.archivedAt ?? null,
    falsePositiveBy: a.false_positive_by ?? a.falsePositiveBy ?? null,
    falsePositiveById: a.false_positive_by_id ?? a.falsePositiveById ?? null,
    falsePositiveAt: a.false_positive_at ?? a.falsePositiveAt ?? null,
  };
}

function toFrontendAlertEvent(event: any): AlertEvent {
  return {
    id: String(event.id ?? ''),
    alertId: String(event.alert_id ?? event.alertId ?? ''),
    action: String(event.action ?? ''),
    previousStatus: event.previous_status ?? event.previousStatus ?? null,
    newStatus: event.new_status ?? event.newStatus ?? null,
    actorId: event.actor_id ?? event.actorId ?? null,
    actorName: event.actor_name ?? event.actorName ?? null,
    note: event.note ?? null,
    metadata: event.event_metadata ?? event.metadata ?? null,
    createdAt: String(event.created_at ?? event.createdAt ?? ''),
  };
}

function toFrontendErgonomicRecord(record: any): ErgonomicRecord {
  return {
    id: record.id,
    cameraId: record.camera_id,
    zone: record.zone ?? null,
    trackId: record.track_id ?? null,
    riskLevel: record.risk_level,
    rulaScore: record.rula_score ?? null,
    rebaScore: record.reba_score ?? null,
    description: record.description ?? null,
    recordedAt: record.recorded_at ?? null,
  };
}

function toFrontendErgonomicStats(stats: any): ErgonomicStats {
  return {
    totalRecords: Number(stats.total_records ?? 0),
    highRiskCount: Number(stats.high_risk_count ?? 0),
    avgRulaScore: Number(stats.avg_rula_score ?? 0),
    avgRebaScore: Number(stats.avg_reba_score ?? 0),
    trend: Array.isArray(stats.trend) ? stats.trend.map((point: any) => ({
      date: String(point.date ?? ''),
      avgRulaScore: Number(point.avg_rula_score ?? 0),
      avgRebaScore: Number(point.avg_reba_score ?? 0),
      count: Number(point.count ?? 0),
    })) : [],
    zoneDistribution: Array.isArray(stats.zone_distribution) ? stats.zone_distribution.map((zone: any) => ({
      zone: String(zone.zone ?? 'Unassigned'),
      count: Number(zone.count ?? 0),
      highRiskCount: Number(zone.high_risk_count ?? 0),
      avgRulaScore: Number(zone.avg_rula_score ?? 0),
    })) : [],
    riskDistribution: Array.isArray(stats.risk_distribution) ? stats.risk_distribution.map((item: any) => ({
      riskLevel: String(item.risk_level ?? ''),
      count: Number(item.count ?? 0),
    })) : [],
  };
}

function toFrontendAnalyticsStats(stats: any): AnalyticsStats {
  return {
    totalAlerts: Number(stats.total_alerts ?? 0),
    activeAlerts: Number(stats.active_alerts ?? 0),
    resolvedAlerts: Number(stats.resolved_alerts ?? 0),
    totalCameras: Number(stats.total_cameras ?? 0),
    onlineCameras: Number(stats.online_cameras ?? 0),
    offlineCameras: Number(stats.offline_cameras ?? 0),
    totalIncidents: Number(stats.total_incidents ?? 0),
    totalUsers: Number(stats.total_users ?? 0),
    fallsDetected: Number(stats.falls_detected ?? 0),
    safetyScore: Number(stats.safety_score ?? 0),
    incidentsLast7Days: Number(stats.incidents_last_7_days ?? 0),
    incidentsPrevious7Days: Number(stats.incidents_previous_7_days ?? 0),
    avgResolutionTimeSeconds: Number(stats.avg_resolution_time_seconds ?? 0),
    slaBreachCount: Number(stats.sla_breach_count ?? stats.slaBreachCount ?? 0),
    slaBreachRate: Number(stats.sla_breach_rate ?? stats.slaBreachRate ?? 0),
    avgResponseTimeSeconds: Number(stats.avg_response_time_seconds ?? stats.avgResponseTimeSeconds ?? 0),
    topDangerousZones: Array.isArray(stats.top_dangerous_zones) ? stats.top_dangerous_zones.map((zone: any) => ({
      zone: String(zone.zone ?? 'Unassigned'),
      incidentCount: Number(zone.incident_count ?? zone.incidentCount ?? 0),
      riskScore: Number(zone.risk_score ?? zone.riskScore ?? 0),
    })) : [],
    recurringHazards: Array.isArray(stats.recurring_hazards) ? stats.recurring_hazards.map((hazard: any) => ({
      zone: String(hazard.zone ?? 'Unassigned'),
      classification: String(hazard.classification ?? 'Hazard'),
      count: Number(hazard.count ?? 0),
    })) : [],
    weeklySummary: stats.weekly_summary ? {
      incidents: Number(stats.weekly_summary.incidents ?? 0),
      previousIncidents: Number(stats.weekly_summary.previous_incidents ?? 0),
      resolved: Number(stats.weekly_summary.resolved ?? 0),
      delta: Number(stats.weekly_summary.delta ?? 0),
    } : undefined,
  };
}

function toFrontendTimeSeriesPoint(point: any): AnalyticsTimeSeriesPoint {
  return {
    date: String(point.date ?? ''),
    count: Number(point.count ?? 0),
  };
}

function toFrontendDistributionPoint(point: any): AnalyticsDistributionPoint {
  return {
    name: String(point.type ?? point.severity ?? point.zone ?? point.name ?? 'Other'),
    count: Number(point.count ?? 0),
  };
}

function toFrontendSystemHealth(data: any): SystemHealthSnapshot {
  const summary = data?.summary ?? {};
  return {
    generatedAt: Number(data?.generated_at ?? Date.now() / 1000),
    summary: {
      backend: String(summary.backend ?? 'unknown'),
      database: String(summary.database ?? 'unknown'),
      redis: String(summary.redis ?? 'unknown'),
      activeWorkers: Number(summary.active_workers ?? 0),
      activeJobs: Number(summary.active_jobs ?? 0),
      onlineCameras: Number(summary.online_cameras ?? 0),
      totalCameras: Number(summary.total_cameras ?? 0),
      globalFps: Number(summary.global_fps ?? 0),
      cpuLoadPercent: Number(summary.cpu_load_percent ?? 0),
      loadAverage1m: Number(summary.load_average_1m ?? 0),
      diskUsedBytes: Number(summary.disk_used_bytes ?? 0),
      diskTotalBytes: Number(summary.disk_total_bytes ?? 0),
      diskUsedPercent: Number(summary.disk_used_percent ?? 0),
      dbLatencyMs: summary.db_latency_ms ?? null,
      wsActiveConnections: Number(summary.ws_active_connections ?? 0),
      incidentsLast60s: Number(summary.incidents_last_60s ?? 0),
      rateLimitedLast60s: Number(summary.rate_limited_last_60s ?? 0),
    },
    workers: Array.isArray(data?.workers) ? data.workers.map((worker: any) => ({
      id: String(worker.id ?? ''),
      name: String(worker.name ?? worker.id ?? 'Edge Worker'),
      status: String(worker.status ?? 'unknown'),
      hostname: worker.hostname ?? null,
      gpuId: worker.gpu_id ?? null,
      queue: worker.queue ?? null,
      capacity: Number(worker.capacity ?? 0),
      activeJobs: Number(worker.active_jobs ?? 0),
      loadPercent: Number(worker.load_percent ?? 0),
      latencyMs: worker.latency_ms ?? null,
      lastSeenSeconds: worker.last_seen_seconds ?? null,
    })) : [],
    cameras: Array.isArray(data?.cameras) ? data.cameras.map((camera: any) => ({
      id: String(camera.id ?? ''),
      name: String(camera.name ?? camera.id ?? 'Camera'),
      status: String(camera.status ?? 'unknown'),
      zone: camera.zone ?? null,
      fps: Number(camera.fps ?? 0),
      health: Number(camera.health ?? 0),
      sourceName: camera.source_name ?? null,
      running: Boolean(camera.running),
      queued: Boolean(camera.queued),
      workerId: camera.worker_id ?? null,
      workerGpuId: camera.worker_gpu_id ?? null,
      startedAt: camera.started_at ?? null,
      lastError: camera.last_error ?? null,
    })) : [],
  };
}

function toBackendAlert(alert: Partial<Alert>): any {
  const body: any = { ...alert };
  if (alert.incidentId !== undefined) {
    body.incident_id = alert.incidentId;
    delete body.incidentId;
  }
  if (alert.timestamp !== undefined) {
    body.occurred_at = alert.timestamp;
    delete body.timestamp;
  }
  if (alert.cameraId !== undefined) {
    body.camera_id = alert.cameraId;
    delete body.cameraId;
  }
  if (alert.cameraName !== undefined) {
    body.camera_name = alert.cameraName;
    delete body.cameraName;
  }
  if (alert.workerId !== undefined) {
    body.worker_id = alert.workerId;
    delete body.workerId;
  }
  if (alert.workerGpuId !== undefined) {
    body.worker_gpu_id = alert.workerGpuId;
    delete body.workerGpuId;
  }
  if (alert.areaId !== undefined) {
    body.area_id = alert.areaId;
    delete body.areaId;
  }
  if (alert.areaName !== undefined) {
    body.area_name = alert.areaName;
    delete body.areaName;
  }
  if (alert.zoneId !== undefined) {
    body.zone_id = alert.zoneId;
    delete body.zoneId;
  }
  if (alert.zoneName !== undefined) {
    body.zone_name = alert.zoneName;
    delete body.zoneName;
  }
  if (alert.locationDescription !== undefined) {
    body.location_description = alert.locationDescription;
    delete body.locationDescription;
  }
  if (alert.videoEvidence !== undefined) {
    body.video_evidence = alert.videoEvidence;
    delete body.videoEvidence;
  }
  if (alert.eventFrame !== undefined) {
    body.event_frame = alert.eventFrame;
    delete body.eventFrame;
  }
  if (alert.trackId !== undefined) {
    body.track_id = alert.trackId;
    delete body.trackId;
  }
  return body;
}

// ═══════════════════════════════════════════════════════════════════════════
// ALERTS
// ═══════════════════════════════════════════════════════════════════════════

export const AlertsAPI = {
  getAll: async (): Promise<Alert[]> => {
    const data = await request<any[]>('/api/alerts/all');
    return data.map(toFrontendAlert);
  },

  update: async (id: string, changes: Partial<Alert>): Promise<Alert> => {
    const data = await request<any>(`/api/alerts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(toBackendAlert(changes)),
    });
    return toFrontendAlert(data);
  },

  getEvents: async (id: string): Promise<AlertEvent[]> => {
    const data = await request<any[]>(`/api/alerts/${id}/events`);
    return Array.isArray(data) ? data.map(toFrontendAlertEvent) : [];
  },

  getById: async (id: string): Promise<Alert> => {
    const data = await request<any>(`/api/alerts/${id}`);
    return toFrontendAlert(data);
  },

  create: async (alert: Alert): Promise<Alert> => {
    const data = await request<any>('/api/alerts', {
      method: 'POST',
      body: JSON.stringify(toBackendAlert(alert)),
    });
    return toFrontendAlert(data);
  },

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
    const body: any = { ...camera, is_privacy_mode: camera.isPrivacyMode };
    if (camera.areaId !== undefined) {
      body.area_id = camera.areaId;
      delete body.areaId;
    }
    if (camera.areaName !== undefined) {
      body.area_name = camera.areaName;
      delete body.areaName;
    }
    if (camera.zoneId !== undefined) {
      body.zone_id = camera.zoneId;
      delete body.zoneId;
    }
    if (camera.zoneName !== undefined) {
      body.zone_name = camera.zoneName;
      delete body.zoneName;
    }
    if (camera.locationDescription !== undefined) {
      body.location_description = camera.locationDescription;
      delete body.locationDescription;
    }
    if (camera.supportedAiCapabilities !== undefined) {
      body.supported_ai_capabilities = camera.supportedAiCapabilities;
      delete body.supportedAiCapabilities;
    }
    if (camera.severityProfile !== undefined) {
      body.severity_profile = camera.severityProfile;
      delete body.severityProfile;
    }
    if (camera.mediamtxPath !== undefined) {
      body.mediamtx_path = camera.mediamtxPath;
      delete body.mediamtxPath;
    }
    if (camera.deviceIndex !== undefined) {
      body.device_index = camera.deviceIndex;
      delete body.deviceIndex;
    }
    const data = await request<any>('/api/cameras', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    return toFrontendCamera(data);
  },

  uploadAndCreate: (
    fields: {
      file: File;
      name: string;
      areaName: string;
      zoneName: string;
      locationDescription?: string;
    },
    onProgress?: (percent: number) => void,
  ): Promise<Camera> => {
    return new Promise((resolve, reject) => {
      const token = getToken();
      const fd = new FormData();
      fd.append('file', fields.file);
      fd.append('name', fields.name);
      fd.append('zone', `${fields.areaName} / ${fields.zoneName}`);
      fd.append('area_name', fields.areaName);
      fd.append('zone_name', fields.zoneName);
      if (fields.locationDescription) fd.append('location_description', fields.locationDescription);

      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${BASE_URL}/api/cameras/upload`);
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.upload.onprogress = (e) => {
        if (onProgress && e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(toFrontendCamera(JSON.parse(xhr.responseText)));
          } catch (err) {
            reject(err);
          }
        } else {
          let detail = `Upload failed: HTTP ${xhr.status}`;
          try {
            const parsed = JSON.parse(xhr.responseText);
            if (parsed?.detail) detail = parsed.detail;
          } catch { /* ignore */ }
          reject(new Error(detail));
        }
      };
      xhr.onerror = () => reject(new Error('Network error during upload'));
      xhr.send(fd);
    });
  },

  update: async (id: string, changes: Partial<Camera>): Promise<Camera> => {
    const body: any = { ...changes };
    if (changes.isPrivacyMode !== undefined) {
      body.is_privacy_mode = changes.isPrivacyMode;
      delete body.isPrivacyMode;
    }
    if (changes.areaId !== undefined) {
      body.area_id = changes.areaId;
      delete body.areaId;
    }
    if (changes.areaName !== undefined) {
      body.area_name = changes.areaName;
      delete body.areaName;
    }
    if (changes.zoneId !== undefined) {
      body.zone_id = changes.zoneId;
      delete body.zoneId;
    }
    if (changes.zoneName !== undefined) {
      body.zone_name = changes.zoneName;
      delete body.zoneName;
    }
    if (changes.locationDescription !== undefined) {
      body.location_description = changes.locationDescription;
      delete body.locationDescription;
    }
    if (changes.supportedAiCapabilities !== undefined) {
      body.supported_ai_capabilities = changes.supportedAiCapabilities;
      delete body.supportedAiCapabilities;
    }
    if (changes.severityProfile !== undefined) {
      body.severity_profile = changes.severityProfile;
      delete body.severityProfile;
    }
    if (changes.mediamtxPath !== undefined) {
      body.mediamtx_path = changes.mediamtxPath;
      delete body.mediamtxPath;
    }
    if (changes.deviceIndex !== undefined) {
      body.device_index = changes.deviceIndex;
      delete body.deviceIndex;
    }
    const data = await request<any>(`/api/cameras/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
    return toFrontendCamera(data);
  },

  /**
   * Returns cameras mapped into the DemoVideo-shaped contract that
   * LiveMonitoring consumes for its source grid. For file sources the
   * streamUrl is the HTTP video endpoint with auth token; for live
   * sources it falls back to the WS AI stream URL.
   */
  toSourceCards: async (): Promise<DemoVideo[]> => {
    const cameras = await CamerasAPI.getAll();
    return cameras.map((cam): DemoVideo => {
      const sourceType: CameraSourceType =
        (cam.source_type as CameraSourceType) ?? 'rtsp';
      const isFile = sourceType === 'file';
      const streamUrl = isFile && cam.stream_url
        ? appendAuthToken(`/api/media/videos/${cam.stream_url}`)
        : getAIStreamUrl(cam.id);
      return {
        id: cam.id,
        cameraId: cam.id,
        name: cam.name,
        fileName: cam.stream_url || '',
        zone: cam.zone || cam.zoneName || '',
        description: cam.locationDescription || '',
        streamUrl,
        sourceType,
        type: sourceType === 'file' ? 'upload' : undefined,
      };
    });
  },

  delete: (id: string) =>
    request<void>(`/api/cameras/${id}`, { method: 'DELETE' }),

  startStream: (id: string) =>
    request<any>(`/api/cameras/${id}/start`, { method: 'POST' }),

  stopStream: (id: string) =>
    request<any>(`/api/cameras/${id}/stop`, { method: 'POST' }),
};

export const SafetyZonesAPI = {
  listForCamera: async (cameraId: string): Promise<CameraSafetyZone[]> => {
    const data = await request<any[]>(`/api/cameras/${encodeURIComponent(cameraId)}/safety-zones`);
    return data.map(toFrontendSafetyZone);
  },

  create: async (cameraId: string, zone: Partial<CameraSafetyZone>): Promise<CameraSafetyZone> => {
    const data = await request<any>(`/api/cameras/${encodeURIComponent(cameraId)}/safety-zones`, {
      method: 'POST',
      body: JSON.stringify(toBackendSafetyZone(zone)),
    });
    return toFrontendSafetyZone(data);
  },

  update: async (zoneId: string, zone: Partial<CameraSafetyZone>): Promise<CameraSafetyZone> => {
    const data = await request<any>(`/api/safety-zones/${encodeURIComponent(zoneId)}`, {
      method: 'PATCH',
      body: JSON.stringify(toBackendSafetyZone(zone)),
    });
    return toFrontendSafetyZone(data);
  },

  setEnabled: async (zoneId: string, enabled: boolean): Promise<CameraSafetyZone> => {
    const data = await request<any>(`/api/safety-zones/${encodeURIComponent(zoneId)}/enabled`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    });
    return toFrontendSafetyZone(data);
  },

  delete: (zoneId: string) =>
    request<void>(`/api/safety-zones/${encodeURIComponent(zoneId)}`, { method: 'DELETE' }),

  eventsForCamera: async (cameraId: string): Promise<SafetyZoneEvent[]> => {
    const data = await request<any[]>(`/api/cameras/${encodeURIComponent(cameraId)}/safety-zone-events`);
    return data.map(toFrontendSafetyZoneEvent);
  },

  statsForCamera: async (cameraId: string): Promise<SafetyZoneStats[]> => {
    const data = await request<any[]>(`/api/cameras/${encodeURIComponent(cameraId)}/safety-zone-stats`);
    return data.map(toFrontendSafetyZoneStats);
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// INCIDENTS
// ═══════════════════════════════════════════════════════════════════════════

export const IncidentsAPI = {
  getAll: async (options: RequestInit = {}, view?: 'active' | 'history'): Promise<Incident[]> => {
    const suffix = view ? `?view=${encodeURIComponent(view)}` : '';
    const data = await request<any[]>(`/api/incidents/all${suffix}`, options);
    return data.map(toFrontendIncident);
  },

  getById: async (id: string): Promise<Incident> => {
    const data = await request<any>(`/api/incidents/${id}`);
    return toFrontendIncident(data);
  },

  create: async (incident: Incident): Promise<Incident> => {
    const body = {
      id:                incident.id,
      zone:              incident.zone,
      classification:    incident.classification,
      severity:          incident.severity,
      camera_id:         incident.cameraId,
      camera_name:       incident.cameraName,
      worker_id:         incident.workerId,
      worker_gpu_id:     incident.workerGpuId,
      status:            incident.status,
      started_at:        incident.startedAt,
      validated_at:      incident.validatedAt,
      acknowledged_at:   incident.acknowledgedAt,
      acknowledged_by:   incident.acknowledgedBy,
      resolved_at:       incident.resolvedAt,
      resolved_by:       incident.resolvedBy,
      archived_at:       incident.archivedAt,
      sla_breached_at:   incident.slaBreachedAt,
      sla_ack_breached_at: incident.slaAckBreachedAt,
      sla_resolution_breached_at: incident.slaResolutionBreachedAt,
      sla_breach_count:  incident.slaBreachCount,
      duration_seconds:  incident.durationSeconds,
      escalation_count:  incident.escalationCount,
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

  updateStatus: async (id: string, status: Incident['status'], note?: string): Promise<Incident> => {
    const data = await request<any>(`/api/incidents/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, note }),
    });
    return toFrontendIncident(data);
  },

  acknowledge: async (id: string): Promise<Incident> => {
    const data = await request<any>(`/api/incidents/${id}/acknowledge`, { method: 'PATCH' });
    return toFrontendIncident(data);
  },

  resolve: async (id: string): Promise<Incident> => {
    const data = await request<any>(`/api/incidents/${id}/resolve`, { method: 'PATCH' });
    return toFrontendIncident(data);
  },

  archive: async (id: string): Promise<Incident> => {
    const data = await request<any>(`/api/incidents/${id}/archive`, { method: 'PATCH' });
    return toFrontendIncident(data);
  },

  reopen: async (id: string): Promise<Incident> => {
    const data = await request<any>(`/api/incidents/${id}/reopen`, { method: 'PATCH' });
    return toFrontendIncident(data);
  },

  escalate: async (id: string): Promise<Incident> => {
    const data = await request<any>(`/api/incidents/${id}/escalate`, { method: 'PATCH' });
    return toFrontendIncident(data);
  },

  falsePositive: async (id: string): Promise<Incident> => {
    const data = await request<any>(`/api/incidents/${id}/false-positive`, { method: 'PATCH' });
    return toFrontendIncident(data);
  },

  getEvents: async (id: string): Promise<IncidentEvent[]> => {
    const data = await request<any[]>(`/api/incidents/${id}/events`);
    return Array.isArray(data) ? data.map(toFrontendIncidentEvent) : [];
  },

  checkSla: async (id: string): Promise<Incident> => {
    const data = await request<any>(`/api/incidents/${id}/sla/check`, { method: 'POST' });
    return toFrontendIncident(data);
  },

  checkAllSla: () =>
    request<{ checked: number; breached: number }>('/api/incidents/sla/check', { method: 'POST' }),
};

// ═══════════════════════════════════════════════════════════════════════════
// ERGONOMICS
// ═══════════════════════════════════════════════════════════════════════════

export const ErgonomicsAPI = {
  getStats: async (days: number = 7): Promise<ErgonomicStats> => {
    const data = await request<any>(`/api/ergonomics/stats?days=${encodeURIComponent(String(days))}`);
    return toFrontendErgonomicStats(data);
  },

  getRecords: async (limit: number = 500): Promise<ErgonomicRecord[]> => {
    const pageSize = Math.min(Math.max(limit, 1), 200);
    const data = await request<any>(`/api/ergonomics?limit=${encodeURIComponent(String(pageSize))}`);
    const items = Array.isArray(data?.items) ? data.items : [];
    return items.map(toFrontendErgonomicRecord);
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// ANALYTICS
// ═══════════════════════════════════════════════════════════════════════════

export const AnalyticsAPI = {
  getStats: async (): Promise<AnalyticsStats> => {
    const data = await request<any>('/api/stats');
    return toFrontendAnalyticsStats(data);
  },

  getIncidentTimeSeries: async (days: number = 7): Promise<AnalyticsTimeSeriesPoint[]> => {
    const data = await request<any[]>(`/api/analytics/incidents/time-series?days=${encodeURIComponent(String(days))}`);
    return Array.isArray(data) ? data.map(toFrontendTimeSeriesPoint) : [];
  },

  getAlertsByType: async (): Promise<AnalyticsDistributionPoint[]> => {
    const data = await request<any[]>('/api/analytics/alerts/by-type');
    return Array.isArray(data) ? data.map(toFrontendDistributionPoint) : [];
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// SYSTEM HEALTH
// ═══════════════════════════════════════════════════════════════════════════

export const SystemHealthAPI = {
  getSnapshot: async (): Promise<SystemHealthSnapshot> => {
    const data = await request<any>('/api/monitoring/system-health');
    return toFrontendSystemHealth(data);
  },
};

export const NotificationsAPI = {
  getAll: async (): Promise<NotificationRecord[]> => {
    const data = await request<any>('/api/notifications?limit=50');
    const items = Array.isArray(data?.items) ? data.items : (Array.isArray(data) ? data : []);
    return items.map(toFrontendNotification);
  },

  markRead: (ids: string[]) =>
    request<void>('/api/notifications/mark-read', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),

  markAllRead: () =>
    request<void>('/api/notifications/mark-all-read', { method: 'POST' }),

  delete: (id: string) =>
    request<void>(`/api/notifications/${encodeURIComponent(id)}`, { method: 'DELETE' }),
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
      trends?: Array<{ date: string; count: number }>;
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
  getAll: async (options: RequestInit = {}) => {
    const data = await request<any[]>('/api/media/videos', options);
    return data.map(toFrontendDemoVideo);
  },

  delete: (fileName: string) =>
    request<void>(`/api/media/videos/${encodeURIComponent(fileName)}`, { method: 'DELETE' }),

  rename: async (fileName: string, nextFileName: string) => {
    const data = await request<any>(`/api/media/videos/${encodeURIComponent(fileName)}`, {
      method: 'PATCH',
      body: JSON.stringify({ file_name: nextFileName }),
    });
    return toFrontendDemoVideo(data);
  },
};

export const JobsAPI = {
  status: async (options: RequestInit = {}) => {
    const data = await request<any>('/api/jobs/status', options);
    return toFrontendJobStatus(data);
  },

  start: async (sourceName: string, cameraId: string = 'cam_01') => {
    const data = await request<any>('/api/jobs/start', {
      method: 'POST',
      body: JSON.stringify({ source_name: sourceName, camera_id: cameraId }),
    });
    return toFrontendJobStatus(data);
  },

  stop: async (cameraId?: string) => {
    const query = cameraId ? `?camera_id=${encodeURIComponent(cameraId)}` : '';
    const data = await request<any>(`/api/jobs/stop${query}`, {
      method: 'POST',
    });
    return toFrontendJobStatus(data);
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// UPLOAD
// ═══════════════════════════════════════════════════════════════════════════

export const UploadAPI = {
  uploadVideo: async (file: File): Promise<any> => {
    const token = getToken();
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${BASE_URL}/api/media/upload`, {
      method: 'POST',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: formData,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail?.detail || `Upload failed: HTTP ${res.status}`);
    }
    return res.json();
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// AI STREAM
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Build WebSocket URL for AI-annotated frame stream.
 */
export function getAIStreamUrl(cameraId: string): string {
  const token = getToken();
  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${WS_BASE_URL}/ws/stream/${encodeURIComponent(cameraId)}${tokenParam}`;
}
