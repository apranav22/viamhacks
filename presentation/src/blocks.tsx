// [codex/unknown · op Ali · Mac.mynetworksettings.com · ali/judges-presentation · 2026-11-14]
import { defineBlock } from '../vendor/deck/index.ts';
import type { CSSProperties } from 'react';

const files = import.meta.glob('../../site/img/judges-*.jpg', { eager: true, query: '?url', import: 'default' });
export const asset = (name: string) => files[`../../site/img/${name}`] as string;
export const teal = '#13796b';
export const red = '#b74435';
export const grey = '#6b706e';

type TextProps = { text: string; width?: number; height?: number; size?: number; color?: string; weight?: number; mono?: boolean; align?: CSSProperties['textAlign'] };
export const Text = defineBlock({
  kind: 'text',
  size: ({ width = 600, height = 60 }: TextProps) => ({ width, height }),
  enter: { opacity: 0, scale: 1 }, exit: { opacity: 0, scale: 1 },
  render: ({ text, size = 26, color = '#202723', weight = 400, mono, align = 'left' }: TextProps) => (
    <div className={mono ? 'mono' : undefined} style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: align === 'center' ? 'center' : 'flex-start', fontSize: size, lineHeight: 1.28, whiteSpace: 'pre-wrap', color, fontWeight: weight, textAlign: align }}>{text}</div>
  ),
});

type PhotoProps = { image: string; alt: string; width: number; height: number; box?: number[]; label?: string; fit?: 'cover' | 'contain' };
export const Photo = defineBlock({
  kind: 'photo',
  size: ({ width, height }: PhotoProps) => ({ width, height }),
  render: ({ image, alt, width, height, box, label, fit = 'contain' }: PhotoProps) => (
    <figure className="photo" style={{ width, height }}>
      <img src={asset(image)} alt={alt} style={{ objectFit: fit }} draggable={false} />
      {box && <svg viewBox="0 0 1280 720" className="detection" aria-label="Saved detection bounding box"><rect x={box[0]} y={box[1]} width={box[2]-box[0]} height={box[3]-box[1]} fill="none" stroke="#8ff1ca" strokeWidth="4" /></svg>}
      {label && <figcaption>{label}</figcaption>}
    </figure>
  ),
});

type NodeProps = { label: string; sub?: string; active?: boolean; width?: number; height?: number; tone?: string };
export const Node = defineBlock({
  kind: 'node',
  size: ({ width = 230, height = 104 }: NodeProps) => ({ width, height }),
  render: ({ label, sub, active, tone = teal }: NodeProps) => (
    <div className="node" style={{ borderColor: active ? tone : '#d8dfdb', background: active ? `${tone}09` : 'white' }}>
      <div style={{ color: active ? tone : '#606963', fontSize: 27, fontWeight: 500 }}>{label}</div>
      {sub && <div style={{ fontSize: 17, color: grey, marginTop: 9 }}>{sub}</div>}
    </div>
  ),
});

type MeterProps = { score: number; threshold: number; width?: number; height?: number; label?: string };
export const Meter = defineBlock({
  kind: 'meter', size: ({ width = 490, height = 155 }: MeterProps) => ({ width, height }),
  render: ({ score, threshold, label }: MeterProps) => {
    const ratio = score / threshold;
    return <div className="meter">
      <div className="meter-heading"><span>{label || 'Anomaly score'}</span><span className="mono" style={{ color: ratio >= 1 ? red : teal }}>{score.toFixed(2)}</span></div>
      <div className="meter-track"><div style={{ width: `${Math.min(ratio/1.5,1)*100}%`, background: ratio >= 1 ? red : teal }} /><i style={{ left: `${100/1.5}%` }} /></div>
      <div className="meter-axis"><span>0</span><span>Threshold {threshold.toFixed(2)}</span></div>
    </div>;
  },
});

type RecordProps = { lines: { key: string; value: string; highlight?: boolean }[]; width?: number; height?: number };
export const Record = defineBlock({
  kind: 'record', size: ({ width = 920, height = 390 }: RecordProps) => ({ width, height }),
  render: ({ lines }: RecordProps) => <div className="record mono">{lines.map(line => <div key={line.key} style={{ color: line.highlight ? teal : undefined }}><span>{line.key}</span><strong>{line.value}</strong></div>)}</div>,
});

type ResultsProps = { rows: { label: string; total: number; flagged: number; clear: number; unknown: number }[] };
export const Results = defineBlock({
  kind: 'results', size: (_: ResultsProps) => ({ width: 1152, height: 390 }),
  render: ({ rows }: ResultsProps) => <div className="results"><div className="results-heading"><span>Saved label</span><span>Flagged</span><span>Clear</span><span>Uncertain</span></div>{rows.map(row => <div className="results-row" key={row.label}><span>{row.label}<small>{row.total} test picks</small></span><span style={{ color: row.label === 'Good' ? red : teal }}>{row.flagged}</span><span style={{ color: row.label === 'Good' ? teal : red }}>{row.clear}</span><span>{row.unknown || '—'}</span></div>)}</div>,
});
