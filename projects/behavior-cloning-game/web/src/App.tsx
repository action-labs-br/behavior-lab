import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Check, ChevronRight,
  BarChart3, CircleHelp, Download, FolderKanban, Gamepad2, LoaderCircle, Pause,
  LogOut, Play, Plus, RotateCcw, Sparkles, Target, Trophy, X,
} from 'lucide-react';
import EvaluationReplay from './EvaluationReplay';
import { accessToken, beginSignIn, currentSession, endSignIn, loadAuthConfig, type AuthConfig } from './auth';

const API = import.meta.env.VITE_API_URL ?? '';
const WORLD = { width: 800, height: 600, hud: 40, player: 50, target: 70, speed: 5 };
type Outcome = 'success' | 'out_of_bounds' | 'stalled' | 'quit';
type Project = { id: string; name: string; created_at: string; dataset_count: number };
type Dataset = {
  id: string; name: string; row_count: number; episode_count: number;
  outcomes: Record<string, number>; no_op_ratio: number; created_at: string;
};
type DatasetMetrics = {
  samples: number; episodes: number; no_op_ratio: number;
  outcomes: Record<string, number>; action_histogram: { action: string; count: number }[];
};
type TrainingRun = {
  id: string; dataset_id: string; status: 'queued' | 'running' | 'cancel_requested' | 'completed' | 'failed' | 'cancelled';
  preset: string; config: { epochs: number; feature_transform: string; seed: number; drop_noop?: boolean };
  progress: { epoch: number; epochs_total: number; train_loss: number[]; validation_loss: number[] };
  error_message?: string; created_at: string;
  metrics?: { best_epoch: number; final_validation_loss: number | null } | null;
};
type Evaluation = {
  id: string; training_run_id: string; created_at: string;
  config: { episodes: number; max_steps: number; seed: number };
  metrics: { episodes: number; successes: number; success_rate: number; mean_successful_steps: number | null; median_successful_steps: number | null; stalled: number; out_of_bounds: number };
  episodes: { episode_id: number; outcome: string; steps: number }[];
};
type Sample = {
  schema_version: 2; episode_id: number; step: number; elapsed_ms: number;
  blue_x: number; blue_y: number; target_x: number; target_y: number;
  action_x: number; action_y: number; outcome: Outcome;
};
type Point = { x: number; y: number };

function App() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const player = useRef<Point>({ x: 375, y: 275 });
  const target = useRef<Point>({ x: 0, y: 0 });
  const pressed = useRef(new Set<string>());
  const buffer = useRef<Sample[]>([]);
  const episode = useRef(0);
  const step = useRef(0);
  const started = useRef(0);
  const sessionSeed = useRef(0);
  const randomState = useRef(0);
  const pausedRef = useRef(false);
  const roundOutcome = useRef<Outcome | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [metricsDataset, setMetricsDataset] = useState<Dataset | null>(null);
  const [datasetMetrics, setDatasetMetrics] = useState<DatasetMetrics | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metricsError, setMetricsError] = useState('');
  const [runs, setRuns] = useState<TrainingRun[]>([]);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [evaluatingRun, setEvaluatingRun] = useState<string | null>(null);
  const [selectedEvaluation, setSelectedEvaluation] = useState<string | null>(null);
  const [evaluationSettings, setEvaluationSettings] = useState<Record<string, { episodes: number; seed: number }>>({});
  const [trainingPreset, setTrainingPreset] = useState('quick');
  const [featureTransform, setFeatureTransform] = useState('absolute');
  const [dropNoop, setDropNoop] = useState(false);
  const [startingRun, setStartingRun] = useState<string | null>(null);
  const [name, setName] = useState('My first project');
  const [collecting, setCollecting] = useState(false);
  const [paused, setPaused] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [episodeCount, setEpisodeCount] = useState(0);
  const [samplesCount, setSamplesCount] = useState(0);
  const [lastOutcome, setLastOutcome] = useState<Outcome | null>(null);
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
  const [authStatus, setAuthStatus] = useState<'loading' | 'local' | 'signed-out' | 'signed-in' | 'error'>('loading');
  const [authMessage, setAuthMessage] = useState('');
  const [username, setUsername] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState('play-the-game');

  useEffect(() => {
    let active = true;
    void loadAuthConfig().then(async (config) => {
      if (!active) return;
      setAuthConfig(config);
      if (!config.authentication_enabled) {
        setAuthStatus('local');
        return;
      }
      const session = await currentSession();
      if (active) {
        setUsername(session.username);
        setAuthStatus(session.signedIn ? 'signed-in' : 'signed-out');
      }
    }).catch((error: unknown) => {
      if (!active) return;
      setAuthMessage(error instanceof Error ? error.message : 'Could not start sign-in.');
      setAuthStatus('error');
    });
    return () => { active = false; };
  }, []);

  const apiFetch = useCallback(async (input: RequestInfo | URL, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    if (authConfig?.authentication_enabled) {
      const token = await accessToken();
      if (!token) {
        setAuthStatus('signed-out');
        throw new Error('Sign in again to continue.');
      }
      headers.set('Authorization', `Bearer ${token}`);
    }
    return fetch(input, { ...init, headers });
  }, [authConfig]);

  const startSignIn = async () => {
    try { await beginSignIn(); }
    catch (error) { setAuthMessage(error instanceof Error ? error.message : 'Could not open sign-in.'); }
  };

  const stopSignIn = async () => {
    try { await endSignIn(); }
    catch (error) { setAuthMessage(error instanceof Error ? error.message : 'Could not sign out.'); }
  };

  const loadProjects = useCallback(async () => {
    try {
      const response = await apiFetch(`${API}/api/v1/projects`);
      if (!response.ok) throw new Error('The API did not respond.');
      setProjects(await response.json());
    } catch {
      setNotice('Could not load projects. Check the service and sign-in status.');
    }
  }, [apiFetch]);

  useEffect(() => {
    if (authConfig?.service_enabled && (authStatus === 'local' || authStatus === 'signed-in')) void loadProjects();
  }, [authConfig, authStatus, loadProjects]);

  const loadDatasets = useCallback(async (projectId: string) => {
    const response = await apiFetch(`${API}/api/v1/projects/${projectId}/datasets`);
    if (response.ok) setDatasets(await response.json());
  }, [apiFetch]);

  const loadRuns = useCallback(async (projectId: string) => {
    const response = await apiFetch(`${API}/api/v1/projects/${projectId}/training-runs`);
    if (response.ok) setRuns(await response.json());
  }, [apiFetch]);

  const loadEvaluations = useCallback(async (projectId: string) => {
    const response = await apiFetch(`${API}/api/v1/projects/${projectId}/evaluations`);
    if (response.ok) setEvaluations(await response.json());
  }, [apiFetch]);

  const openProject = (item: Project) => {
    setProject(item);
    setNotice('');
    void loadDatasets(item.id);
    void loadRuns(item.id);
    void loadEvaluations(item.id);
  };

  useEffect(() => {
    if (!project || !runs.some((run) => ['queued', 'running', 'cancel_requested'].includes(run.status))) return;
    const interval = window.setInterval(() => { void loadRuns(project.id); }, 2000);
    return () => window.clearInterval(interval);
  }, [project, runs, loadRuns]);

  const createProject = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      const response = await apiFetch(`${API}/api/v1/projects`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmed }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? 'Could not create project.');
      setProjects((current) => [result, ...current]);
      openProject(result);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not create project.');
    }
  };

  const startEpisode = useCallback(() => {
    roundOutcome.current = null;
    player.current = { x: (WORLD.width - WORLD.player) / 2, y: (WORLD.height - WORLD.player) / 2 };
    const random = () => {
      randomState.current ^= randomState.current << 13;
      randomState.current ^= randomState.current >>> 17;
      randomState.current ^= randomState.current << 5;
      return (randomState.current >>> 0) / 4_294_967_296;
    };
    target.current = {
      x: Math.floor(random() * (WORLD.width - WORLD.target)),
      y: WORLD.hud + Math.floor(random() * (WORLD.height - WORLD.hud - WORLD.target)),
    };
    buffer.current = [];
    step.current = 0;
    started.current = performance.now();
    setLastOutcome(null);
  }, []);

  const finishEpisode = useCallback((outcome: Outcome) => {
    if (roundOutcome.current) return;
    roundOutcome.current = outcome;
    const completed = buffer.current.map((sample) => ({ ...sample, outcome }));
    buffer.current = [];
    if (completed.length) {
      // Keep session data in memory until the learner saves the collection.
      sessionRows.current.push(...completed);
      setSamplesCount(sessionRows.current.length);
      setEpisodeCount((current) => current + 1);
      episode.current += 1;
    }
    setLastOutcome(outcome);
    window.setTimeout(startEpisode, 1000);
  }, [startEpisode]);

  const sessionRows = useRef<Sample[]>([]);

  useEffect(() => {
    if (!collecting || paused) return;
    let frame = 0;
    let animation = 0;
    let lastStepAt = 0;
    const draw = (timestamp: number) => {
      const element = canvas.current;
      if (!element) return;
      const context = element.getContext('2d');
      if (!context) return;
      if (!roundOutcome.current && (!lastStepAt || timestamp - lastStepAt >= 1000 / 60)) {
        lastStepAt = timestamp;
        const actionX = (pressed.current.has('ArrowRight') ? WORLD.speed : 0) - (pressed.current.has('ArrowLeft') ? WORLD.speed : 0);
        const actionY = (pressed.current.has('ArrowDown') ? WORLD.speed : 0) - (pressed.current.has('ArrowUp') ? WORLD.speed : 0);
        const before = { ...player.current };
        const goal = target.current;
        player.current = { x: before.x + actionX, y: before.y + actionY };
        step.current += 1;
        buffer.current.push({
          schema_version: 2, episode_id: episode.current + 1, step: step.current - 1,
          elapsed_ms: Math.round(performance.now() - started.current),
          blue_x: before.x, blue_y: before.y, target_x: goal.x, target_y: goal.y,
          action_x: actionX, action_y: actionY, outcome: 'quit',
        });
        const inside = player.current.x >= goal.x && player.current.x + WORLD.player <= goal.x + WORLD.target
          && player.current.y >= goal.y && player.current.y + WORLD.player <= goal.y + WORLD.target;
        const outside = player.current.x < 0 || player.current.y < WORLD.hud
          || player.current.x > WORLD.width - WORLD.player || player.current.y > WORLD.height - WORLD.player;
        if (inside) { finishEpisode('success'); }
        else if (outside) { finishEpisode('out_of_bounds'); }
        else if (step.current >= 500) { finishEpisode('stalled'); }
      }

      const scale = Math.min(element.clientWidth / WORLD.width, element.clientHeight / WORLD.height);
      const pixelRatio = window.devicePixelRatio || 1;
      const width = Math.round(WORLD.width * scale * pixelRatio);
      const height = Math.round(WORLD.height * scale * pixelRatio);
      if (element.width !== width || element.height !== height) { element.width = width; element.height = height; }
      context.setTransform(pixelRatio * scale, 0, 0, pixelRatio * scale, 0, 0);
      context.clearRect(0, 0, WORLD.width, WORLD.height);
      context.fillStyle = '#eef3f8'; context.fillRect(0, 0, WORLD.width, WORLD.height);
      context.fillStyle = '#ffffff'; context.fillRect(0, 0, WORLD.width, WORLD.hud);
      context.strokeStyle = '#d9e2ec'; context.lineWidth = 2; context.strokeRect(1, 1, WORLD.width - 2, WORLD.hud - 2);
      context.strokeStyle = '#c9d6e2'; context.lineWidth = 1;
      for (let x = 0; x < WORLD.width; x += 40) { context.beginPath(); context.moveTo(x, WORLD.hud); context.lineTo(x, WORLD.height); context.stroke(); }
      for (let y = WORLD.hud; y < WORLD.height; y += 40) { context.beginPath(); context.moveTo(0, y); context.lineTo(WORLD.width, y); context.stroke(); }
      context.fillStyle = '#ffffff'; context.fillRect(target.current.x, target.current.y, WORLD.target, WORLD.target);
      context.strokeStyle = '#233245'; context.lineWidth = 3; context.strokeRect(target.current.x + 1.5, target.current.y + 1.5, WORLD.target - 3, WORLD.target - 3);
      context.beginPath(); context.arc(player.current.x + WORLD.player / 2, player.current.y + WORLD.player / 2, WORLD.player / 2, 0, Math.PI * 2);
      context.fillStyle = roundOutcome.current === 'success' ? '#2eaa68'
        : roundOutcome.current ? '#e34d4d' : '#2475e8'; context.fill();
      context.fillStyle = '#344256'; context.font = '600 15px Inter, system-ui, sans-serif';
      context.fillText(`EPISODE ${episode.current + 1}   ·   ${sessionRows.current.length.toLocaleString()} SAMPLES`, 18, 26);
      animation = window.requestAnimationFrame(draw);
      frame += 1;
    };
    animation = window.requestAnimationFrame(draw);
    return () => { window.cancelAnimationFrame(animation); void frame; };
  }, [collecting, paused, finishEpisode]);

  useEffect(() => {
    const onDown = (event: KeyboardEvent) => {
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '].includes(event.key)) event.preventDefault();
      if (event.key === ' ' && collecting) { pausedRef.current = !pausedRef.current; setPaused(pausedRef.current); pressed.current.clear(); }
      else if (event.key.startsWith('Arrow')) pressed.current.add(event.key);
    };
    const onUp = (event: KeyboardEvent) => { pressed.current.delete(event.key); };
    window.addEventListener('keydown', onDown); window.addEventListener('keyup', onUp);
    return () => { window.removeEventListener('keydown', onDown); window.removeEventListener('keyup', onUp); };
  }, [collecting]);

  const beginCollection = () => {
    if (sessionRows.current.length && !window.confirm('Start a new session and discard the unsaved demonstrations?')) return;
    sessionRows.current = []; episode.current = 0;
    sessionSeed.current = Math.floor(Math.random() * 2_147_483_647) + 1;
    randomState.current = sessionSeed.current;
    setEpisodeCount(0); setSamplesCount(0); setPaused(false); pausedRef.current = false;
    setCollecting(true); startEpisode();
  };

  const endCollection = async () => {
    const discardedPartial = buffer.current.length > 0;
    buffer.current = [];
    setCollecting(false); pressed.current.clear(); setSaving(true);
    const rows = sessionRows.current;
    if (!rows.length || !project) {
      setSaving(false);
      setNotice(discardedPartial ? 'The unfinished attempt was discarded. Complete an episode before saving a dataset.' : 'Complete an episode before saving a dataset.');
      return;
    }
    try {
      const response = await apiFetch(`${API}/api/v1/projects/${project.id}/datasets`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: `Demonstrations ${new Date().toLocaleDateString()}`, session_seed: sessionSeed.current, rows }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? 'Could not save dataset.');
      sessionRows.current = []; setSamplesCount(0); setEpisodeCount(0);
      await loadDatasets(project.id);
      setNotice(`Saved ${result.episode_count} episodes and ${result.row_count.toLocaleString()} samples.${discardedPartial ? ' The unfinished attempt was discarded.' : ''}`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not save dataset.');
    } finally { setSaving(false); }
  };

  const downloadCsv = async (dataset: Dataset) => {
    const response = await apiFetch(`${API}/api/v1/datasets/${dataset.id}/download`);
    if (!response.ok) { setNotice('Could not download dataset.'); return; }
    const blob = await response.blob(); const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${dataset.name.replace(/[^a-z0-9-]+/gi, '-')}.csv`; anchor.click();
    URL.revokeObjectURL(url);
  };

  const showDatasetMetrics = async (dataset: Dataset) => {
    setMetricsDataset(dataset);
    setDatasetMetrics(null);
    setMetricsError('');
    setMetricsLoading(true);
    try {
      const response = await apiFetch(`${API}/api/v1/datasets/${dataset.id}/metrics`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? 'Could not load dataset metrics.');
      setDatasetMetrics(result);
    } catch (error) {
      setMetricsError(error instanceof Error ? error.message : 'Could not load dataset metrics.');
    } finally {
      setMetricsLoading(false);
    }
  };

  const trainDataset = async (dataset: Dataset) => {
    setStartingRun(dataset.id);
    try {
      const response = await apiFetch(`${API}/api/v1/datasets/${dataset.id}/training-runs`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preset: trainingPreset, feature_transform: featureTransform, seed: 42, drop_noop: dropNoop }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? 'Could not start training.');
      setRuns((current) => [result, ...current.filter((run) => run.id !== result.id)]);
      setNotice(`Training run queued with the ${trainingPreset} preset${dropNoop ? ', dropping no-op actions' : ''}.`);
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Could not start training.';
      setNotice(Array.isArray(detail) ? detail.join(', ') : detail);
    } finally { setStartingRun(null); }
  };

  const cancelRun = async (run: TrainingRun) => {
    const response = await apiFetch(`${API}/api/v1/training-runs/${run.id}/cancel`, { method: 'POST' });
    if (response.ok) {
      const updated = await response.json();
      setRuns((current) => current.map((item) => item.id === updated.id ? updated : item));
    }
  };

  const evaluateRun = async (run: TrainingRun) => {
    const settings = evaluationSettings[run.id] ?? { episodes: 20, seed: 42 };
    setEvaluatingRun(run.id);
    try {
      const response = await apiFetch(`${API}/api/v1/training-runs/${run.id}/evaluations`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ episodes: settings.episodes, max_steps: 500, seed: settings.seed }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? 'Could not evaluate policy.');
      setEvaluations((current) => [result, ...current.filter((item) => item.id !== result.id)]);
      setSelectedEvaluation(result.id);
      setNotice(`Evaluation complete: ${Math.round(result.metrics.success_rate * 100)}% success across ${result.metrics.episodes} episodes.`);
      if (project) await loadEvaluations(project.id);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not evaluate policy.');
    } finally { setEvaluatingRun(null); }
  };

  const downloadEvaluation = async (evaluation: Evaluation) => {
    const response = await apiFetch(`${API}/api/v1/evaluations/${evaluation.id}/download`);
    if (!response.ok) { setNotice('Could not download evaluation.'); return; }
    const blob = await response.blob(); const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `evaluation-${evaluation.id}.json`; anchor.click();
    URL.revokeObjectURL(url);
  };

  const renderTrainingRun = (run: TrainingRun) => {
    const progress = run.progress ?? { epoch: 0, epochs_total: run.config.epochs, train_loss: [], validation_loss: [] };
    const ratio = progress.epochs_total ? Math.min(100, progress.epoch / progress.epochs_total * 100) : 0;
    const latestLoss = progress.validation_loss.at(-1);
    const evaluation = evaluationSettings[run.id] ?? { episodes: 20, seed: 42 };
    const updateEvaluation = (key: 'episodes' | 'seed', value: number) => {
      setEvaluationSettings((current) => ({
        ...current,
        [run.id]: { ...(current[run.id] ?? { episodes: 20, seed: 42 }), [key]: value },
      }));
    };
    return <article className="run-card" key={run.id}>
      <div className="run-topline"><div className="run-icon"><Sparkles size={16} /></div><div className="run-name"><strong>{run.preset} policy</strong><small>{run.config.feature_transform.replaceAll('-', ' ')}{run.config.drop_noop ? ' · no-op dropped' : ''} · {new Date(run.created_at).toLocaleString()}</small></div><span className={`run-status ${run.status}`}>{run.status.replace('_', ' ')}</span>{['queued', 'running'].includes(run.status) && <button className="run-cancel" onClick={() => void cancelRun(run)}>Cancel</button>}</div>
      {['queued', 'running', 'cancel_requested'].includes(run.status) && <><div className="progress-track"><span style={{ width: `${ratio}%` }} /></div><div className="progress-label"><span>{run.status === 'queued' ? 'Waiting for the worker' : `Epoch ${progress.epoch} of ${progress.epochs_total}`}</span><span>{latestLoss === undefined ? 'Preparing data…' : `Validation loss ${latestLoss.toFixed(4)}`}</span></div></>}
      {run.status === 'completed' && <div className="run-result"><span><Check size={14} /> Best epoch {run.metrics?.best_epoch ?? '—'}</span><span>Validation loss {run.metrics?.final_validation_loss?.toFixed(4) ?? '—'}</span><div className="eval-inline-options"><label>EPISODES<input type="number" min={1} max={50} value={evaluation.episodes} onChange={(event) => updateEvaluation('episodes', Math.min(50, Math.max(1, Number(event.target.value))))} /></label><label>SEED<input type="number" min={0} max={2147483647} value={evaluation.seed} onChange={(event) => updateEvaluation('seed', Math.min(2147483647, Math.max(0, Number(event.target.value))))} /></label></div><button className="button train-button evaluate-button" disabled={evaluatingRun !== null} onClick={() => void evaluateRun(run)}>{evaluatingRun === run.id ? <LoaderCircle className="spin" size={14} /> : <Target size={14} />}{evaluatingRun === run.id ? 'Evaluating…' : 'Evaluate policy'}</button></div>}
      {run.status === 'failed' && <div className="run-error">{run.error_message ?? 'Training failed. Try again with another preset.'}</div>}
      {run.status === 'cancelled' && <div className="run-result">This run was cancelled.</div>}
    </article>;
  };

  const navigateTo = (sectionId: string) => {
    setActiveSection(sectionId);
    document.getElementById(sectionId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  if (authStatus === 'loading') return (
    <main className="auth-page"><a className="brand" href="#"><span className="brand-mark"><Sparkles size={17} /></span> behavior<span>lab</span></a><div className="auth-card"><LoaderCircle className="spin" size={20} /><span>Connecting to Behavior Lab…</span></div></main>
  );

  if (authStatus === 'error') return (
    <main className="auth-page"><a className="brand" href="#"><span className="brand-mark"><Sparkles size={17} /></span> behavior<span>lab</span></a><div className="auth-card"><div className="eyebrow"><span className="eyebrow-line" /> SERVICE UNAVAILABLE</div><h1>We couldn't connect.</h1><p>{authMessage || 'The service configuration could not be loaded.'}</p><button className="button primary" onClick={() => window.location.reload()}>Try again</button></div></main>
  );

  if (authConfig && !authConfig.service_enabled) return (
    <main className="auth-page"><a className="brand" href="#"><span className="brand-mark"><Sparkles size={17} /></span> behavior<span>lab</span></a><div className="auth-card"><div className="eyebrow"><span className="eyebrow-line" /> PILOT PAUSED</div><h1>Back soon.</h1><p>The Behavior Lab pilot is paused right now. Your projects and datasets remain stored safely.</p></div></main>
  );

  if (authStatus === 'signed-out') return (
    <main className="auth-page"><a className="brand" href="#"><span className="brand-mark"><Sparkles size={17} /></span> behavior<span>lab</span></a><div className="auth-card"><div className="eyebrow"><span className="eyebrow-line" /> PRIVATE LEARNING LAB</div><h1>Welcome back.</h1><p>Sign in to continue your behavior-cloning projects. Access is limited to invited accounts.</p><button className="button primary" onClick={() => void startSignIn()}>Sign in <ChevronRight size={16} /></button>{authMessage && <div className="notice" role="status">{authMessage}</div>}</div></main>
  );

  if (!project) return (
    <main className="landing">
      <header className="topbar"><a className="brand" href="#"><span className="brand-mark"><Sparkles size={17} /></span> behavior<span>lab</span></a><div className="auth-actions"><span className="top-note"><span className="status-dot" />{authConfig?.authentication_enabled ? ` Signed in${username ? ` as ${username}` : ''}` : ' Local workspace'}</span>{authConfig?.authentication_enabled && <button className="signout-button" onClick={() => void stopSignIn()}><LogOut size={14} /> Sign out</button>}</div></header>
      <section className="hero">
        <div className="hero-copy"><div className="eyebrow"><span className="eyebrow-line" /> AN INTERACTIVE ML LAB</div>
          <h1>Teach a machine<br />by <em>showing</em> it.</h1>
          <p className="hero-text">Record how you solve a simple game. Train a small policy to imitate you. Then see what it learned.</p>
          <form className="create-card" onSubmit={createProject}>
            <label htmlFor="project-name">Start a learning project</label>
            <div className="create-row"><input id="project-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="Give your project a name" /><button className="button primary" type="submit">Create project <ChevronRight size={16} /></button></div>
          </form>
          {notice && <div className="notice" role="status">{notice}</div>}
          {projects.length > 0 && <div className="project-list"><div className="section-kicker">YOUR PROJECTS</div>{projects.map((item) => <button className="project-row" key={item.id} onClick={() => openProject(item)}><span className="project-icon"><FolderKanban size={17} /></span><span><strong>{item.name}</strong><small>{item.dataset_count} datasets</small></span><ChevronRight size={17} /></button>)}</div>}
        </div>
        <div className="hero-art" aria-hidden="true"><div className="art-grid" /><div className="art-target"><span /><span /><span /><span /></div><div className="art-ball" /><div className="art-route route-one" /><div className="art-route route-two" /><div className="art-label label-start">YOUR MOVES</div><div className="art-label label-end">LEARNED POLICY</div><div className="art-chip"><span className="chip-dot" /> imitation in progress</div></div>
      </section>
      <footer className="landing-footer"><span>A small game with a big idea.</span><span>COLLECT <i /> TRAIN <i /> EVALUATE</span></footer>
    </main>
  );

  return (
    <main className="workspace">
      <header className="topbar"><a className="brand" href="#" onClick={(e) => { e.preventDefault(); setProject(null); void loadProjects(); }}><span className="brand-mark"><Sparkles size={17} /></span> behavior<span>lab</span></a><div className="workspace-title"><span>PROJECT</span><strong>{project.name}</strong></div><div className="auth-actions"><span className="top-note"><span className="status-dot" />{authConfig?.authentication_enabled ? ` Signed in${username ? ` as ${username}` : ''}` : ' Local workspace'}</span>{authConfig?.authentication_enabled && <button className="signout-button" onClick={() => void stopSignIn()}><LogOut size={14} /> Sign out</button>}</div></header>
      <div className="workspace-body"><aside className="sidebar"><div className="side-label">LEARNING LAB</div><nav aria-label="Project sections"><button aria-current={activeSection === 'play-the-game' ? 'location' : undefined} className={`side-item ${activeSection === 'play-the-game' ? 'active' : 'muted'}`} onClick={() => navigateTo('play-the-game')}><Gamepad2 size={17} /> Play & collect</button><button aria-current={activeSection === 'demonstration-datasets' ? 'location' : undefined} className={`side-item ${activeSection === 'demonstration-datasets' ? 'active' : 'muted'}`} onClick={() => navigateTo('demonstration-datasets')}><FolderKanban size={17} /> Demonstration Datasets <b>{datasets.length}</b></button><button aria-current={activeSection === 'policy-evaluations' ? 'location' : undefined} className={`side-item ${activeSection === 'policy-evaluations' ? 'active' : 'muted'}`} onClick={() => navigateTo('policy-evaluations')}><Target size={17} /> Policy Evaluations <b>{evaluations.length}</b></button></nav><div className="sidebar-bottom"><CircleHelp size={16} /><span>Every move becomes<br />a training example.</span></div></aside>
        <section className="main-panel"><div className="page-heading" id="play-the-game"><div><div className="eyebrow"><span className="eyebrow-line" /> PLAY & COLLECT</div><h1>Play the game.</h1><p>Move the blue circle fully inside the target. Your completed attempts become examples for the model.</p></div></div>
          <div className="game-layout"><div className="game-column"><div className="game-frame"><div className="canvas-top"><span className="live-label"><span className={collecting ? 'live-dot active' : 'live-dot'} />{collecting ? (paused ? 'PAUSED' : 'RECORDING') : 'READY'}</span><span>800 × 600 PLAYFIELD</span><button className="icon-button" title="Keyboard controls: arrow keys move; space pauses" aria-label="Keyboard controls: arrow keys move; space pauses"><CircleHelp size={16} /></button></div><canvas ref={canvas} className={collecting ? 'game-canvas' : 'game-canvas idle'} width={800} height={600} aria-label="Game playfield" />{!collecting && <div className="game-overlay"><div className="overlay-icon"><Gamepad2 size={24} /></div><strong>Ready when you are</strong><span>Start a collection session and teach by playing.</span><button className="button primary" onClick={beginCollection}><Play size={15} fill="currentColor" /> Start collecting</button></div>}{collecting && paused && <div className="pause-overlay"><Pause size={21} /><strong>Paused</strong><span>Press space or resume when you’re ready.</span><button className="button primary" onClick={() => { pausedRef.current = false; setPaused(false); }}><Play size={15} fill="currentColor" /> Resume</button></div>}</div>
            <div className="game-controls"><div className="key-help"><span>MOVE</span><kbd><ArrowUp size={11} /></kbd><div><kbd><ArrowLeft size={11} /></kbd><kbd><ArrowDown size={11} /></kbd><kbd><ArrowRight size={11} /></kbd></div><span className="space-key"><kbd>SPACE</kbd> pause</span></div><div className="control-actions">{collecting ? <><button className="button secondary" onClick={() => { startEpisode(); setNotice('Current attempt discarded. A fresh attempt is ready.'); }}><RotateCcw size={15} /> Restart attempt</button><button className="button dark" onClick={endCollection} disabled={saving}>{saving ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />} Save collection</button></> : samplesCount > 0 ? <><button className="button dark" onClick={endCollection} disabled={saving}>{saving ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />} Save collection</button><button className="button secondary" onClick={beginCollection}><Play size={15} /> New session</button></> : <button className="button secondary" onClick={beginCollection}><Play size={15} /> New session</button>}</div></div>
          </div><aside className="stats-column"><div className="stat-card primary-stat"><div className="stat-icon blue"><Gamepad2 size={17} /></div><div className="stat-label">COMPLETED EPISODES</div><div className="stat-value">{episodeCount.toString().padStart(2, '0')}</div><div className="stat-foot">{episodeCount < 2 ? `${2 - episodeCount} more needed to train` : 'Ready to train'}</div></div><div className="stat-card"><div className="stat-icon lilac"><Target size={17} /></div><div className="stat-label">RECORDED SAMPLES</div><div className="stat-value">{samplesCount.toLocaleString()}</div><div className="stat-foot">state and action pairs</div></div><div className="outcome-card"><div className="stat-label">LAST ATTEMPT</div>{lastOutcome ? <div className={`outcome-value ${lastOutcome}`}><span />{lastOutcome.replace('_', ' ')}</div> : <div className="outcome-empty">Complete an attempt to see its outcome</div>}</div><div className="tip-card"><div className="tip-title"><Trophy size={15} /> QUICK TIP</div><p>Collect a couple of varied attempts. The model can only imitate patterns it has seen.</p></div></aside></div>
          {notice && <div className="notice workspace-notice" role="status">{notice}<button aria-label="Dismiss message" onClick={() => setNotice('')}><X size={15} /></button></div>}
          <section className="datasets-section" id="demonstration-datasets">
            <div className="datasets-heading">
              <div><div className="section-kicker">YOUR WORK</div><h2>Demonstration datasets</h2></div>
              <span>{datasets.length} DATASET{datasets.length === 1 ? '' : 'S'}</span>
            </div>
            {datasets.length ? <div className="dataset-table">{datasets.map((dataset) => <div className="dataset-item" key={dataset.id}>
              <div className="dataset-row">
                <div className="dataset-symbol"><FolderKanban size={16} /></div>
                <div className="dataset-name"><strong>{dataset.name}</strong><small>{new Date(dataset.created_at).toLocaleString()}</small></div>
                <div className="dataset-metric"><strong>{dataset.episode_count}</strong><small>episodes</small></div>
                <div className="dataset-metric"><strong>{dataset.row_count.toLocaleString()}</strong><small>samples</small></div>
                <div className="dataset-metric"><strong>{Math.round((dataset.outcomes.success ?? 0) / Math.max(1, dataset.episode_count) * 100)}%</strong><small>success</small></div>
                <button className="icon-button" title={`View ${dataset.name} metrics`} aria-label={`View ${dataset.name} metrics`} onClick={() => void showDatasetMetrics(dataset)}><BarChart3 size={16} /></button>
                <button className="icon-button download" aria-label={`Download ${dataset.name} CSV`} onClick={() => void downloadCsv(dataset)}><Download size={16} /></button>
              </div>
              <details className="dataset-teach">
                <summary><Sparkles size={14} /> Teach your policy</summary>
                <div className="dataset-teach-content">
                  <label>TRAINING PRESET<select value={trainingPreset} onChange={(event) => setTrainingPreset(event.target.value)}><option value="quick">Quick · 10 epochs</option><option value="balanced">Balanced · 30 epochs</option><option value="explore">Explore · 50 epochs</option></select></label>
                  <label>STATE FEATURES<select value={featureTransform} onChange={(event) => setFeatureTransform(event.target.value)}><option value="absolute">Absolute position</option><option value="relative-center">Relative to center</option><option value="relative-containment">Relative containment</option></select></label>
                  <label className="drop-noop-option"><input type="checkbox" checked={dropNoop} onChange={(event) => setDropNoop(event.target.checked)} /><span>Drop no-op actions from training</span></label>
                  <button className="button train-button" disabled={dataset.episode_count < 2 || startingRun !== null} onClick={() => void trainDataset(dataset)}>
                    {startingRun === dataset.id ? <LoaderCircle className="spin" size={14} /> : <Sparkles size={14} />}
                    {dataset.episode_count < 2 ? 'Need 2 episodes' : startingRun === dataset.id ? 'Starting…' : 'Train policy'}
                  </button>
                </div>
                {runs.some((run) => run.dataset_id === dataset.id) && <><div className="dataset-runs-heading">Training runs</div><div className="run-list dataset-runs">{runs.filter((run) => run.dataset_id === dataset.id).map(renderTrainingRun)}</div></>}
              </details>
            </div>)}</div> : <div className="empty-datasets"><div className="empty-icon"><Plus size={17} /></div><span>Your saved datasets will show up here.</span><span className="muted-text">Complete and save a collection to get started.</span></div>}
          </section>
          <section className="evaluation-section" id="policy-evaluations">
            <div className="training-heading"><div><div className="section-kicker">POLICY EVALUATIONS</div><h2>See what it learned</h2></div><span>SEEDED · REPRODUCIBLE</span></div>
            {evaluations.length > 0 && <div className="evaluation-list">{evaluations.map((evaluation) => <article className="evaluation-card" key={evaluation.id}>
              <div className="evaluation-summary"><div className="run-icon"><Target size={16} /></div><div className="run-name"><strong>{Math.round(evaluation.metrics.success_rate * 100)}% success</strong><small>{evaluation.config.episodes} episodes · seed {evaluation.config.seed} · {new Date(evaluation.created_at).toLocaleString()}</small></div><span className="run-status completed">{evaluation.metrics.successes}/{evaluation.metrics.episodes} passed</span><button className="button train-button" onClick={() => setSelectedEvaluation((current) => current === evaluation.id ? null : evaluation.id)}>{selectedEvaluation === evaluation.id ? 'Hide replay' : 'View replay'}</button><button className="icon-button download" title="Download evaluation JSON" aria-label="Download evaluation JSON" onClick={() => void downloadEvaluation(evaluation)}><Download size={16} /></button></div>
              <div className="evaluation-metrics"><span>Mean successful steps <b>{evaluation.metrics.mean_successful_steps?.toFixed(1) ?? '—'}</b></span><span>Median <b>{evaluation.metrics.median_successful_steps?.toFixed(1) ?? '—'}</b></span><span>Stalled <b>{evaluation.metrics.stalled}</b></span><span>Out of bounds <b>{evaluation.metrics.out_of_bounds}</b></span></div>
              {selectedEvaluation === evaluation.id && <EvaluationReplay evaluation={evaluation} apiFetch={apiFetch} />}
            </article>)}</div>}
            {!evaluations.length && <div className="empty-datasets evaluation-empty">Evaluate a completed policy to see how reliably it reaches the target.</div>}
          </section>
        </section></div>
      {metricsDataset && <div className="dataset-metrics-backdrop" onClick={() => setMetricsDataset(null)}>
        <section className="dataset-metrics-modal" role="dialog" aria-modal="true" aria-labelledby="dataset-metrics-title" onClick={(event) => event.stopPropagation()}>
          <div className="dataset-metrics-heading"><div><div className="section-kicker">DATASET ANALYSIS</div><h2 id="dataset-metrics-title">{metricsDataset.name}</h2></div><button className="icon-button" aria-label="Close dataset metrics" onClick={() => setMetricsDataset(null)}><X size={18} /></button></div>
          {metricsLoading && <div className="dataset-metrics-message"><LoaderCircle className="spin" size={18} /> Loading dataset metrics…</div>}
          {metricsError && <div className="run-error">{metricsError}</div>}
          {datasetMetrics && <>
            <div className="dataset-metrics-summary"><div><small>Samples</small><strong>{datasetMetrics.samples.toLocaleString()}</strong></div><div><small>Episodes</small><strong>{datasetMetrics.episodes.toLocaleString()}</strong></div><div><small>No-op actions</small><strong>{(datasetMetrics.no_op_ratio * 100).toFixed(1)}%</strong></div></div>
            <div className="dataset-metrics-panels">
              <section><h3>Episode outcomes</h3>{Object.entries(datasetMetrics.outcomes).map(([outcome, count]) => <div className="dataset-outcome-row" key={outcome}><span><i className={`outcome-dot ${outcome}`} />{outcome.replaceAll('_', ' ')}</span><strong>{count}</strong></div>)}</section>
              <section><h3>Action distribution</h3>{datasetMetrics.action_histogram.slice(0, 5).map((item) => <div className="dataset-action-row" key={item.action}><span>{item.action}</span><div><i style={{ width: `${item.count / Math.max(1, datasetMetrics.action_histogram[0]?.count ?? 1) * 100}%` }} /></div><strong>{item.count}</strong></div>)}</section>
            </div>
          </>}
        </section>
      </div>}
    </main>
  );
}

export default App;
