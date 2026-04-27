import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
	ArrowLeft,
	Grid,
	Layers,
	Maximize2,
	Power,
	Play,
	RefreshCw,
	Square,
	Target,
	VolumeX,
	Video,
	Radio,
	Upload,
	Cpu,
} from 'lucide-react';
import { DemoVideosAPI, IncidentsAPI, JobsAPI, UploadAPI, getAIStreamUrl, WS_BASE_URL, getAuthToken } from '../api';
import { DemoVideo, Incident, JobStatus } from '../types';
import { useLanguage } from '../contexts/LanguageContext';

const layoutButtonClass = (active: boolean) =>
	`p-2 rounded transition-colors ${active ? 'bg-zinc-800 text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-300'}`;

const severityStyle: Record<string, string> = {
	High: 'text-red-400 border-red-500/30 bg-red-500/10',
	Medium: 'text-amber-400 border-amber-500/30 bg-amber-500/10',
	Low: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
};

const formatTime = (value: string) =>
	new Date(value).toLocaleString([], {
		month: 'short',
		day: '2-digit',
		hour: '2-digit',
		minute: '2-digit',
	});

const toFrontendIncident = (payload: any): Incident => ({
	id: payload.id,
	zone: payload.zone,
	classification: payload.classification,
	severity: payload.severity,
	rootCause: payload.root_cause,
	correctiveAction: payload.corrective_action,
	createdAt: payload.created_at,
});

const DemoVideoCard = ({
	video,
	isActive,
	onClick,
}: {
	video: DemoVideo;
	isActive: boolean;
	onClick: () => void;
}) => {
	return (
		<button
			onClick={onClick}
			className={`group relative overflow-hidden rounded-xl border text-start transition-all ${isActive ? 'border-vs-orange shadow-[0_0_0_1px_rgba(249,115,22,0.45)]' : 'border-zinc-800 hover:border-zinc-700'}`}
		>
			<div className="absolute inset-0 bg-gradient-to-br from-white/[0.03] to-transparent" />
			<div className="aspect-video bg-zinc-950">
				<video
					src={video.streamUrl}
					className="h-full w-full object-cover opacity-70 group-hover:opacity-90 transition-opacity"
					muted
					playsInline
					preload="metadata"
				/>
			</div>
			<div className="absolute inset-0 flex flex-col justify-between p-3">
				<div className="flex items-start justify-between gap-2">
					<div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/70 px-2 py-1 backdrop-blur-sm">
						<span className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_10px_#10b981]" />
						<span className="font-mono text-[10px] font-bold tracking-[0.2em] text-white">
							LIVE DEMO
						</span>
					</div>
					<span className={`rounded-full border px-2 py-1 text-[9px] font-bold uppercase tracking-[0.2em] ${isActive ? 'border-vs-orange/30 bg-vs-orange/10 text-vs-orange' : 'border-white/10 bg-black/50 text-zinc-400'}`}>
						{video.zone}
					</span>
				</div>
				<div>
					<p className="text-sm font-bold text-white">{video.name}</p>
					<p className="mt-1 text-[10px] text-zinc-300 line-clamp-2">{video.description}</p>
				</div>
			</div>
		</button>
	);
};

const IncidentItem: React.FC<{ incident: Incident }> = ({ incident }) => {
	return (
		<div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 transition-colors hover:border-zinc-700">
			<div className="flex items-start justify-between gap-3">
				<div>
					<p className="text-sm font-semibold text-white">{incident.classification}</p>
					<p className="mt-1 text-[10px] font-mono text-zinc-500">{incident.zone} • {formatTime(incident.createdAt)}</p>
				</div>
				<span className={`rounded-full border px-2 py-1 text-[9px] font-bold uppercase tracking-[0.2em] ${severityStyle[incident.severity] ?? 'border-zinc-700 bg-zinc-800 text-zinc-300'}`}>
					{incident.severity}
				</span>
			</div>
			<p className="mt-3 text-xs leading-relaxed text-zinc-400">{incident.rootCause}</p>
			<p className="mt-2 text-[11px] text-zinc-500">{incident.correctiveAction}</p>
		</div>
	);
};

const LiveMonitoring = () => {
	const { t } = useLanguage();
	const [layout, setLayout] = useState<4 | 9>(4);
	const [viewMode, setViewMode] = useState<'file' | 'stream' | 'ai'>('file');
	const [videos, setVideos] = useState<DemoVideo[]>([]);
	const [selectedVideoId, setSelectedVideoId] = useState<string>('');
	const [incidents, setIncidents] = useState<Incident[]>([]);
	const [jobStatus, setJobStatus] = useState<JobStatus>({ running: false });
	const [jobBusy, setJobBusy] = useState(false);
	const [jobError, setJobError] = useState<string | null>(null);
	const [isLoading, setIsLoading] = useState(true);
	const [isRefreshing, setIsRefreshing] = useState(false);
	const [lastUpdated, setLastUpdated] = useState<string | null>(null);
	const [dataError, setDataError] = useState<string | null>(null);
	const [wsState, setWsState] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
	const wsRef = useRef<WebSocket | null>(null);
	const reconnectTimerRef = useRef<number | null>(null);
	const reconnectAttemptRef = useRef(0);

	// AI Stream state
	const [aiStreamUrl, setAiStreamUrl] = useState<string | null>(null);
	const aiStreamWsRef = useRef<WebSocket | null>(null);
	const aiCanvasRef = useRef<HTMLCanvasElement | null>(null);
	const [aiStreamConnected, setAiStreamConnected] = useState(false);
	const [uploadBusy, setUploadBusy] = useState(false);
	const fileInputRef = useRef<HTMLInputElement | null>(null);

	const selectedVideo = videos.find((video) => video.id === selectedVideoId) ?? videos[0] ?? null;

	const upsertIncident = (incident: Incident) => {
		setIncidents((previous) => {
			const existingIndex = previous.findIndex((item) => item.id === incident.id);
			if (existingIndex >= 0) {
				const updated = [...previous];
				updated[existingIndex] = incident;
				return updated;
			}
			return [incident, ...previous];
		});
	};

	const loadVideos = async () => {
		const data = await DemoVideosAPI.getAll();
		setVideos(data);
		setSelectedVideoId((current) => current || data[0]?.id || '');
		setDataError(null);
	};

	const loadIncidents = async () => {
		setIsRefreshing(true);
		try {
			const data = await IncidentsAPI.getAll();
			setIncidents(data);
			setLastUpdated(new Date().toLocaleTimeString());
			setDataError(null);
		} finally {
			setIsRefreshing(false);
			setIsLoading(false);
		}
	};

	const loadJobStatus = async () => {
		const status = await JobsAPI.status();
		setJobStatus(status);
	};

	const startJob = async () => {
		if (!selectedVideo || jobBusy) {
			return;
		}
		setJobBusy(true);
		setJobError(null);
		try {
			const status = await JobsAPI.start(selectedVideo.fileName, 'cam_01');
			setJobStatus(status);
		} catch (error: any) {
			setJobError(error?.message ?? 'Failed to start worker job');
		} finally {
			setJobBusy(false);
		}
	};

	const stopJob = async () => {
		if (jobBusy) {
			return;
		}
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

	const handleUpload = async () => {
		fileInputRef.current?.click();
	};

	const onFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
		const file = e.target.files?.[0];
		if (!file) return;
		setUploadBusy(true);
		setJobError(null);
		try {
			await UploadAPI.uploadVideo(file);
			await loadVideos();
		} catch (err: any) {
			setJobError(err?.message ?? 'Upload failed');
		} finally {
			setUploadBusy(false);
			e.target.value = '';
		}
	};

	// Connect AI stream WebSocket when viewMode is 'ai' and job is running
	useEffect(() => {
		if (viewMode !== 'ai' || !jobStatus.running) {
			if (aiStreamWsRef.current) {
				aiStreamWsRef.current.close();
				aiStreamWsRef.current = null;
			}
			setAiStreamConnected(false);
			return;
		}

		const cameraId = jobStatus.cameraId || 'cam_01';
		const url = getAIStreamUrl(cameraId);
		const ws = new WebSocket(url);
		ws.binaryType = 'arraybuffer';
		aiStreamWsRef.current = ws;

		ws.onopen = () => setAiStreamConnected(true);
		ws.onclose = () => setAiStreamConnected(false);
		ws.onerror = () => ws.close();

		ws.onmessage = (event) => {
			if (event.data instanceof ArrayBuffer) {
				const blob = new Blob([event.data], { type: 'image/jpeg' });
				const imgUrl = URL.createObjectURL(blob);
				const img = new Image();
				img.onload = () => {
					const canvas = aiCanvasRef.current;
					if (canvas) {
						canvas.width = img.width;
						canvas.height = img.height;
						const ctx2d = canvas.getContext('2d');
						if (ctx2d) ctx2d.drawImage(img, 0, 0);
					}
					URL.revokeObjectURL(imgUrl);
				};
				img.src = imgUrl;
			}
		};

		return () => {
			ws.close();
			aiStreamWsRef.current = null;
		};
	}, [viewMode, jobStatus.running, jobStatus.cameraId]);

	useEffect(() => {
		loadVideos().catch(() => {
			setIsLoading(false);
			setDataError('Failed to load demo videos from backend.');
		});
		loadIncidents().catch(() => {
			setIsLoading(false);
			setDataError('Failed to load incidents from backend.');
		});
		loadJobStatus().catch(() => undefined);
		const timer = window.setInterval(() => {
			loadJobStatus().catch(() => undefined);
		}, 2000);
		return () => window.clearInterval(timer);
	}, []);

	useEffect(() => {
		let stopped = false;

		const connect = () => {
			if (stopped) {
				return;
			}
			setWsState('connecting');
			const token = getAuthToken();
			const wsUrl = token
				? `${WS_BASE_URL}/ws/incidents?token=${encodeURIComponent(token)}`
				: `${WS_BASE_URL}/ws/incidents`;
			const ws = new WebSocket(wsUrl);
			wsRef.current = ws;

			ws.onopen = () => {
				reconnectAttemptRef.current = 0;
				setWsState('connected');
			};

			ws.onmessage = (event) => {
				try {
					const payload = JSON.parse(event.data);
					if (payload?.type === 'incident_created' && payload?.incident) {
						upsertIncident(toFrontendIncident(payload.incident));
						setLastUpdated(new Date().toLocaleTimeString());
					}
				} catch {
					// ignore malformed payloads in MVP
				}
			};

			ws.onclose = () => {
				if (stopped) {
					return;
				}
				setWsState('disconnected');
				setDataError('Realtime channel disconnected. Reconnecting...');
				reconnectAttemptRef.current += 1;
				const backoffMs = Math.min(1000 * reconnectAttemptRef.current, 10000);
				reconnectTimerRef.current = window.setTimeout(connect, backoffMs);
			};

			ws.onerror = () => {
				setDataError('Realtime channel error.');
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
	}, []);

	const recentIncidents = incidents.slice(0, 6);

	return (
		<div className="flex h-full overflow-hidden bg-[#050505]">
			<div className="flex-1 overflow-hidden p-4">
				<div className="mb-4 flex items-center justify-between gap-4">
					<div>
						<h2 className="text-xl font-bold uppercase tracking-wider text-white">{t('liveFeeds')}</h2>
						<p className="text-[10px] font-mono text-zinc-500">
							{videos.length} demo sources • job status refresh every 2 seconds
						</p>
					</div>
					<div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-[#0f0f11] p-1">
						<button onClick={() => setLayout(4)} className={layoutButtonClass(layout === 4)}>
							<Grid size={18} />
						</button>
						<button onClick={() => setLayout(9)} className={layoutButtonClass(layout === 9)}>
							<Layers size={18} />
						</button>
					</div>
				</div>
					{dataError ? (
						<div className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
							{dataError}
						</div>
					) : null}

				<div className="grid h-[calc(100%-4rem)] gap-4 xl:grid-cols-[minmax(0,1.55fr)_360px]">
					<div className="flex min-h-0 flex-col rounded-2xl border border-zinc-800 bg-[#09090b] shadow-2xl">
						<div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
							<div className="flex items-center gap-3">
								<div className="flex items-center gap-2 rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.2em] text-red-400">
									<span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
									Live
								</div>
								<div className="text-[10px] font-mono text-zinc-500">
									{selectedVideo ? `${selectedVideo.name} • ${selectedVideo.fileName}` : 'Loading demo videos'}
								</div>
							</div>
							<div className="flex items-center gap-3 text-[10px] font-mono text-zinc-500">
								<div className={`rounded-full border px-3 py-1 text-[10px] font-bold uppercase tracking-[0.2em] ${jobStatus.running ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-zinc-700 bg-zinc-900 text-zinc-400'}`}>
									{jobStatus.running ? 'Worker Running' : 'Worker Stopped'}
								</div>
								<div className={`rounded-full border px-3 py-1 text-[10px] font-bold uppercase tracking-[0.2em] ${wsState === 'connected' ? 'border-cyan-400/40 bg-cyan-400/10 text-cyan-300' : wsState === 'connecting' ? 'border-amber-400/40 bg-amber-400/10 text-amber-300' : 'border-zinc-700 bg-zinc-900 text-zinc-400'}`}>
									WS {wsState}
								</div>
								<button
									onClick={startJob}
									disabled={!selectedVideo || jobStatus.running || jobBusy}
									className="inline-flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-emerald-300 transition-colors hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-50"
								>
									<Power size={12} /> Start
								</button>
								<button
									onClick={stopJob}
									disabled={!jobStatus.running || jobBusy}
									className="inline-flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-1 text-red-300 transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-50"
								>
									<Square size={12} /> Stop
								</button>
								<input ref={fileInputRef} type="file" accept="video/*" className="hidden" onChange={onFileSelected} />
								<button
									onClick={handleUpload}
									disabled={uploadBusy}
									className="inline-flex items-center gap-2 rounded-md border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-cyan-300 transition-colors hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-50"
								>
									<Upload size={12} /> {uploadBusy ? 'Uploading...' : 'Upload'}
								</button>
								<div className="flex items-center gap-1 rounded-full border border-zinc-800 bg-zinc-950 p-1">
									<button
										onClick={() => setViewMode('file')}
										className={`inline-flex items-center gap-1 rounded-full px-3 py-1 transition-colors ${viewMode === 'file' ? 'bg-vs-orange text-black' : 'text-zinc-400 hover:text-white'}`}
									>
										<Play size={12} /> File
									</button>
									<button
										onClick={() => setViewMode('stream')}
										className={`inline-flex items-center gap-1 rounded-full px-3 py-1 transition-colors ${viewMode === 'stream' ? 'bg-vs-orange text-black' : 'text-zinc-400 hover:text-white'}`}
									>
										<Radio size={12} /> Stream
									</button>
									<button
										onClick={() => setViewMode('ai')}
										className={`inline-flex items-center gap-1 rounded-full px-3 py-1 transition-colors ${viewMode === 'ai' ? 'bg-emerald-500 text-black' : 'text-zinc-400 hover:text-white'}`}
									>
										<Cpu size={12} /> AI Stream
									</button>
								</div>
								<span>{lastUpdated ? `Last sync ${lastUpdated}` : 'Syncing incidents'}</span>
								<button
									onClick={() => loadIncidents().catch(() => undefined)}
									className="inline-flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-900 px-3 py-1 text-zinc-300 transition-colors hover:border-zinc-700 hover:text-white"
								>
									<RefreshCw size={12} className={isRefreshing ? 'animate-spin' : ''} />
									Refresh
								</button>
							</div>
						</div>
						{jobError ? (
							<div className="border-b border-red-500/20 bg-red-500/10 px-4 py-2 text-xs text-red-300">{jobError}</div>
						) : null}

						<div className="relative flex-1 min-h-[320px] bg-black">
							{viewMode === 'ai' ? (
								<div className="flex h-full w-full items-center justify-center">
									{jobStatus.running ? (
										<>
											<canvas ref={aiCanvasRef} className="h-full w-full object-contain" />
											{!aiStreamConnected && (
												<div className="absolute inset-0 flex items-center justify-center bg-black/60">
													<div className="text-center">
														<Cpu size={32} className="mx-auto text-emerald-400 animate-pulse" />
														<p className="mt-3 text-sm font-semibold text-white">Connecting to AI Stream...</p>
														<p className="mt-1 text-xs text-zinc-400">Waiting for YOLO pipeline frames</p>
													</div>
												</div>
											)}
										</>
									) : (
										<div className="text-center p-8">
											<Cpu size={40} className="mx-auto text-zinc-600" />
											<p className="mt-4 text-sm font-semibold text-zinc-300">AI Pipeline Not Running</p>
											<p className="mt-2 text-xs text-zinc-500">Select a video and click Start to begin real-time YOLO detection</p>
										</div>
									)}
								</div>
							) : selectedVideo ? (
								viewMode === 'file' ? (
									<video
										key={selectedVideo.streamUrl}
										src={selectedVideo.streamUrl}
										className="h-full w-full object-contain"
										controls
										autoPlay
										muted
										loop
										playsInline
									/>
								) : (
									<img
										key={selectedVideo.streamFeedUrl}
										src={selectedVideo.streamFeedUrl}
										className="h-full w-full object-contain"
										alt={selectedVideo.name}
									/>
								)
							) : (
								<div className="flex h-full items-center justify-center text-sm text-zinc-500">
									Loading demo video sources...
								</div>
							)}
							<div className="pointer-events-none absolute inset-0 border border-vs-orange/15" />
							<div className="absolute bottom-4 left-4 right-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-black/65 px-4 py-3 backdrop-blur-md">
								<div>
									<p className="text-xs font-semibold text-white">{selectedVideo?.name ?? 'No video selected'}</p>
									<p className="mt-1 text-[10px] text-zinc-400">
										{selectedVideo?.description ?? 'Select a source to preview it in the dashboard.'}
									</p>
									<p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-zinc-600">
										{viewMode === 'file' ? 'Video endpoint' : 'Video feed endpoint'}
									</p>
								</div>
								<div className="flex items-center gap-3 text-zinc-300">
									<button className="transition-colors hover:text-white">
										<VolumeX size={18} />
									</button>
									<button className="transition-colors hover:text-white">
										<Maximize2 size={18} />
									</button>
								</div>
							</div>
						</div>

						<div className="border-t border-zinc-800 p-4">
							<div className={`grid gap-3 ${layout === 4 ? 'grid-cols-2' : 'grid-cols-3'}`}>
								{videos.map((video) => (
									<div key={video.id} className="aspect-video">
										<DemoVideoCard
											video={video}
											isActive={video.id === selectedVideo?.id}
											onClick={() => setSelectedVideoId(video.id)}
										/>
									</div>
								))}
							</div>
						</div>
					</div>

					<div className="flex min-h-0 flex-col rounded-2xl border border-zinc-800 bg-[#0f0f11] shadow-2xl">
						<div className="border-b border-zinc-800 p-4">
							<div className="flex items-center justify-between gap-3">
								<div>
									<h3 className="text-sm font-bold uppercase tracking-wider text-white">Incident Feed</h3>
									<p className="mt-1 text-[10px] font-mono text-zinc-500">
										Realtime stream from backend incidents
									</p>
								</div>
								<div className="rounded-full border border-zinc-800 bg-zinc-900 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-400">
									{incidents.length} total
								</div>
							</div>
						</div>

						<div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
							<div className="space-y-3">
								{isLoading && incidents.length === 0 ? (
									<div className="flex h-40 items-center justify-center text-sm text-zinc-500">
										Loading incidents...
									</div>
								) : recentIncidents.length > 0 ? (
									recentIncidents.map((incident) => (
										<IncidentItem key={incident.id} incident={incident} />
									))
								) : (
									<div className="rounded-xl border border-dashed border-zinc-800 bg-zinc-950/60 p-6 text-center">
										<Video size={28} className="mx-auto text-zinc-700" />
										<p className="mt-3 text-sm font-semibold text-zinc-300">No incidents yet</p>
										<p className="mt-2 text-xs leading-relaxed text-zinc-500">
											Run the selected `edge_ai` source and keep this view open. New events will appear here automatically.
										</p>
									</div>
								)}
							</div>

							<div className="mt-4 rounded-xl border border-zinc-800 bg-black/40 p-4">
								<div className="flex items-start gap-3">
									<div className="rounded-lg border border-vs-orange/30 bg-vs-orange/10 p-2 text-vs-orange">
										<Target size={16} />
									</div>
									<div>
										<p className="text-xs font-semibold text-white">How to use this screen</p>
										<p className="mt-2 text-[11px] leading-relaxed text-zinc-400">
											Select a test video above, run the same file in `edge_ai`, and keep the dashboard open. The video preview comes from the backend media route, while incidents are refreshed live from the API.
										</p>
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>
	);
};

export default LiveMonitoring;