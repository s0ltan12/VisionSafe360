import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
	AlertTriangle,
	Clock,
	Cpu,
	FastForward,
	Grid,
	Layers,
	Loader2,
	Pause,
	Play,
	Radio,
	RefreshCw,
	Rewind,
	ShieldCheck,
	Square,
	Upload,
	Video,
	Wifi,
	WifiOff,
} from 'lucide-react';
import {
	DemoVideosAPI,
	IncidentsAPI,
	JobsAPI,
	UploadAPI,
	WS_BASE_URL,
	getAIStreamUrl,
	getAuthToken,
} from '../api';
import { DemoVideo, Incident, JobStatus } from '../types';
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

const normalizeIncident = (payload: any): Incident => ({
	id: String(payload?.id ?? `INC-${Date.now()}`),
	zone: String(payload?.zone ?? 'Unknown zone'),
	classification: String(payload?.classification ?? 'Unclassified'),
	severity: payload?.severity === 'High' || payload?.severity === 'Medium' || payload?.severity === 'Low'
		? payload.severity
		: 'Low',
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

const withPreviewTimestamp = (url: string, seconds = 1.25) => {
	if (!url) return '';
	const [base, fragment = ''] = url.split('#');
	return `${base}#t=${seconds}${fragment ? `&${fragment}` : ''}`;
};

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

const isJobForVideo = (status: JobStatus, video: DemoVideo) => {
	const sourceName = status.sourceName || '';
	return sourceName === video.fileName || sourceName.endsWith(`/${video.fileName}`) || sourceName.includes(video.fileName);
};

const SourcePreview: React.FC<{ video: DemoVideo }> = ({ video }) => {
	const canvasRef = useRef<HTMLCanvasElement | null>(null);
	const videoRef = useRef<HTMLVideoElement | null>(null);
	const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
	const previewSrc = useMemo(() => withPreviewTimestamp(video.streamUrl), [video.streamUrl]);

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
		context.drawImage(element, 0, 0, canvas.width, canvas.height);
		setState('ready');
	}, []);

	useEffect(() => {
		setState('loading');
	}, [previewSrc]);

	return (
		<div className="relative aspect-video overflow-hidden bg-zinc-950">
			<canvas
				ref={canvasRef}
				className={`h-full w-full object-cover transition-opacity ${state === 'ready' ? 'opacity-75 group-hover:opacity-90' : 'opacity-0'}`}
				aria-hidden="true"
			/>
			<video
				ref={videoRef}
				src={previewSrc}
				className="pointer-events-none absolute h-px w-px opacity-0"
				muted
				playsInline
				preload="metadata"
				onLoadedMetadata={(event) => {
					const element = event.currentTarget;
					if (Number.isFinite(element.duration) && element.duration > 0) {
						element.currentTime = Math.min(1.25, Math.max(0, element.duration * 0.15));
					} else {
						drawPreview();
					}
				}}
				onLoadedData={drawPreview}
				onSeeked={drawPreview}
				onError={() => setState('error')}
			/>
			{state !== 'ready' && (
				<div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-zinc-950 text-zinc-600">
					{state === 'loading' ? <Loader2 size={18} className="animate-spin" aria-hidden="true" /> : <Video size={22} aria-hidden="true" />}
					<span className="px-3 text-center text-[9px] font-bold uppercase tracking-wide text-zinc-500">
						{video.name}
					</span>
				</div>
			)}
		</div>
	);
};

const DemoVideoCard: React.FC<{
	video: DemoVideo;
	isActive: boolean;
	onClick: () => void;
}> = ({ video, isActive, onClick }) => {
	const { t } = useLanguage();
	return (
		<button
			type="button"
			onClick={onClick}
			aria-pressed={isActive}
			className={`group relative min-h-32 overflow-hidden rounded-lg border text-start transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange ${
				isActive ? 'border-vs-orange shadow-[0_0_0_1px_rgba(249,115,22,0.45)]' : 'border-zinc-800 hover:border-zinc-700'
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
					<span className={`max-w-[52%] truncate rounded-full border px-2 py-1 text-[9px] font-bold uppercase tracking-wider ${isActive ? 'border-vs-orange/30 bg-vs-orange/10 text-vs-orange' : 'border-white/10 bg-black/50 text-zinc-400'}`}>
						{video.zone}
					</span>
				</div>
				<div>
					<p className="truncate text-sm font-bold text-white">{video.name}</p>
					<p className="mt-1 line-clamp-2 text-[10px] text-zinc-300">{video.description}</p>
				</div>
			</div>
		</button>
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
	const [viewMode, setViewMode] = useState<'file' | 'ai'>('file');
	const [videos, setVideos] = useState<DemoVideo[]>([]);
	const [selectedVideoId, setSelectedVideoId] = useState('');
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
	const [aiState, setAiState] = useState<'idle' | 'connecting' | 'waiting' | 'streaming' | 'unavailable'>('idle');

	const wsRef = useRef<WebSocket | null>(null);
	const reconnectTimerRef = useRef<number | null>(null);
	const reconnectAttemptRef = useRef(0);
	const videoPlayerRef = useRef<HTMLVideoElement>(null);
	const aiCanvasRef = useRef<HTMLCanvasElement>(null);
	const aiWsRef = useRef<WebSocket | null>(null);
	const aiStartAttemptRef = useRef<string | null>(null);
	const aiTransitionRef = useRef(false);
	const fileInputRef = useRef<HTMLInputElement | null>(null);
	const [isPlaying, setIsPlaying] = useState(true);
	const [uploadBusy, setUploadBusy] = useState(false);

	const selectedVideo = useMemo(
		() => videos.find((video) => video.id === selectedVideoId) ?? videos[0] ?? null,
		[videos, selectedVideoId],
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

	const loadVideos = useCallback(async (options: RequestInit = {}) => {
		setIsRefreshingVideos(true);
		try {
			const data = await DemoVideosAPI.getAll(options);
			setVideos(data);
			setSelectedVideoId((current) => {
				if (current && data.some((video) => video.id === current)) return current;
				return data[0]?.id || '';
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
			const data = await IncidentsAPI.getAll(options);
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

	const startJobForVideo = useCallback(async (video: DemoVideo, cameraId = 'cam_01') => {
		const status = await JobsAPI.start(video.fileName, cameraId);
		setJobStatus(status);
		setJobError(null);
		return status;
	}, []);

	const startJob = useCallback(async () => {
		if (!selectedVideo || jobBusy) return;
		setJobBusy(true);
		setJobError(null);
		try {
			await startJobForVideo(selectedVideo, activeCameraId);
		} catch (error: any) {
			setJobError(error?.message ?? 'Failed to start worker job');
		} finally {
			setJobBusy(false);
		}
	}, [activeCameraId, jobBusy, selectedVideo, startJobForVideo]);

	const restartAiForVideo = useCallback(async (video: DemoVideo) => {
		if (aiTransitionRef.current) return;
		aiTransitionRef.current = true;
		aiStartAttemptRef.current = video.id;
		setJobBusy(true);
		setJobError(null);
		try {
			const currentStatus = await JobsAPI.status();
			setJobStatus(currentStatus);
			if (currentStatus.running && !isJobForVideo(currentStatus, video)) {
				setAiState('waiting');
				const stoppedStatus = await JobsAPI.stop();
				setJobStatus(stoppedStatus);
				const stopped = await waitForJobIdle();
				if (!stopped) {
					throw new Error('Timed out waiting for the previous AI worker to stop.');
				}
			}
			const latestStatus = await JobsAPI.status();
			if (!latestStatus.running) {
				await startJobForVideo(video, 'cam_01');
			} else if (!isJobForVideo(latestStatus, video)) {
				throw new Error('AI worker is running a different source. Stop it before starting this source.');
			} else {
				setJobStatus(latestStatus);
			}
		} catch (error: any) {
			setJobError(error?.message ?? 'Failed to start AI worker');
		} finally {
			setJobBusy(false);
			aiTransitionRef.current = false;
		}
	}, [startJobForVideo, waitForJobIdle]);

	const stopJob = async () => {
		if (jobBusy) return;
		setJobBusy(true);
		setJobError(null);
		try {
			const status = await JobsAPI.stop();
			setJobStatus(status);
		} catch (error: any) {
			setJobError(error?.message ?? 'Failed to stop worker job');
		} finally {
			setJobBusy(false);
		}
	};

	const handlePlayPause = async () => {
		const player = videoPlayerRef.current;
		if (!player) return;
		if (player.paused) {
			try {
				await player.play();
				setIsPlaying(true);
			} catch {
				setJobError('Browser blocked video playback. Use the video area or controls to start playback.');
			}
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

	const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
		const file = event.target.files?.[0];
		if (!file) return;
		setUploadBusy(true);
		setJobError(null);
		try {
			await UploadAPI.uploadVideo(file);
			await loadVideos();
		} catch (err: any) {
			setJobError(err?.message || 'Upload failed');
		} finally {
			setUploadBusy(false);
			event.target.value = '';
		}
	};

	const handleModeChange = useCallback((mode: 'file' | 'ai') => {
		setViewMode(mode);
		if (mode === 'ai' && selectedVideo) {
			aiStartAttemptRef.current = null;
			void restartAiForVideo(selectedVideo);
		}
	}, [restartAiForVideo, selectedVideo]);

	const handleSelectVideo = useCallback((video: DemoVideo) => {
		setSelectedVideoId(video.id);
		if (viewMode === 'ai') {
			void restartAiForVideo(video);
		}
	}, [restartAiForVideo, viewMode]);

	useEffect(() => {
		if (viewMode !== 'ai') {
			aiStartAttemptRef.current = null;
			return;
		}
		if (!selectedVideo || jobBusy || aiStartAttemptRef.current === selectedVideo.id) {
			return;
		}
		if (jobStatus.running && isJobForVideo(jobStatus, selectedVideo)) {
			aiStartAttemptRef.current = selectedVideo.id;
			return;
		}
		void restartAiForVideo(selectedVideo);
	}, [jobBusy, jobStatus, restartAiForVideo, selectedVideo, viewMode]);

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
		loadJobStatus({ signal: controller.signal }).catch(() => undefined);
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
		if (viewMode !== 'ai') {
			setAiState('idle');
			return undefined;
		}

		const token = getAuthToken();
		if (!token) {
			setAiState('unavailable');
			return undefined;
		}

		let stopped = false;
		setAiState('connecting');
		const ws = new WebSocket(getAIStreamUrl(activeCameraId));
		ws.binaryType = 'arraybuffer';
		aiWsRef.current = ws;

		ws.onopen = () => setAiState('waiting');
		ws.onclose = () => {
			if (!stopped) setAiState('unavailable');
		};
		ws.onerror = () => ws.close();
		ws.onmessage = (event) => {
			const frame = event.data instanceof ArrayBuffer ? event.data : null;
			if (!frame) return;
			const blob = new Blob([frame], { type: 'image/jpeg' });
			const imageUrl = URL.createObjectURL(blob);
			const image = new Image();
			image.onload = () => {
				const canvas = aiCanvasRef.current;
				const context = canvas?.getContext('2d');
				if (canvas && context) {
					canvas.width = image.width;
					canvas.height = image.height;
					context.drawImage(image, 0, 0);
					setAiState('streaming');
				}
				URL.revokeObjectURL(imageUrl);
			};
			image.onerror = () => URL.revokeObjectURL(imageUrl);
			image.src = imageUrl;
		};

		return () => {
			stopped = true;
			ws.close();
			aiWsRef.current = null;
		};
	}, [activeCameraId, viewMode]);

	const showInitialLoading = videosLoading && videos.length === 0;

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
						<input
							type="file"
							ref={fileInputRef}
							onChange={handleFileUpload}
							className="hidden"
							accept="video/mp4,video/avi,video/quicktime,video/x-matroska"
						/>
						<button
							type="button"
							onClick={() => fileInputRef.current?.click()}
							disabled={uploadBusy}
							className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2 text-xs font-bold uppercase tracking-wide text-zinc-300 transition-colors hover:border-vs-orange/50 hover:text-white disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-vs-orange"
						>
							{uploadBusy ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Upload size={14} aria-hidden="true" />}
							{t('uploadVideo' as any)}
						</button>
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

				<div className="grid min-h-[720px] gap-5 lg:h-[calc(100vh-11.5rem)] lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_360px] 2xl:grid-cols-[minmax(0,1fr)_400px]">
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
									{(['file', 'ai'] as const).map((mode) => (
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
											{mode === 'ai' ? 'AI' : t(mode as any)}
										</button>
									))}
								</div>
							</div>

							<div className="flex flex-wrap items-center gap-2">
								<button
									type="button"
									onClick={startJob}
									disabled={!selectedVideo || jobStatus.running || jobBusy}
									className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-1.5 text-[10px] font-bold uppercase tracking-wide text-emerald-400 transition-colors hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
								>
									{jobBusy ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Play size={14} fill="currentColor" aria-hidden="true" />}
									{t('start')}
								</button>
								<button
									type="button"
									onClick={stopJob}
									disabled={!jobStatus.running || jobBusy}
									className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-1.5 text-[10px] font-bold uppercase tracking-wide text-red-400 transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
								>
									<Square size={12} fill="currentColor" aria-hidden="true" />
									{t('stop')}
								</button>
							</div>
						</div>

						<div className="group relative flex min-h-[320px] flex-1 bg-black">
							{showInitialLoading ? (
								<div className="flex h-full w-full flex-col items-center justify-center gap-3 text-zinc-600">
									<Loader2 size={28} className="animate-spin" aria-hidden="true" />
									<p className="text-xs font-bold uppercase tracking-wide">{t('loading' as any)}</p>
								</div>
							) : selectedVideo ? (
								viewMode === 'file' ? (
									<video
										ref={videoPlayerRef}
										key={selectedVideo.streamUrl}
										src={selectedVideo.streamUrl}
										className="h-full w-full object-contain"
										autoPlay
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
										{aiState !== 'streaming' && (
											<div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/75 p-6 text-center text-zinc-400">
												<Cpu size={36} className={aiState === 'connecting' ? 'animate-pulse text-vs-orange' : 'text-zinc-600'} aria-hidden="true" />
												<p className="text-sm font-bold text-white">
													{aiState === 'connecting' ? t('connectingAiStream' as any) : aiState === 'waiting' ? t('waitingForFrames' as any) : t('aiStreamUnavailable' as any)}
												</p>
												<p className="max-w-md text-xs leading-relaxed text-zinc-500">
													{jobStatus.running ? t('waitingForFrames' as any) : t('startWorkerForAi' as any)}
												</p>
											</div>
										)}
									</div>
								)
							) : (
								<EmptySourceState message={t('selectSourceToStart' as any)} />
							)}

							{viewMode === 'file' && selectedVideo && (
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
		</div>
	);
};

export default LiveMonitoring;
