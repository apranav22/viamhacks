// [codex/unknown · op Ali · Mac.mynetworksettings.com · ali/judges-presentation · 2026-11-14]
import { createRoot } from 'react-dom/client';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Player } from '../vendor/deck/player.tsx';
import { parseDeck, places, placeIndex, formatPosition } from '../vendor/deck/index.ts';
import definition from './deck.tsx';
import evidence from './evidence.json';
import './style.css';

const parsed = parseDeck(definition);
if(parsed._tag === 'Err') throw new Error(JSON.stringify(parsed.error));
const all = places(parsed.value);
const subscribe = (fn: () => void) => { window.addEventListener('hashchange',fn); return () => window.removeEventListener('hashchange',fn); };
const snapshot = () => window.location.hash;

function App() {
  const hash = useSyncExternalStore(subscribe,snapshot);
  const index = placeIndex(all, hash);
  const [panel,setPanel] = useState<'notes'|'sources'|'chapters'|null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const presenter = new URLSearchParams(location.search).get('view') === 'presenter';
  const go = (delta: number) => { const target=all[Math.max(0,Math.min(all.length-1,index+delta))]; location.replace(formatPosition(target.position)); };
  const full = () => { if(document.fullscreenElement) void document.exitFullscreen(); else void document.documentElement.requestFullscreen().catch(()=>{}); };
  useEffect(()=>{
    if(panel) dialog.current?.showModal(); else dialog.current?.close();
  },[panel]);
  useEffect(()=>{
    const key=(e:KeyboardEvent)=>{
      if((e.target as HTMLElement).closest('button,a,input,dialog')) return;
      if(e.key.toLowerCase()==='n') setPanel(p=>p==='notes'?null:'notes');
      if(e.key.toLowerCase()==='g') setPanel('chapters');
      if(e.key.toLowerCase()==='f') full();
    };
    window.addEventListener('keydown',key);return ()=>window.removeEventListener('keydown',key);
  },[]);
  return <>
    <Player deck={definition}/>
    <div className="transport" aria-label="Presentation controls">
      <span className="deck-name">Spot it, sort it</span>
      <div className="step-controls"><button onClick={()=>go(-1)} disabled={index===0} aria-label="Previous step">←</button><button className="position" onClick={()=>setPanel('chapters')} aria-label="Choose a step">{String(index+1).padStart(2,'0')} / {all.length}</button><button onClick={()=>go(1)} disabled={index===all.length-1} aria-label="Next step">→</button></div>
      <div className="tools"><button onClick={()=>setPanel('notes')}>Notes</button><button onClick={()=>setPanel('sources')}>Sources</button>{!presenter && <a href={`?view=presenter${hash}`} target="_blank" rel="noreferrer">Presenter ↗</a>}<button onClick={full} aria-label="Toggle fullscreen">Fullscreen</button></div>
    </div>
    <dialog ref={dialog} onCancel={()=>setPanel(null)} onClick={e=>{if(e.target===dialog.current)setPanel(null);}} aria-label={panel ? `${panel} panel` : 'Presentation panel'}>
      <header><h2>{panel==='notes' ? 'Speaker notes' : panel==='sources' ? 'Sources & evidence' : 'Choose a step'}</h2><button onClick={()=>setPanel(null)} aria-label="Close panel">Close ×</button></header>
      {panel==='notes' && <><h3>{all[index].slide.title} · {index+1} / {all.length}</h3><p className="speaker-notes">{all[index].step.notes}</p><p className="hint">Arrow keys / Space: advance · N: notes · G: steps · F: fullscreen</p></>}
      {panel==='chapters' && <ol className="step-list">{all.map((place,i)=><li key={formatPosition(place.position)}><a href={formatPosition(place.position)} aria-current={i===index?'step':undefined} onClick={()=>setPanel(null)}><span className="mono">{String(i+1).padStart(2,'0')}</span>{place.slide.title}<span>{place.position.step}</span></a></li>)}</ol>}
      {panel==='sources' && <div className="sources">
        <p>Every image is a saved capture and every number comes from a recorded run, a config file measured on the arm, or an offline evaluation. The presentation does not connect to the robot.</p>
        <h3>Images</h3><p className="mono">wrist views: runs/20261114_103009_collect/item_002 · webcam views: runs/20261114_104514_collect/item_001<br/>presentation/src/pipeline_assets.json (source and asset SHA-256)</p>
        <h3>Detection choices</h3><p className="mono">docs/OVERNIGHT_FINDINGS_20261114.md · exp/backbone_top/summary.md · docs/THRESHOLD_FINDINGS.md · docs/TRAINING_RUN_20261114.md</p><p>Colour rule 22/28 (all blue) and model 6/6 on the non-blue defects, backbone 12/28 vs 6/28, crop repair 25–26 vs 22–24 of 28, type classifier 103/112 vs 78/112: all on development picks that repeat physical parts.</p>
        <h3>Device placement</h3><p className="mono">docs/INTEL.md (device_report.json: CPU 6.30 / GPU 8.51 ms p50) · docs/THRESHOLD_FINDINGS.md (NPU ~7.7 ms) · docs/CONTEXT.md (reference PatchCore: GPU 23–31, CPU 75–77, NPU 158 ms or no compile)</p>
        <h3>Motion, poses, calibration</h3><p className="mono">config/checkpoint.json · config/poses.json · config/obstacles.json · vh/coverage.py · vh/kinematics.py · sort.py · docs/AGENT_LOG.md</p>
        <h3>Day-1 record</h3><p className="mono">docs/DAY1_RECAP.md · runs/{evidence.live.pick}</p>
        <h3>Day-2 numbers</h3><p className="mono">presentation/src/today.json (filled by presentation/set_row.py; empty fields fall back to day-1 figures, labelled)</p>
        <p>Engine adapted from Amphibian-AI/amphibian-platform-v2, commit <code>0a55bb06d4e05c0c5cd3e627d44cd29e88b36b3a</code>, packages/deck. No customer pitch content included.</p>
      </div>}
    </dialog>
    <div className="sr-only" role="status" aria-live="polite">Step {index+1} of {all.length}: {all[index].slide.title}, {all[index].position.step}</div>
  </>;
}

createRoot(document.getElementById('root')!).render(<App/>);
