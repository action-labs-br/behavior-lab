import { useEffect, useMemo, useRef, useState } from 'react';
import { Pause, Play, RotateCcw } from 'lucide-react';

const API = import.meta.env.VITE_API_URL ?? '';
const WORLD = { width: 800, height: 600, hud: 40, player: 50, target: 70 };
type Evaluation = {
  id: string;
  episodes: { episode_id: number; outcome: string; steps: number }[];
};
type Frame = { blue_x: number; blue_y: number; target_x: number; target_y: number };

type ApiFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export default function EvaluationReplay({ evaluation, apiFetch }: { evaluation: Evaluation; apiFetch: ApiFetch }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [episodeId, setEpisodeId] = useState(1);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [error, setError] = useState('');
  const episode = evaluation.episodes.find((item) => item.episode_id === episodeId);
  const replayFrames = useMemo(() => {
    if (episode?.outcome !== 'stalled' || frames.length < 2) return frames;
    let lastMovement = 0;
    for (let frameIndex = 1; frameIndex < frames.length; frameIndex += 1) {
      const previous = frames[frameIndex - 1];
      const frame = frames[frameIndex];
      if (frame.blue_x !== previous.blue_x || frame.blue_y !== previous.blue_y) lastMovement = frameIndex;
    }
    return frames.slice(0, lastMovement + 1);
  }, [episode?.outcome, frames]);
  const current = replayFrames[index];

  useEffect(() => {
    let cancelled = false;
    setFrames([]); setIndex(0); setPlaying(true); setError('');
    apiFetch(`${API}/api/v1/evaluations/${evaluation.id}/replay?episode_id=${episodeId}`)
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail ?? 'Could not load replay.');
        return payload.frames as Frame[];
      })
      .then((result) => { if (!cancelled) setFrames(result); })
      .catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : 'Could not load replay.'); });
    return () => { cancelled = true; };
  }, [apiFetch, evaluation.id, episodeId]);

  useEffect(() => {
    if (!playing || replayFrames.length === 0) return;
    const timer = window.setInterval(() => {
      if (index < replayFrames.length - 1) {
        setIndex(index + 1);
        return;
      }
      const episodeIndex = evaluation.episodes.findIndex((item) => item.episode_id === episodeId);
      const nextEpisode = evaluation.episodes[episodeIndex + 1];
      if (nextEpisode) {
        setPlaying(false);
        window.setTimeout(() => {
          setEpisodeId(nextEpisode.episode_id);
          setIndex(0);
          setPlaying(true);
        }, 1000);
      } else setPlaying(false);
    }, 45);
    return () => window.clearInterval(timer);
  }, [playing, replayFrames.length, evaluation.episodes, episodeId, index]);

  useEffect(() => {
    const element = canvas.current;
    if (!element || !current) return;
    const context = element.getContext('2d');
    if (!context) return;
    const scale = Math.min(element.clientWidth / WORLD.width, element.clientHeight / WORLD.height);
    const pixelRatio = window.devicePixelRatio || 1;
    const width = Math.round(WORLD.width * scale * pixelRatio);
    const height = Math.round(WORLD.height * scale * pixelRatio);
    if (element.width !== width || element.height !== height) { element.width = width; element.height = height; }
    context.setTransform(pixelRatio * scale, 0, 0, pixelRatio * scale, 0, 0);
    context.fillStyle = '#eef3f8'; context.fillRect(0, 0, WORLD.width, WORLD.height);
    context.fillStyle = '#fff'; context.fillRect(0, 0, WORLD.width, WORLD.hud);
    context.strokeStyle = '#d9e2ec'; context.lineWidth = 2; context.strokeRect(1, 1, WORLD.width - 2, WORLD.hud - 2);
    context.strokeStyle = '#c9d6e2'; context.lineWidth = 1;
    for (let x = 0; x < WORLD.width; x += 40) { context.beginPath(); context.moveTo(x, WORLD.hud); context.lineTo(x, WORLD.height); context.stroke(); }
    for (let y = WORLD.hud; y < WORLD.height; y += 40) { context.beginPath(); context.moveTo(0, y); context.lineTo(WORLD.width, y); context.stroke(); }
    const visibleFrames = replayFrames.slice(0, index + 1);
    if (visibleFrames.length > 1) {
      context.beginPath();
      context.moveTo(visibleFrames[0].blue_x + WORLD.player / 2, visibleFrames[0].blue_y + WORLD.player / 2);
      for (const frame of visibleFrames.slice(1)) {
        context.lineTo(frame.blue_x + WORLD.player / 2, frame.blue_y + WORLD.player / 2);
      }
      context.strokeStyle = '#2475e8'; context.globalAlpha = 0.55; context.lineWidth = 3;
      context.lineCap = 'round'; context.lineJoin = 'round'; context.stroke();
      context.globalAlpha = 1;
    }
    context.fillStyle = '#fff'; context.fillRect(current.target_x, current.target_y, WORLD.target, WORLD.target);
    context.strokeStyle = '#233245'; context.lineWidth = 3; context.strokeRect(current.target_x + 1.5, current.target_y + 1.5, WORLD.target - 3, WORLD.target - 3);
    context.beginPath(); context.arc(current.blue_x + WORLD.player / 2, current.blue_y + WORLD.player / 2, WORLD.player / 2, 0, Math.PI * 2);
    const outcome = episode?.outcome;
    const showingResult = index === replayFrames.length - 1;
    context.fillStyle = showingResult && outcome
      ? outcome === 'success' ? '#2eaa68' : '#e34d4d'
      : '#2475e8';
    context.fill();
    context.fillStyle = '#344256'; context.font = '600 15px Inter, system-ui, sans-serif';
    context.fillText(`EPISODE ${episodeId}   ·   STEP ${index} / ${Math.max(0, replayFrames.length - 1)}`, 18, 26);
  }, [current, episode, episodeId, replayFrames, index]);

  return <div className="replay-panel">
    <div className="replay-heading"><div><strong>Policy replay</strong><small>{episode ? `${episode.outcome.replaceAll('_', ' ')} · ${episode.steps} steps` : 'Loading episode…'}</small></div>
      <label>EPISODE<select value={episodeId} onChange={(event) => setEpisodeId(Number(event.target.value))}>{evaluation.episodes.map((item) => <option key={item.episode_id} value={item.episode_id}>Episode {item.episode_id} · {item.outcome.replaceAll('_', ' ')}</option>)}</select></label>
    </div>
    <canvas ref={canvas} className="replay-canvas" width={800} height={600} aria-label="Trained policy evaluation replay" />
    {error && <div className="run-error">{error}</div>}
    <div className="replay-controls"><button className="button secondary" onClick={() => setPlaying((value) => !value)} disabled={!frames.length}>{playing ? <Pause size={14} /> : <Play size={14} />}{playing ? 'Pause' : 'Play'}</button>
      <button className="button secondary" onClick={() => { setIndex(0); setPlaying(true); }} disabled={!frames.length}><RotateCcw size={14} /> Restart</button>
      <input type="range" min={0} max={Math.max(0, replayFrames.length - 1)} value={index} onChange={(event) => { setIndex(Number(event.target.value)); setPlaying(false); }} aria-label="Replay position" disabled={!replayFrames.length} />
      <span>{replayFrames.length ? `${index} / ${replayFrames.length - 1}` : 'Loading…'}</span>
    </div>
  </div>;
}
