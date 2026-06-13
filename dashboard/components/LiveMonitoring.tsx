import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
	AlertTriangle,
	CheckSquare,
	Clock,
	Cpu,
	Eye,
	EyeOff,
	FastForward,
	Grid,
	Layers,
	Loader2,
	Maximize2,
	Pause,
	Play,
	Radio,
	RefreshCw,
	Rewind,
	ShieldCheck,
	Square,
	Video,
	Wifi,
	WifiOff,
	X,
} from 'lucide-react';
import {
	CamerasAPI,
	IncidentsAPI,
	JobsAPI,
	SafetyZonesAPI,
	WS_BASE_URL,
	getAIStreamUrl,
	getAuthToken,
} from '../api';
import { CameraSafetyZone, DemoVideo, Incident, JobStatus } from '../types';
import { useLanguage } from '../contexts/LanguageContext';

const layoutButtonClass = (active: boolean) =>
	`p-2 rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange ${
		active ? 'bg-zinc-800 text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-300'
	}`;

const severityStyle: Record<string, string> = {
	High: 'text-red-400 border-red-500/30 bg-red-500/10',
	Medium: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
	Low: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
};

const isOverspeedIncident = (payload: any) =>
	/overspeed/i.test([
		payload?.classification,
		payload?.root_cause,
		payload?.rootCause,
		payload?.description,
		payload?.type,
	].map(value => String(value ?? '')).join(' '));

const normalizeIncident = (payload: any): Incident => ({
	id: String(payload?.id ?? `INC-${Date.now()}`),
	zone: String(payload?.zone ?? 'Unknown zone'),
	classification: isOverspeedIncident(payload)
		? 'Forklift Overspeed'
		: String(payload?.classification ?? 'Unclassified'),
	severity: payload?.severity === 'Critical' || payload?.severity === 'High' || payload?.severity === 'Medium' || payload?.severity === 'Low'
		? payload.severity
		: 'Low',
	cameraId: payload?.camera_id ?? payload?.cameraId ?? null,
	cameraName: payload?.camera_name ?? payload?.cameraName ?? null,
	workerId: payload?.worker_id ?? payload?.workerId ?? null,
	workerGpuId: payload?.worker_gpu_id ?? payload?.workerGpuId ?? null,
	status: payload?.status ?? 'New',
	rootCause: String(payload?.root_cause ?? payload?.rootCause ?? 'Under Investigation'),
	correctiveAction: String(payload?.corrective_action ?? payload?.correctiveAction ?? 'Pending Review'),
	createdAt: String(payload?.created_at ?? payload?.createdAt ?? new Date().toISOString()),
});

const formatTime = (value: string | null | undefined) => {
	if (!value) return 'Pending time';
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return 'Pending time';
	return date.toLocaleString([], {
		month: 'short',
		day: '2-digit',
		hour: '2-digit',
		minute: '2-digit',
	});
};

const MetadataPill = ({ label, value }: { label: string; value?: string | null }) => {
	if (!value) return null;
	return (
		<span className="inline-flex items-center rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[9px] font-mono uppercase tracking-wide text-zinc-400">
			{label}: {value}
		</span>
	);
};

const StatusBadge = ({
	state,
}: {
	state: 'connected' | 'connecting' | 'disconnected';
}) => {
	const stateClass = {
		connected: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
		connecting: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
		disconnected: 'border-red-500/30 bg-red-500/10 text-red-300',
	}[state];
	const Icon = state === 'connected' ? Wifi : state === 'connecting' ? Radio : WifiOff;

	return (
		<div className={`flex items-center gap-2 rounded-full border px-3 py-1 text-[10px] font-bold uppercase tracking-wider ${stateClass}`}>
			<Icon size={12} aria-hidden="true" />
			<span>WS {state}</span>
		</div>
	);
};

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

type ViewMode = 'file' | 'ai' | 'multi_ai';
type AiViewState = 'stopped' | 'starting' | 'running' | 'no_frames' | 'error';

interface MultiAiStreamState {
	videoId: string;
	cameraId: string;
	state: AiViewState;
	error?: string | null;
}

const makeMultiCameraId = (video: DemoVideo, index: number) => {
	const safeId = video.id.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 28) || `source_${index + 1}`;
	return `multi_${index + 1}_${safeId}`;
};

const SourcePreview: React.FC<{ video: DemoVideo }> = ({ video }) => {
	const canvasRef = useRef<HTMLCanvasElement | null>(null);
	const videoRef = useRef<HTMLVideoElement | null>(null);
	const timeoutRef = useRef<number | null>(null);
	const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
	const thumbnail = video.thumbnail;
	const isFile = !video.sourceType || video.sourceType === 'file';
	// <video>-based capture only works for file sources (live cameras have WS URLs)
	const previewSrc = !thumbnail && isFile ? video.streamUrl : '';

	const drawPreview = useCallback(() => {
		const element = videoRef.current;
		const canvas = canvasRef.current;
		if (!element || !canvas || element.readyState < 2 || element.videoWidth === 0 || element.videoHeight === 0) {
			return;
		}
		canvas.width = element.videoWidth;
		canvas.height = element.videoHeight;
		const context = canvas.getContext('2d');
		if (!context) return;
		try {
			context.drawImage(element, 0, 0, canvas.width, canvas.height);
			if (timeoutRef.current !== null) {
				window.clearTimeout(timeoutRef.current);
				timeoutRef.current = null;
			}
			setState('ready');
		} catch {
			setState('error');
		}
	}, []);

	useEffect(() => {
		if (thumbnail) {
			setState('ready');
			return undefined;
		}
		setState('loading');
		if (timeoutRef.current !== null) {
			window.clearTimeout(timeoutRef.current);
		}
		if (!previewSrc) {
			setState('error');
			return undefined;
		}
		timeoutRef.current = window.setTimeout(() => {
			setState((current) => (current === 'ready' ? current : 'error'));
		}, 7000);
		window.requestAnimationFrame(() => videoRef.current?.load());
		return () => {
			if (timeoutRef.current !== null) {
				window.clearTimeout(timeoutRef.current);
				timeoutRef.current = null;
			}
		};
	}, [previewSrc, thumbnail]);

	if (thumbnail) {
		return (
			<div className="relative aspect-video overflow-hidden bg-zinc-950">
				<img
					src={thumbnail}
					alt={video.name}
					className="h-full w-full object-cover opacity-80 transition-opacity group-hover:opacity-100"
					loading="lazy"
					onError={() => setState('error')}
				/>
			</div>
		);
	}

	return (
		<div className="relative aspect-video overflow-hidden bg-zinc-950">
			<canvas
				ref={canvasRef}
				className={`h-full w-full object-cover transition-opacity ${state === 'ready' ? 'opacity-75 group-hover:opacity-90' : 'opacity-0'}`}
				aria-hidden="true"
			/>
			{previewSrc && (
				<video
					ref={videoRef}
					src={previewSrc}
					className="pointer-events-none absolute inset-0 h-full w-full object-cover opacity-0"
					muted
					playsInline
					preload="auto"
					onLoadedMetadata={(event) => {
						const element = event.currentTarget;
						if (Number.isFinite(element.duration) && element.duration > 0) {
							const previewTime = Math.min(1.25, Math.max(0.1, element.duration * 0.12));
							if (Math.abs(element.currentTime - previewTime) > 0.05) {
								element.currentTime = previewTime;
							} else {
								drawPreview();
							}
						} else {
							drawPreview();
						}
					}}
					onLoadedData={drawPreview}
					onCanPlay={drawPreview}
					onSeeked={drawPreview}
					onError={() => setState('error')}
				/>
			)}
			{state !== 'ready' && (
				<div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-zinc-950 text-zinc-600">
					{state === 'loading' ? <Loader2 size={18} className="animate-spin" aria-hidden="true" /> : <Video size={22} aria-hidden="true" />}
					<span className="px-3 text-center text-[9px] font-bold uppercase tracking-wide text-zinc-500">
						{state === 'loading' ? video.name : 'No preview available'}
					</span>
				</div>
			)}
		</div>
	);
};

const SafetyZonesOverlay: React.FC<{ zones: CameraSafetyZone[] }> = ({ zones }) => {
	if (!zones.length) return null;
	const ref = zones[0];
	const sw = ref.sourceWidth || 1280;
	const sh = ref.sourceHeight || 720;
	return (
		<svg
			viewBox={`0 0 ${sw} ${sh}`}
			preserveAspectRatio="xMidYMid meet"
			className="pointer-events-none absolute inset-0 h-full w-full"
			aria-hidden="true"
		>
			{zones.filter(z => z.enabled && z.polygon.length >= 3).map((zone) => {
				const points = zone.polygon.map(p => `${p.x},${p.y}`).join(' ');
				const labelPoint = zone.polygon[0];
				return (
					<g key={zone.id}>
						<polygon
							points={points}
							fill={`${zone.color}26`}
							stroke={zone.color}
							strokeWidth={4}
							strokeDasharray={zone.zoneType === 'allowed' ? '0' : '14 8'}
						/>
						<rect
							x={labelPoint.x + 6}
							y={labelPoint.y - 30}
							width={(zone.name.length + 2) * 11}
							height={26}
							rx={6}
							fill="rgba(0,0,0,0.78)"
							stroke={zone.color}
							strokeWidth={1.5}
						/>
						<text
							x={labelPoint.x + 16}
							y={labelPoint.y - 12}
							fill={zone.color}
							fontSize={16}
							fontWeight={700}
							fontFamily="ui-monospace, SFMono-Regular, monospace"
						>
							{zone.name}
						</text>
					</g>
				);
			})}
		</svg>
	);
};

const SOURCE_TYPE_PILL: Record<string, { label: string; cls: string }> = {
	rtsp:     { label: 'RTSP',     cls: 'border-sky-500/30 bg-sky-500/15 text-sky-300' },
	mediamtx: { label: 'MEDIAMTX', cls: 'border-purple-500/30 bg-purple-500/15 text-purple-300' },
	file:     { label: 'FILE',     cls: 'border-amber-500/30 bg-amber-500/15 text-amber-300' },
	webcam:   { label: 'WEBCAM',   cls: 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300' },
	webrtc:   { label: 'WEBRTC',   cls: 'border-zinc-500/30 bg-zinc-500/15 text-zinc-300' },
};

const DemoVideoCard: React.FC<{
	video: DemoVideo;
	isActive: boolean;
	onClick: () => void;
	isMultiSelect?: boolean;
	isMultiSelected?: boolean;
}> = ({ video, isActive, onClick, isMultiSelect = false, isMultiSelected = false }) => {
	const { t } = useLanguage();
	const pill = SOURCE_TYPE_PILL[video.sourceType || 'rtsp'] || SOURCE_TYPE_PILL.rtsp;
	return (
		<div
			onClick={onClick}
			onKeyDown={(event) => {
				if (event.key === 'Enter' || event.key === ' ') {
					event.preventDefault();
					onClick();
				}
			}}
			role="button"
			tabIndex={0}
			aria-pressed={isMultiSelect ? isMultiSelected : isActive}
			className={`group relative min-h-32 overflow-hidden rounded-lg border text-start transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange ${
				isActive || isMultiSelected ? 'border-vs-orange shadow-[0_0_0_1px_rgba(249,115,22,0.45)]' : 'border-zinc-800 hover:border-zinc-700'
			}`}
		>
			<SourcePreview video={video} />
			<div className="absolute inset-0 flex flex-col justify-between bg-gradient-to-t from-black/80 via-black/10 to-black/40 p-3">
				<div className="flex items-start justify-between gap-2">
					<div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/75 px-2 py-1">
						<span className="h-2 w-2 rounded-full bg-emerald-500" />
						<span className="font-mono text-[10px] font-bold tracking-wider text-white">
							{t('live')}
						</span>
					</div>
					<span className={`max-w-[52%] truncate rounded-full border px-2 py-1 text-[9px] font-bold uppercase tracking-wider ${isActive || isMultiSelected ? 'border-vs-orange/30 bg-vs-orange/10 text-vs-orange' : 'border-white/10 bg-black/50 text-zinc-400'}`}>
						{video.zone}
					</span>
				</div>
				{isMultiSelect && (
					<div className={`absolute left-3 top-11 flex h-8 w-8 items-center justify-center rounded-md border bg-black/75 ${
						isMultiSelected ? 'border-vs-orange/50 text-vs-orange' : 'border-white/10 text-zinc-500'
					}`} aria-hidden="true">
						{isMultiSelected ? <CheckSquare size={15} /> : <Square size={15} />}
					</div>
				)}
				<span className={`absolute right-3 top-11 rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-wider ${pill.cls}`}>
					{pill.label}
				</span>
				<div>
					<p className="truncate text-sm font-bold text-white">{video.name}</p>
					<p className="mt-1 line-clamp-2 text-[10px] text-zinc-300">{video.description}</p>
				</div>
			</div>
		</div>
	);
};

const IncidentItem: React.FC<{ incident: Incident }> = ({ incident }) => {
	const { t } = useLanguage();
	return (
		<div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 transition-colors hover:border-zinc-700">
			<div className="flex items-start justify-between gap-3">
				<div className="min-w-0">
					<p className="truncate text-sm font-semibold text-white">{incident.classification}</p>
					<p className="mt-1 truncate text-[10px] font-mono text-zinc-500">
						{incident.zone} • {formatTime(incident.createdAt)}
					</p>
				</div>
				<span className={`shrink-0 rounded-full border px-2 py-1 text-[9px] font-bold uppercase tracking-wider ${severityStyle[incident.severity] ?? 'border-zinc-700 bg-zinc-800 text-zinc-300'}`}>
					{t(incident.severity.toLowerCase() as any)}
				</span>
			</div>
			<div className="mt-3 flex flex-wrap gap-2">
				<MetadataPill label="Camera" value={incident.cameraName ?? incident.cameraId} />
				<MetadataPill label="Worker" value={incident.workerId} />
				<MetadataPill label="GPU" value={incident.workerGpuId} />
			</div>
			<p className="mt-3 text-xs leading-relaxed text-zinc-400">{incident.rootCause}</p>
			<p className="mt-2 text-[11px] leading-relaxed text-zinc-500">{incident.correctiveAction}</p>
		</div>
	);
};

const EmptySourceState = ({ message }: { message: string }) => (
	<div className="flex h-full min-h-80 flex-col items-center justify-center gap-4 p-6 text-center text-zinc-600">
		<Video size={48} className="opacity-25" aria-hidden="true" />
		<p className="text-sm font-medium uppercase tracking-wide">{message}</p>
	</div>
);

const LiveMonitoring = () => {
	const { t } = useLanguage();
	const [layout, setLayout] = useState<4 | 9>(4);
	const [viewMode, setViewMode] = useState<ViewMode>('file');
	const [videos, setVideos] = useState<DemoVideo[]>([]);
	const [selectedVideoId, setSelectedVideoId] = useState('');
	const [selectedMultiVideoIds, setSelectedMultiVideoIds] = useState<string[]>([]);
	const [incidents, setIncidents] = useState<Incident[]>([]);
	const [jobStatus, setJobStatus] = useState<JobStatus>({ running: false });
	const [jobBusy, setJobBusy] = useState(false);
	const [jobError, setJobError] = useState<string | null>(null);
	const [videosLoading, setVideosLoading] = useState(true);
	const [incidentsLoading, setIncidentsLoading] = useState(true);
	const [isRefreshingVideos, setIsRefreshingVideos] = useState(false);
	const [isRefreshingIncidents, setIsRefreshingIncidents] = useState(false);
	const [lastUpdated, setLastUpdated] = useState<string | null>(null);
	const [dataError, setDataError] = useState<string | null>(null);
	const [wsState, setWsState] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
	const [aiState, setAiState] = useState<AiViewState>('stopped');
	const [multiAiStates, setMultiAiStates] = useState<Record<string, MultiAiStreamState>>({});

	const wsRef = useRef<WebSocket | null>(null);
	const reconnectTimerRef = useRef<number | null>(null);
	const reconnectAttemptRef = useRef(0);
	const videoPlayerRef = useRef<HTMLVideoElement>(null);
	const aiCanvasRef = useRef<HTMLCanvasElement>(null);
	const fullscreenAiCanvasRef = useRef<HTMLCanvasElement>(null);
	const aiWsRef = useRef<WebSocket | null>(null);
	const multiAiWsRefs = useRef<Record<string, WebSocket>>({});
	const multiAiCanvasRefs = useRef<Record<string, HTMLCanvasElement | null>>({});
	const fullscreenMultiAiCanvasRefs = useRef<Record<string, HTMLCanvasElement | null>>({});
	const [isPlaying, setIsPlaying] = useState(false);
	const [isMaximized, setIsMaximized] = useState(false);
	const [aiSessionActive, setAiSessionActive] = useState(false);
	const [cameraZones, setCameraZones] = useState<CameraSafetyZone[]>([]);
	const [showZones, setShowZones] = useState(true);
	const [multiAiSessionActive, setMultiAiSessionActive] = useState(false);

	const selectedVideo = useMemo(
		() => videos.find((video) => video.id === selectedVideoId) ?? null,
		[videos, selectedVideoId],
	);

	useEffect(() => {
		const cameraId = selectedVideo?.cameraId;
		if (!cameraId) {
			setCameraZones([]);
			return;
		}
		let cancelled = false;
		SafetyZonesAPI.listForCamera(cameraId)
			.then((zones) => { if (!cancelled) setCameraZones(zones); })
			.catch(() => { if (!cancelled) setCameraZones([]); });
		return () => { cancelled = true; };
	}, [selectedVideo?.cameraId]);

	const visibleZones = useMemo(
		() => (showZones ? cameraZones.filter((z) => z.enabled && z.polygon.length >= 3) : []),
		[cameraZones, showZones],
	);
	const selectedMultiVideos = useMemo(
		() => selectedMultiVideoIds
			.map((id) => videos.find((video) => video.id === id))
			.filter(Boolean) as DemoVideo[],
		[selectedMultiVideoIds, videos],
	);
	const multiStreamDescriptors = useMemo(
		() => selectedMultiVideos.map((video, index) => ({
			video,
			cameraId: makeMultiCameraId(video, index),
		})),
		[selectedMultiVideos],
	);
	const multiDescriptorKey = useMemo(
		() => multiStreamDescriptors.map((item) => `${item.video.id}:${item.cameraId}`).join('|'),
		[multiStreamDescriptors],
	);

	const activeCameraId = jobStatus.cameraId || 'cam_01';
	const recentIncidents = useMemo(() => incidents.slice(0, 10), [incidents]);

	const upsertIncident = useCallback((incident: Incident) => {
		setIncidents((previous) => {
			const existingIndex = previous.findIndex((item) => item.id === incident.id);
			if (existingIndex >= 0) {
				const updated = [...previous];
				updated[existingIndex] = incident;
				return updated;
			}
			return [incident, ...previous].slice(0, 1000);
		});
	}, []);

	const loadVideos = useCallback(async (_options: RequestInit = {}) => {
		setIsRefreshingVideos(true);
		try {
			const data = await CamerasAPI.toSourceCards();
			setVideos(data);
			setSelectedVideoId((current) => {
				if (current && data.some((video) => video.id === current)) return current;
				return data[0]?.id || '';
			});
			setSelectedMultiVideoIds((current) => {
				const valid = current.filter((id) => data.some((video) => video.id === id));
				return valid.length > 0 ? valid : data.slice(0, Math.min(2, data.length)).map((video) => video.id);
			});
			setDataError(null);
		} finally {
			setVideosLoading(false);
			setIsRefreshingVideos(false);
		}
	}, []);

	const loadIncidents = useCallback(async (options: RequestInit = {}) => {
		setIsRefreshingIncidents(true);
		try {
			const data = await IncidentsAPI.getAll(options, 'active');
			setIncidents(data.map(normalizeIncident));
			setLastUpdated(new Date().toLocaleTimeString());
			setDataError(null);
		} finally {
			setIncidentsLoading(false);
			setIsRefreshingIncidents(false);
		}
	}, []);

	const loadJobStatus = useCallback(async (options: RequestInit = {}) => {
		const status = await JobsAPI.status(options);
		setJobStatus(status);
	}, []);

	const waitForJobIdle = useCallback(async (timeoutMs = 30000) => {
		const deadline = Date.now() + timeoutMs;
		let latestStatus = await JobsAPI.status();
		while (latestStatus.running && Date.now() < deadline) {
			await sleep(750);
			latestStatus = await JobsAPI.status();
		}
		setJobStatus(latestStatus);
		return !latestStatus.running;
	}, []);

	const drawFrameToCanvases = useCallback((frame: ArrayBuffer, canvases: Array<HTMLCanvasElement | null>) => {
		const blob = new Blob([frame], { type: 'image/jpeg' });
		const imageUrl = URL.createObjectURL(blob);
		const image = new Image();
		image.onload = () => {
			for (const canvas of canvases) {
				if (!canvas) continue;
				const context = canvas.getContext('2d');
				if (!context) continue;
				canvas.width = image.naturalWidth || image.width;
				canvas.height = image.naturalHeight || image.height;
				context.clearRect(0, 0, canvas.width, canvas.height);
				context.imageSmoothingEnabled = true;
				context.imageSmoothingQuality = 'high';
				context.drawImage(image, 0, 0, canvas.width, canvas.height);
			}
			URL.revokeObjectURL(imageUrl);
		};
		image.onerror = () => URL.revokeObjectURL(imageUrl);
		image.src = imageUrl;
	}, []);

	const startJobForVideo = useCallback(async (video: DemoVideo, cameraId = 'cam_01') => {
		const status = await JobsAPI.start(video.fileName, cameraId);
		setJobStatus(status);
		setJobError(null);
		return status;
	}, []);

	const startMonitoring = useCallback(async () => {
		if (jobBusy) return;
		if (viewMode !== 'multi_ai' && !selectedVideo) return;
		if (viewMode === 'multi_ai' && selectedMultiVideos.length === 0) {
			setJobError('Select at least one source for Multi-Camera AI.');
			return;
		}
		setJobBusy(true);
		setJobError(null);
		try {
			if (viewMode === 'file') {
				const player = videoPlayerRef.current;
				if (!player) return;
				await player.play();
				setIsPlaying(true);
				return;
			}
			if (viewMode === 'multi_ai') {
				setAiSessionActive(false);
				setAiState('stopped');
				setMultiAiSessionActive(true);
				const startingStates = Object.fromEntries(
					multiStreamDescriptors.map(({ video, cameraId }) => [
						cameraId,
						{ videoId: video.id, cameraId, state: 'starting' as AiViewState, error: null },
					]),
				);
				setMultiAiStates(startingStates);
				const results = await Promise.allSettled(
					multiStreamDescriptors.map(({ video, cameraId }) => startJobForVideo(video, cameraId)),
				);
				const failed = results
					.map((result, index) => ({ result, descriptor: multiStreamDescriptors[index] }))
					.filter((item) => item.result.status === 'rejected');
				if (failed.length > 0) {
					setMultiAiStates((current) => {
						const next = { ...current };
						for (const item of failed) {
							next[item.descriptor.cameraId] = {
								videoId: item.descriptor.video.id,
								cameraId: item.descriptor.cameraId,
								state: 'error',
								error: (item.result as PromiseRejectedResult).reason?.message ?? 'Failed to start AI stream',
							};
						}
						return next;
					});
					setJobError(`${failed.length} AI stream${failed.length === 1 ? '' : 's'} failed to start.`);
				}
				await loadJobStatus().catch(() => undefined);
				return;
			}
			setAiState('starting');
			setAiSessionActive(true);
			await startJobForVideo(selectedVideo, 'cam_01');
		} catch (error: any) {
			if (viewMode === 'ai') {
				setAiSessionActive(false);
				setAiState('error');
			}
			setJobError(error?.message ?? (viewMode === 'ai' ? 'Failed to start AI worker' : 'Browser blocked video playback. Press Start again or use a supported browser.'));
		} finally {
			setJobBusy(false);
		}
	}, [jobBusy, loadJobStatus, multiStreamDescriptors, selectedMultiVideos.length, selectedVideo, startJobForVideo, viewMode]);

	const stopMonitoring = async () => {
		if (jobBusy) return;
		setJobBusy(true);
		setJobError(null);
		try {
			const player = videoPlayerRef.current;
			if (player) {
				player.pause();
				setIsPlaying(false);
			}
			if (viewMode === 'ai') {
				setAiSessionActive(false);
				setAiState('stopped');
			}
			if (viewMode === 'multi_ai') {
				setMultiAiSessionActive(false);
				for (const ws of Object.values(multiAiWsRefs.current) as WebSocket[]) {
					ws.close();
				}
				multiAiWsRefs.current = {};
				setMultiAiStates((current) => Object.fromEntries(
					Object.entries(current).map(([cameraId, state]) => [cameraId, { ...(state as MultiAiStreamState), state: 'stopped' as AiViewState }]),
				) as Record<string, MultiAiStreamState>);
			}
			if (jobStatus.running) {
				const status = await JobsAPI.stop();
				setJobStatus(status);
				const stopped = await waitForJobIdle();
				if (!stopped) {
					setJobError('Stop requested, but the worker is still shutting down.');
				}
			}
		} catch (error: any) {
			setJobError(error?.message ?? 'Failed to stop worker job');
			if (viewMode === 'ai') {
				setAiSessionActive(false);
				setAiState('error');
			}
			if (viewMode === 'multi_ai') {
				setMultiAiSessionActive(false);
				setMultiAiStates((current) => Object.fromEntries(
					Object.entries(current).map(([cameraId, state]) => [cameraId, { ...(state as MultiAiStreamState), state: 'error' as AiViewState, error: error?.message ?? 'Failed to stop AI stream' }]),
				) as Record<string, MultiAiStreamState>);
			}
		} finally {
			setJobBusy(false);
		}
	};

	const handlePlayPause = async () => {
		const player = videoPlayerRef.current;
		if (!player) return;
		if (player.paused) {
			setJobError('Press Start to begin file playback.');
		} else {
			player.pause();
			setIsPlaying(false);
		}
	};

	const handleSkip = (seconds: number) => {
		const player = videoPlayerRef.current;
		if (!player || Number.isNaN(player.duration)) return;
		player.currentTime = Math.max(0, Math.min(player.duration, player.currentTime + seconds));
	};

	const handleModeChange = useCallback((mode: ViewMode) => {
		setViewMode(mode);
		if (mode !== 'file') {
			videoPlayerRef.current?.pause();
			setIsPlaying(false);
		}
	}, []);

	const handleSelectVideo = useCallback((video: DemoVideo) => {
		if (viewMode === 'multi_ai') {
			setSelectedMultiVideoIds((current) => (
				current.includes(video.id)
					? current.filter((id) => id !== video.id)
					: [...current, video.id]
			));
			return;
		}
		videoPlayerRef.current?.pause();
		setIsPlaying(false);
		setAiSessionActive(false);
		setAiState('stopped');
		setSelectedVideoId(video.id);
		// Live sources can't play through <video>; auto-switch to AI mode.
		if (viewMode === 'file' && video.sourceType && video.sourceType !== 'file') {
			setViewMode('ai');
		}
	}, [viewMode]);

	useEffect(() => {
		const controller = new AbortController();
		loadVideos({ signal: controller.signal }).catch((error) => {
			if (error?.name !== 'AbortError') {
				setVideosLoading(false);
				setDataError('Failed to load video sources from backend.');
			}
		});
		loadIncidents({ signal: controller.signal }).catch((error) => {
			if (error?.name !== 'AbortError') {
				setIncidentsLoading(false);
				setDataError('Failed to load incidents from backend.');
			}
		});
		JobsAPI.stop()
			.then((status) => setJobStatus(status))
			.catch(() => loadJobStatus({ signal: controller.signal }).catch(() => undefined));
		const timer = window.setInterval(() => {
			loadJobStatus().catch(() => undefined);
		}, 5000);
		return () => {
			controller.abort();
			window.clearInterval(timer);
		};
	}, [loadIncidents, loadJobStatus, loadVideos]);

	useEffect(() => {
		let stopped = false;
		const token = getAuthToken();
		if (!token) {
			setWsState('disconnected');
			return undefined;
		}

		const connect = () => {
			if (stopped) return;
			setWsState('connecting');
			const ws = new WebSocket(`${WS_BASE_URL}/ws/incidents?token=${encodeURIComponent(token)}`);
			wsRef.current = ws;

			ws.onopen = () => {
				reconnectAttemptRef.current = 0;
				setWsState('connected');
			};

			ws.onmessage = (event) => {
				try {
					const payload = JSON.parse(event.data);
					if (payload?.type === 'incident_created' && payload?.incident) {
						upsertIncident(normalizeIncident(payload.incident));
						setLastUpdated(new Date().toLocaleTimeString());
					}
				} catch {
					// Ignore malformed event payloads from non-dashboard clients.
				}
			};

			ws.onclose = () => {
				if (stopped) return;
				setWsState('disconnected');
				reconnectAttemptRef.current += 1;
				const backoffMs = Math.min(1000 * reconnectAttemptRef.current, 10000);
				reconnectTimerRef.current = window.setTimeout(connect, backoffMs);
			};

			ws.onerror = () => {
				ws.close();
			};
		};

		connect();

		return () => {
			stopped = true;
			if (reconnectTimerRef.current !== null) {
				window.clearTimeout(reconnectTimerRef.current);
			}
			if (wsRef.current) {
				wsRef.current.close();
				wsRef.current = null;
			}
		};
	}, [upsertIncident]);

	useEffect(() => {
		if (viewMode !== 'ai' || !jobStatus.running || !aiSessionActive) {
			if (viewMode === 'ai' && !jobBusy) setAiState('stopped');
			return undefined;
		}

		const token = getAuthToken();
		if (!token) {
			setAiState('error');
			return undefined;
		}

		let stopped = false;
		let receivedFrame = false;
		let noFrameTimer: number | null = window.setTimeout(() => {
			if (!receivedFrame && !stopped) setAiState('no_frames');
		}, 12000);
		setAiState('starting');
		const ws = new WebSocket(getAIStreamUrl(activeCameraId));
		ws.binaryType = 'arraybuffer';
		aiWsRef.current = ws;

		ws.onopen = () => {
			if (!stopped) setAiState('starting');
		};
		ws.onclose = () => {
			if (!stopped) setAiState('error');
		};
		ws.onerror = () => {
			setAiState('error');
			ws.close();
		};
		ws.onmessage = (event) => {
			const frame = event.data instanceof ArrayBuffer ? event.data : null;
			if (!frame) return;
			receivedFrame = true;
			if (noFrameTimer !== null) {
				window.clearTimeout(noFrameTimer);
				noFrameTimer = null;
			}
			drawFrameToCanvases(frame, [aiCanvasRef.current, fullscreenAiCanvasRef.current]);
			setAiState('running');
		};

		return () => {
			stopped = true;
			if (noFrameTimer !== null) {
				window.clearTimeout(noFrameTimer);
				noFrameTimer = null;
			}
			ws.close();
			aiWsRef.current = null;
		};
	}, [activeCameraId, aiSessionActive, drawFrameToCanvases, jobBusy, jobStatus.running, viewMode]);

	useEffect(() => {
		if (viewMode !== 'multi_ai' || !multiAiSessionActive || multiStreamDescriptors.length === 0) {
			if (viewMode === 'multi_ai' && !jobBusy && !multiAiSessionActive) {
				setMultiAiStates((current) => Object.fromEntries(
					Object.entries(current).map(([cameraId, state]) => [cameraId, { ...(state as MultiAiStreamState), state: 'stopped' as AiViewState }]),
				) as Record<string, MultiAiStreamState>);
			}
			return undefined;
		}

		const token = getAuthToken();
		if (!token) {
			setMultiAiStates((current) => Object.fromEntries(
				multiStreamDescriptors.map(({ video, cameraId }) => [
					cameraId,
					current[cameraId] ?? { videoId: video.id, cameraId, state: 'error' as AiViewState, error: 'Missing auth token' },
				]),
			));
			return undefined;
		}

		let stopped = false;
		const timers: Record<string, number> = {};
		const sockets: Record<string, WebSocket> = {};

		for (const { video, cameraId } of multiStreamDescriptors) {
			setMultiAiStates((current) => ({
				...current,
				[cameraId]: current[cameraId] ?? { videoId: video.id, cameraId, state: 'starting', error: null },
			}));
			timers[cameraId] = window.setTimeout(() => {
				if (!stopped) {
					setMultiAiStates((current) => ({
						...current,
						[cameraId]: {
							...(current[cameraId] ?? { videoId: video.id, cameraId }),
							state: 'no_frames',
						},
					}));
				}
			}, 12000);

			const ws = new WebSocket(getAIStreamUrl(cameraId));
			ws.binaryType = 'arraybuffer';
			sockets[cameraId] = ws;
			multiAiWsRefs.current[cameraId] = ws;

			ws.onmessage = (event) => {
				const frame = event.data instanceof ArrayBuffer ? event.data : null;
				if (!frame) return;
				if (timers[cameraId]) {
					window.clearTimeout(timers[cameraId]);
					delete timers[cameraId];
				}
				drawFrameToCanvases(frame, [
					multiAiCanvasRefs.current[cameraId] ?? null,
					fullscreenMultiAiCanvasRefs.current[cameraId] ?? null,
				]);
				setMultiAiStates((current) => ({
					...current,
					[cameraId]: { videoId: video.id, cameraId, state: 'running', error: null },
				}));
			};
			ws.onerror = () => {
				setMultiAiStates((current) => ({
					...current,
					[cameraId]: { videoId: video.id, cameraId, state: 'error', error: 'AI stream connection failed' },
				}));
				ws.close();
			};
			ws.onclose = () => {
				if (!stopped) {
					setMultiAiStates((current) => ({
						...current,
						[cameraId]: { ...(current[cameraId] ?? { videoId: video.id, cameraId }), state: 'error', error: 'AI stream disconnected' },
					}));
				}
			};
		}

		return () => {
			stopped = true;
			for (const timer of Object.values(timers)) {
				window.clearTimeout(timer);
			}
			for (const [cameraId, ws] of Object.entries(sockets)) {
				ws.close();
				delete multiAiWsRefs.current[cameraId];
			}
		};
	}, [drawFrameToCanvases, jobBusy, multiAiSessionActive, multiDescriptorKey, multiStreamDescriptors, viewMode]);

	useEffect(() => {
		if (!isMaximized) return undefined;
		const handleKeyDown = (event: KeyboardEvent) => {
			if (event.key === 'Escape') setIsMaximized(false);
		};
		window.addEventListener('keydown', handleKeyDown);
		return () => window.removeEventListener('keydown', handleKeyDown);
	}, [isMaximized]);

	const showInitialLoading = videosLoading && videos.length === 0;
	const aiStateLabelMap: Record<AiViewState, string> = {
		stopped: 'AI stopped',
		starting: 'Starting AI...',
		running: 'AI running',
		no_frames: 'No frames received',
		error: 'AI error',
	};
	const aiStateLabel = aiStateLabelMap[aiState];
	const aiStateBadgeClass = aiState === 'running'
		? 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300'
		: aiState === 'error'
			? 'border-red-500/30 bg-red-500/15 text-red-300'
			: aiState === 'no_frames'
				? 'border-amber-500/30 bg-amber-500/15 text-amber-300'
				: aiState === 'starting'
					? 'border-vs-orange/30 bg-vs-orange/15 text-vs-orange'
					: 'border-zinc-700 bg-zinc-900/80 text-zinc-400';
	const aiStateDotClass = aiState === 'running'
		? 'animate-pulse bg-emerald-400'
		: aiState === 'error'
			? 'bg-red-400'
			: aiState === 'no_frames'
				? 'bg-amber-400'
				: aiState === 'starting'
					? 'animate-pulse bg-vs-orange'
					: 'bg-zinc-500';
	const multiActive = (Object.values(multiAiStates) as MultiAiStreamState[]).some((stream) => ['starting', 'running', 'no_frames'].includes(stream.state));
	const selectedIsFileSource = !selectedVideo?.sourceType || selectedVideo.sourceType === 'file';
	const canStart = !jobBusy && (
		viewMode === 'file'
			? Boolean(selectedVideo) && selectedIsFileSource && !isPlaying
			: viewMode === 'multi_ai'
				? selectedMultiVideos.length > 0 && !multiAiSessionActive && !multiActive
				: Boolean(selectedVideo) && !jobStatus.running
	);
	const canStop = !jobBusy && (
		viewMode === 'file'
			? isPlaying || jobStatus.running
			: viewMode === 'multi_ai'
				? jobStatus.running || multiAiSessionActive || multiActive
				: jobStatus.running || aiState === 'starting' || aiState === 'running' || aiState === 'no_frames'
	);

	return (
		<div className="flex h-full min-h-0 overflow-hidden bg-[#050505]">
			<div className="flex-1 overflow-y-auto p-4 lg:p-6">
				<div className="mb-5 flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
					<div>
						<h2 className="text-xl font-bold uppercase tracking-wide text-white">{t('liveFeeds')}</h2>
						<div className="mt-2 flex flex-wrap items-center gap-3">
							<StatusBadge state={wsState} />
							<span className="text-[10px] font-mono uppercase text-zinc-500">
								{videos.length} {t('sources' as any)}
							</span>
							{lastUpdated && (
								<span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase text-zinc-600">
									<Clock size={12} aria-hidden="true" />
									{t('lastUpdated')}: {lastUpdated}
								</span>
							)}
						</div>
					</div>

					<div className="flex flex-wrap items-center gap-3">
						<div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-[#0f0f11] p-1" aria-label="Source grid density">
							<button type="button" onClick={() => setLayout(4)} className={layoutButtonClass(layout === 4)} aria-pressed={layout === 4} title="Comfortable grid">
								<Grid size={18} aria-hidden="true" />
							</button>
							<button type="button" onClick={() => setLayout(9)} className={layoutButtonClass(layout === 9)} aria-pressed={layout === 9} title="Dense grid">
								<Layers size={18} aria-hidden="true" />
							</button>
						</div>
					</div>
				</div>

				{dataError && (
					<div className="mb-4 flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100" role="status">
						<AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
						<span>{dataError}</span>
					</div>
				)}
				{jobError && (
					<div className="mb-4 flex items-start justify-between gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100" role="alert">
						<div className="flex items-start gap-3">
							<AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
							<span>{jobError}</span>
						</div>
						<button type="button" onClick={() => setJobError(null)} className="text-xs font-bold uppercase text-red-200 hover:text-white">
							{t('close')}
						</button>
					</div>
				)}

				<div className="grid min-h-[780px] gap-4 lg:h-[calc(100vh-9.5rem)] lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_300px] 2xl:grid-cols-[minmax(0,1fr)_340px]">
					<div className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-zinc-800 bg-[#09090b] shadow-2xl">
						<div className="flex flex-col gap-3 border-b border-zinc-800 bg-zinc-900/50 px-4 py-3 xl:flex-row xl:items-center xl:justify-between">
							<div className="flex flex-wrap items-center gap-3">
								<div className={`flex items-center gap-2 rounded-full border px-3 py-1 text-[10px] font-bold uppercase tracking-wider ${
									jobStatus.running ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-zinc-700 bg-zinc-800/50 text-zinc-500'
								}`}>
									<span className={`h-1.5 w-1.5 rounded-full ${jobStatus.running ? 'animate-pulse bg-emerald-500' : 'bg-zinc-600'}`} />
									{jobStatus.running ? t('workerActive' as any) : t('workerOffline' as any)}
								</div>
								<div className="flex items-center gap-1 rounded-full border border-zinc-800 bg-zinc-950 p-1" role="tablist" aria-label="Live monitoring view mode">
									{(['file', 'ai', 'multi_ai'] as const).map((mode) => (
										<button
											key={mode}
											type="button"
											role="tab"
											aria-selected={viewMode === mode}
											onClick={() => handleModeChange(mode)}
											className={`rounded-full px-3 py-1 text-[10px] font-bold uppercase tracking-wide transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange ${
												viewMode === mode ? 'bg-vs-orange text-black' : 'text-zinc-500 hover:text-zinc-300'
											}`}
										>
											{mode === 'ai' ? 'AI' : mode === 'multi_ai' ? 'Multi AI' : t(mode as any)}
										</button>
									))}
								</div>
								{viewMode === 'multi_ai' && (
									<span className="rounded-full border border-zinc-800 bg-zinc-950 px-3 py-1 text-[10px] font-bold uppercase tracking-wide text-zinc-400">
										{selectedMultiVideos.length} selected
									</span>
								)}
							</div>

							<div className="flex flex-wrap items-center gap-2">
								<button
									type="button"
									onClick={startMonitoring}
									disabled={!canStart}
									className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-1.5 text-[10px] font-bold uppercase tracking-wide text-emerald-400 transition-colors hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
								>
									{jobBusy ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Play size={14} fill="currentColor" aria-hidden="true" />}
									{t('start')}
								</button>
								<button
									type="button"
									onClick={stopMonitoring}
									disabled={!canStop}
									className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-1.5 text-[10px] font-bold uppercase tracking-wide text-red-400 transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
								>
									<Square size={12} fill="currentColor" aria-hidden="true" />
									{t('stop')}
								</button>
								{cameraZones.length > 0 && (
									<button
										type="button"
										onClick={() => setShowZones(v => !v)}
										title={`${cameraZones.length} safety zone${cameraZones.length > 1 ? 's' : ''}`}
										className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-[10px] font-bold uppercase tracking-wide transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange ${
											showZones
												? 'border-vs-orange/40 bg-vs-orange/10 text-vs-orange hover:bg-vs-orange/20'
												: 'border-zinc-700 bg-zinc-900 text-zinc-400 hover:text-zinc-200'
										}`}
									>
										{showZones ? <Eye size={12} aria-hidden="true" /> : <EyeOff size={12} aria-hidden="true" />}
										<span>Zones · {cameraZones.length}</span>
									</button>
								)}
							</div>
						</div>

						<div className="group relative flex min-h-[420px] flex-1 bg-black">
							{showInitialLoading ? (
								<div className="flex h-full w-full flex-col items-center justify-center gap-3 text-zinc-600">
									<Loader2 size={28} className="animate-spin" aria-hidden="true" />
									<p className="text-xs font-bold uppercase tracking-wide">{t('loading' as any)}</p>
								</div>
							) : viewMode === 'multi_ai' ? (
								selectedMultiVideos.length > 0 ? (
									<div className="grid h-full w-full gap-2 p-2 sm:grid-cols-2 xl:grid-cols-3">
										{multiStreamDescriptors.map(({ video, cameraId }) => {
											const streamState = multiAiStates[cameraId]?.state ?? 'stopped';
											const streamLabel = aiStateLabelMap[streamState];
											return (
												<div key={cameraId} className="relative min-h-[220px] overflow-hidden rounded-md border border-zinc-800 bg-black">
													<canvas
														ref={(node) => {
															multiAiCanvasRefs.current[cameraId] = node;
														}}
														className="h-full w-full object-contain"
														aria-label={`${video.name} AI annotated stream`}
													/>
													<div className="absolute left-3 top-3 max-w-[calc(100%-1.5rem)] rounded-md border border-white/10 bg-black/70 px-3 py-1.5">
														<p className="truncate text-[10px] font-mono font-bold uppercase tracking-wider text-white">{video.name}</p>
													</div>
													<div className={`absolute bottom-3 left-3 flex items-center gap-2 rounded-md border px-3 py-1.5 ${streamState === 'running' ? 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300' : streamState === 'error' ? 'border-red-500/30 bg-red-500/15 text-red-300' : streamState === 'no_frames' ? 'border-amber-500/30 bg-amber-500/15 text-amber-300' : streamState === 'starting' ? 'border-vs-orange/30 bg-vs-orange/15 text-vs-orange' : 'border-zinc-700 bg-zinc-900/80 text-zinc-400'}`}>
														<span className={`h-2 w-2 rounded-full ${streamState === 'running' ? 'animate-pulse bg-emerald-400' : streamState === 'error' ? 'bg-red-400' : streamState === 'no_frames' ? 'bg-amber-400' : streamState === 'starting' ? 'animate-pulse bg-vs-orange' : 'bg-zinc-500'}`} />
														<span className="text-[10px] font-mono font-bold uppercase tracking-wider">{streamLabel}</span>
													</div>
													{streamState !== 'running' && (
														<div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/70 p-4 text-center text-zinc-500">
															<Cpu size={28} className={streamState === 'starting' ? 'animate-pulse text-vs-orange' : 'text-zinc-600'} aria-hidden="true" />
															<p className="text-xs font-bold uppercase tracking-wide text-zinc-300">{streamLabel}</p>
														</div>
													)}
												</div>
											);
										})}
									</div>
								) : (
									<EmptySourceState message="Select sources for Multi-Camera AI" />
								)
							) : selectedVideo ? (
								viewMode === 'file' ? (
									<video
										ref={videoPlayerRef}
										key={selectedVideo.streamUrl}
										src={selectedVideo.streamUrl}
										className="h-full w-full object-contain"
										muted
										loop
										playsInline
										preload="metadata"
										onPlay={() => setIsPlaying(true)}
										onPause={() => setIsPlaying(false)}
										onError={() => setJobError('Unable to load this video source. Check media permissions and file availability.')}
									/>
								) : (
									<div className="relative h-full w-full">
										<canvas ref={aiCanvasRef} className="h-full w-full object-contain" aria-label="AI annotated stream" />
										<div className={`absolute bottom-4 left-4 flex items-center gap-2 rounded-md border px-3 py-1.5 ${aiStateBadgeClass}`}>
											<span className={`h-2 w-2 rounded-full ${aiStateDotClass}`} />
											<span className="text-[10px] font-mono font-bold uppercase tracking-wider">{aiStateLabel}</span>
										</div>
										{aiState !== 'running' && (
											<div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/75 p-6 text-center text-zinc-400">
												<Cpu size={36} className={aiState === 'starting' ? 'animate-pulse text-vs-orange' : 'text-zinc-600'} aria-hidden="true" />
												<p className="text-sm font-bold text-white">
													{aiStateLabel}
												</p>
												<p className="max-w-md text-xs leading-relaxed text-zinc-500">
													{aiState === 'stopped' ? 'Press Start to run AI analysis for the selected source.' : aiState === 'no_frames' ? 'The worker is active, but no annotated frames have arrived yet.' : aiState === 'error' ? 'Stop and start AI again, or check the worker logs.' : 'Connecting to the edge worker stream.'}
												</p>
											</div>
										)}
									</div>
								)
							) : (
								<EmptySourceState message={t('selectSourceToStart' as any)} />
							)}

							{selectedVideo && viewMode !== 'multi_ai' && visibleZones.length > 0 && (
								<SafetyZonesOverlay zones={visibleZones} />
							)}

							{viewMode === 'file' && selectedVideo && !isPlaying && (
								<div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/55 p-6 text-center text-zinc-400">
									<Video size={34} className="text-zinc-600" aria-hidden="true" />
									<p className="text-sm font-bold text-white">File stopped</p>
									<p className="max-w-md text-xs leading-relaxed text-zinc-500">Press Start to begin playback for the selected source.</p>
								</div>
							)}

							{viewMode === 'file' && selectedVideo && isPlaying && (
								<div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-4 rounded-lg border border-white/10 bg-black/70 px-5 py-3 opacity-100 transition-opacity duration-200 lg:opacity-0 lg:group-hover:opacity-100">
									<button type="button" onClick={() => handleSkip(-10)} className="text-zinc-400 transition-colors hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange" aria-label="Rewind 10 seconds">
										<Rewind size={20} fill="currentColor" aria-hidden="true" />
									</button>
									<button type="button" onClick={handlePlayPause} className="flex h-11 w-11 items-center justify-center rounded-full bg-vs-orange text-black transition-transform hover:scale-105 focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange" aria-label={isPlaying ? 'Pause video' : 'Play video'}>
										{isPlaying ? <Pause size={22} fill="currentColor" aria-hidden="true" /> : <Play size={22} fill="currentColor" className="ms-1" aria-hidden="true" />}
									</button>
									<button type="button" onClick={() => handleSkip(10)} className="text-zinc-400 transition-colors hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange" aria-label="Fast forward 10 seconds">
										<FastForward size={20} fill="currentColor" aria-hidden="true" />
									</button>
								</div>
							)}

							<div className="absolute right-4 top-4">
								<div className="flex items-center gap-2 rounded-md border border-white/10 bg-black/65 px-3 py-1.5">
									<div className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
									<span className="text-[10px] font-mono font-bold uppercase tracking-wider text-white">{t('recording' as any)}</span>
								</div>
							</div>

							{(selectedVideo || (viewMode === 'multi_ai' && selectedMultiVideos.length > 0)) && (
								<button
									type="button"
									onClick={() => setIsMaximized(true)}
									className="absolute left-4 top-4 flex h-9 w-9 items-center justify-center rounded-md border border-white/10 bg-black/65 text-zinc-300 transition-colors hover:border-vs-orange/50 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange"
									aria-label="Maximize video preview"
									title="Maximize"
								>
									<Maximize2 size={16} aria-hidden="true" />
								</button>
							)}
						</div>

						<div className="border-t border-zinc-800 bg-zinc-900/30 p-4">
							<div className="mb-3 flex items-center justify-between">
								<h3 className="text-xs font-bold uppercase tracking-wide text-zinc-500">{t('availableSources' as any)}</h3>
								<button type="button" onClick={() => loadVideos().catch(() => setDataError('Failed to refresh video sources.'))} className="text-zinc-600 transition-colors hover:text-zinc-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange" aria-label="Refresh video sources">
									<RefreshCw size={14} className={isRefreshingVideos ? 'animate-spin' : ''} aria-hidden="true" />
								</button>
							</div>
							{videos.length > 0 ? (
								<div className={`grid gap-3 ${layout === 4 ? 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-4' : 'grid-cols-2 md:grid-cols-3 2xl:grid-cols-6'}`}>
									{videos.map((video) => (
										<DemoVideoCard
											key={video.id}
											video={video}
											isActive={video.id === selectedVideo?.id}
											onClick={() => handleSelectVideo(video)}
											isMultiSelect={viewMode === 'multi_ai'}
											isMultiSelected={selectedMultiVideoIds.includes(video.id)}
										/>
									))}
								</div>
							) : (
								<div className="rounded-lg border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-500">
									{t('noVideoSources' as any)}
								</div>
							)}
						</div>
					</div>

					<div className="flex min-h-0 flex-col rounded-lg border border-zinc-800 bg-[#0f0f11] shadow-2xl">
						<div className="flex items-center justify-between border-b border-zinc-800 p-4">
							<div>
								<h3 className="text-sm font-bold uppercase tracking-wide text-white">{t('liveIncidentFeed')}</h3>
								<p className="mt-1 text-[10px] font-mono text-zinc-500">{t('realTimeDetectionStream' as any)}</p>
							</div>
							<div className="rounded-full border border-vs-orange/20 bg-vs-orange/10 px-3 py-1 text-[10px] font-bold text-vs-orange">
								{incidents.length}
							</div>
						</div>

						<div className="min-h-0 flex-1 overflow-y-auto p-4">
							<div className="space-y-4">
								{incidentsLoading && incidents.length === 0 ? (
									<div className="flex h-40 flex-col items-center justify-center gap-3 text-zinc-600">
										<Loader2 size={24} className="animate-spin" aria-hidden="true" />
										<p className="text-xs font-medium uppercase tracking-wide">{t('initializingFeed' as any)}</p>
									</div>
								) : recentIncidents.length > 0 ? (
									recentIncidents.map((incident) => (
										<IncidentItem key={incident.id} incident={incident} />
									))
								) : (
									<div className="rounded-lg border border-dashed border-zinc-800 bg-zinc-950/40 p-8 text-center">
										<div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-zinc-900 text-zinc-700">
											<ShieldCheck size={24} aria-hidden="true" />
										</div>
										<p className="text-sm font-bold text-zinc-400">{t('noIncidentsYet' as any)}</p>
										<p className="mt-2 text-xs leading-relaxed text-zinc-600">{t('monitoringForHazards' as any)}</p>
									</div>
								)}
							</div>
						</div>

						<div className="border-t border-zinc-800 p-4">
							<button
								type="button"
								onClick={() => loadIncidents().catch(() => setDataError('Failed to refresh incidents.'))}
								disabled={isRefreshingIncidents}
								className="flex w-full items-center justify-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 py-3 text-xs font-bold uppercase tracking-wide text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange"
							>
								<RefreshCw size={14} className={isRefreshingIncidents ? 'animate-spin' : ''} aria-hidden="true" />
								{t('viewFullHistory' as any)}
							</button>
						</div>
					</div>
				</div>
			</div>
			{isMaximized && (selectedVideo || (viewMode === 'multi_ai' && selectedMultiVideos.length > 0)) && (
				<div
					className="fixed inset-0 z-50 flex bg-zinc-950/95 p-3 backdrop-blur-sm sm:p-5"
					role="dialog"
					aria-modal="true"
					aria-label="Maximized live monitoring preview"
				>
					<div className="relative flex min-h-0 flex-1 overflow-hidden rounded-lg border border-zinc-800 bg-black shadow-2xl">
						{viewMode === 'multi_ai' ? (
							<div className="grid h-full w-full gap-3 p-3 sm:grid-cols-2 xl:grid-cols-3">
								{multiStreamDescriptors.map(({ video, cameraId }) => {
									const streamState = multiAiStates[cameraId]?.state ?? 'stopped';
									const streamLabel = aiStateLabelMap[streamState];
									return (
										<div key={`fullscreen-${cameraId}`} className="relative min-h-[280px] overflow-hidden rounded-md border border-zinc-800 bg-black">
											<canvas
												ref={(node) => {
													fullscreenMultiAiCanvasRefs.current[cameraId] = node;
												}}
												className="h-full w-full object-contain"
												aria-label={`${video.name} maximized AI annotated stream`}
											/>
											<div className="absolute left-3 top-3 max-w-[calc(100%-1.5rem)] rounded-md border border-white/10 bg-black/70 px-3 py-1.5">
												<p className="truncate text-[10px] font-mono font-bold uppercase tracking-wider text-white">{video.name}</p>
											</div>
											<div className={`absolute bottom-3 left-3 flex items-center gap-2 rounded-md border px-3 py-1.5 ${streamState === 'running' ? 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300' : streamState === 'error' ? 'border-red-500/30 bg-red-500/15 text-red-300' : streamState === 'no_frames' ? 'border-amber-500/30 bg-amber-500/15 text-amber-300' : streamState === 'starting' ? 'border-vs-orange/30 bg-vs-orange/15 text-vs-orange' : 'border-zinc-700 bg-zinc-900/80 text-zinc-400'}`}>
												<span className={`h-2 w-2 rounded-full ${streamState === 'running' ? 'animate-pulse bg-emerald-400' : streamState === 'error' ? 'bg-red-400' : streamState === 'no_frames' ? 'bg-amber-400' : streamState === 'starting' ? 'animate-pulse bg-vs-orange' : 'bg-zinc-500'}`} />
												<span className="text-[10px] font-mono font-bold uppercase tracking-wider">{streamLabel}</span>
											</div>
										</div>
									);
								})}
							</div>
						) : viewMode === 'file' && selectedVideo ? (
							<video
								key={`fullscreen-${selectedVideo.streamUrl}`}
								src={selectedVideo.streamUrl}
								className="h-full w-full object-contain"
								autoPlay={isPlaying}
								muted
								loop
								playsInline
								preload="metadata"
								onError={() => setJobError('Unable to load this video source in fullscreen view.')}
							/>
						) : selectedVideo ? (
							<div className="relative h-full w-full">
								<canvas ref={fullscreenAiCanvasRef} className="h-full w-full object-contain" aria-label="Maximized AI annotated stream" />
								<div className={`absolute bottom-4 left-4 flex items-center gap-2 rounded-md border px-3 py-1.5 ${aiStateBadgeClass}`}>
									<span className={`h-2 w-2 rounded-full ${aiStateDotClass}`} />
									<span className="text-[10px] font-mono font-bold uppercase tracking-wider">{aiStateLabel}</span>
								</div>
								{aiState !== 'running' && (
									<div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/75 p-6 text-center text-zinc-400">
										<Cpu size={42} className={aiState === 'starting' ? 'animate-pulse text-vs-orange' : 'text-zinc-600'} aria-hidden="true" />
										<p className="text-sm font-bold text-white">
											{aiStateLabel}
										</p>
									</div>
								)}
							</div>
						) : null}

						{selectedVideo && viewMode !== 'multi_ai' && visibleZones.length > 0 && (
							<SafetyZonesOverlay zones={visibleZones} />
						)}

						{viewMode === 'file' && !isPlaying && (
							<div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/55 p-6 text-center text-zinc-400">
								<Video size={42} className="text-zinc-600" aria-hidden="true" />
								<p className="text-sm font-bold text-white">File stopped</p>
								<p className="max-w-md text-xs leading-relaxed text-zinc-500">Close this view and press Start to begin playback.</p>
							</div>
						)}

						<div className="absolute left-4 top-4 flex items-center gap-2 rounded-md border border-white/10 bg-black/70 px-3 py-1.5">
							<div className={`h-2 w-2 rounded-full ${jobStatus.running ? 'animate-pulse bg-emerald-500' : 'bg-zinc-600'}`} />
							<span className="text-[10px] font-mono font-bold uppercase tracking-wider text-white">
								{viewMode === 'multi_ai' ? `Multi AI • ${selectedMultiVideos.length} sources` : `${viewMode === 'ai' ? 'AI' : t('file' as any)} • ${selectedVideo?.name ?? ''}`}
							</span>
						</div>
						<div className="absolute right-4 top-4 flex items-center gap-2">
							<div className="hidden items-center gap-2 rounded-md border border-white/10 bg-black/70 px-3 py-1.5 sm:flex">
								<div className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
								<span className="text-[10px] font-mono font-bold uppercase tracking-wider text-white">{t('recording' as any)}</span>
							</div>
							<button
								type="button"
								onClick={() => setIsMaximized(false)}
								className="flex h-10 w-10 items-center justify-center rounded-md border border-white/10 bg-black/70 text-zinc-300 transition-colors hover:border-vs-orange/50 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange"
								aria-label="Close maximized preview"
								title="Close"
							>
								<X size={18} aria-hidden="true" />
							</button>
						</div>
					</div>
				</div>
			)}
		</div>
	);
};

export default LiveMonitoring;
