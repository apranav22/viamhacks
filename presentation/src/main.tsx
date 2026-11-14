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
        <p>This presentation uses saved captures and recorded results. It does not connect to the robot.</p>
        <h3>Recorded sorting cycle</h3><p className="mono">runs/{evidence.live.pick}/meta.json<br/>runs/20261113_173234_sort/decisions.jsonl</p>
        <p>Original decision: reject. Trigger: {evidence.live.decision.reason}. A logged release does not establish independently verified destination placement. The row has no calibrated confidence field.</p>
        <h3>Offline candidate replay</h3><p className="mono">runs/_analysis/curated-candidate-top-replay.json</p><p>Top view, CPU, automatic size routing, margin 1.15. Candidate not activated. All 171 source-image hashes verified during preparation. Test counts: 34 good and 28 labeled defect picks; train/calibration rows are excluded from the result table. Pick splits repeat physical specimens.</p>
        <p>Marker and missed-tape examples were originally collected without a model. Their displayed scores come from the later replay. Reconstructed model inputs use the saved bbox and part-top-v2; they are not anomaly heatmaps.</p>
        <h3>Event brief</h3><p>Viam Overview, p6: six judge items, five-minute run and five-minute explanation; decision, execution, latency, recovery, log contract. Reference sheet, pp9–10: device-placement rationale, OpenVINO setup and baseline limitations. Their emphasis differs; this deck covers both without assuming final score weights.</p>
        <h3>Supporting records</h3><ul>{evidence.sources.map(s=><li key={s.path}>{s.path}</li>)}</ul>
        <p>Engine adapted from Amphibian-AI/amphibian-platform-v2, commit <code>0a55bb06d4e05c0c5cd3e627d44cd29e88b36b3a</code>, packages/deck. No customer pitch content included.</p>
        <p><a href="./evidence.json" target="_blank" rel="noreferrer">Open complete provenance manifest ↗</a></p>
      </div>}
    </dialog>
    <div className="sr-only" role="status" aria-live="polite">Step {index+1} of {all.length}: {all[index].slide.title}, {all[index].position.step}</div>
  </>;
}

createRoot(document.getElementById('root')!).render(<App/>);
