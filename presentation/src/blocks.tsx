// [claude-code/claude-opus-5-5, then claude-code/claude-fable-5-2 · op Ali (git: Ali) · Alis-MacBook-Air.local · ali/judges-presentation · 2026-11-14]
// Visual blocks for the judges deck. Every number drawn here is passed in from deck.tsx, which cites its source.
import { defineBlock } from '../vendor/deck/index.ts';
import type { CSSProperties, ReactNode } from 'react';

const files = import.meta.glob('../../site/img/judges-*.jpg', { eager: true, query: '?url', import: 'default' });
export const asset = (name: string) => files[`../../site/img/${name}`] as string;

export const C = {
  ink: '#111418', ink2: '#3a4047', muted: '#6c7279', line: '#e2dfd8', paper: '#f6f5f1', card: '#ffffff',
  wrist: '#0f6a8a', web: '#b4621b', model: '#5a4bc0', good: '#1e7a4c', bad: '#b3322a',
};
// legacy names used by the evidence slides
export const teal = C.good, red = C.bad, grey = C.muted;

const tint = (hex: string, a = '14') => hex + a;

/* ---------- text ---------- */
type TextProps = { text: string; width?: number; height?: number; size?: number; color?: string; weight?: number; mono?: boolean; align?: CSSProperties['textAlign']; tracking?: number; lh?: number };
export const Text = defineBlock({
  kind: 'text',
  size: ({ width = 600, height = 60 }: TextProps) => ({ width, height }),
  enter: { opacity: 0, scale: 1 }, exit: { opacity: 0, scale: 1 },
  render: ({ text, size = 24, color = C.ink, weight = 400, mono, align = 'left', tracking = 0, lh = 1.3 }: TextProps) => (
    <div className={mono ? 'mono' : undefined} style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: align === 'center' ? 'center' : align === 'right' ? 'flex-end' : 'flex-start', fontSize: size, lineHeight: lh, whiteSpace: 'pre-wrap', color, fontWeight: weight, textAlign: align, letterSpacing: tracking }}>{text}</div>
  ),
});

/* ---------- slide heading: eyebrow + title + optional lede ---------- */
type HeadProps = { eyebrow: string; title: string; lede?: string; accent?: string; width?: number; height?: number };
export const Head = defineBlock({
  kind: 'head',
  size: ({ width = 1300, height = 150 }: HeadProps) => ({ width, height }),
  enter: { opacity: 0, scale: 1 }, exit: { opacity: 0, scale: 1 },
  render: ({ eyebrow, title, lede, accent = C.wrist }: HeadProps) => (
    <div className="head">
      <div className="eyebrow" style={{ color: accent }}><i style={{ background: accent }} />{eyebrow}</div>
      <h1>{title}</h1>
      {lede && <p>{lede}</p>}
    </div>
  ),
});

/* ---------- photo ---------- */
type PhotoProps = { image: string; alt: string; width: number; height: number; tag?: string; tagColor?: string; caption?: string; fit?: 'cover' | 'contain'; box?: number[]; dim?: boolean };
export const Photo = defineBlock({
  kind: 'photo',
  size: ({ width, height }: PhotoProps) => ({ width, height }),
  render: ({ image, alt, width, height, tag, tagColor = C.ink, caption, fit = 'cover', box, dim }: PhotoProps) => (
    <figure className="photo" style={{ width, height, opacity: dim ? 0.35 : 1 }}>
      <img src={asset(image)} alt={alt} style={{ objectFit: fit }} draggable={false} />
      {box && <svg viewBox="0 0 1280 720" className="detection" aria-hidden><rect x={box[0]} y={box[1]} width={box[2]-box[0]} height={box[3]-box[1]} fill="none" stroke="#8ff1ca" strokeWidth="4" /></svg>}
      {tag && <span className="tag" style={{ background: tagColor }}>{tag}</span>}
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  ),
});

/* ---------- pipeline rail ---------- */
export type Stage = { key: string; label: string; sub: string; cam?: 'wrist' | 'web'; scored?: boolean };
type RailProps = { stages: Stage[]; active?: string[]; width?: number; height?: number; compact?: boolean };
export const Rail = defineBlock({
  kind: 'rail',
  size: ({ width = 1300, height = 150 }: RailProps) => ({ width, height }),
  render: ({ stages, active, compact }: RailProps) => (
    <div className={`rail${compact ? ' compact' : ''}`}>
      {stages.map((s, i) => {
        const on = !active || active.includes(s.key);
        const color = s.cam === 'wrist' ? C.wrist : s.cam === 'web' ? C.web : C.ink2;
        return <div key={s.key} className="rail-stage" style={{ opacity: on ? 1 : 0.32, borderTopColor: on ? color : C.line }}>
          <div className="rail-n mono" style={{ color }}>{String(i + 1).padStart(2, '0')}</div>
          <div className="rail-label">{s.label}</div>
          {!compact && <div className="rail-sub">{s.sub}</div>}
          {s.scored && <div className="rail-scored" style={{ color: C.model }}><i />anomaly scored</div>}
        </div>;
      })}
    </div>
  ),
});

/* ---------- card ---------- */
type CardProps = { title: string; body?: string; kicker?: string; accent?: string; width?: number; height?: number; mono?: boolean; muted?: boolean; size?: number };
export const Card = defineBlock({
  kind: 'card',
  size: ({ width = 380, height = 200 }: CardProps) => ({ width, height }),
  render: ({ title, body, kicker, accent = C.ink, muted, size = 26 }: CardProps) => (
    <div className="card" style={{ borderTopColor: accent, opacity: muted ? 0.4 : 1 }}>
      {kicker && <div className="card-kicker mono" style={{ color: accent }}>{kicker}</div>}
      <div className="card-title" style={{ fontSize: size }}>{title}</div>
      {body && <div className="card-body">{body}</div>}
    </div>
  ),
});

/* ---------- stat ---------- */
type StatProps = { value: string; label: string; note?: string; accent?: string; width?: number; height?: number; size?: number };
export const Stat = defineBlock({
  kind: 'stat',
  size: ({ width = 300, height = 180 }: StatProps) => ({ width, height }),
  render: ({ value, label, note, accent = C.ink, size = 64 }: StatProps) => (
    <div className="stat">
      <div className="stat-value" style={{ color: accent, fontSize: size }}>{value}</div>
      <div className="stat-label">{label}</div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  ),
});

/* ---------- coverage ring: schematic cross-section of a part lying on the pad ---------- */
type RingProps = { show?: 'all' | 'wrist' | 'web'; width?: number; height?: number };
const arc = (cx: number, cy: number, r: number, a0: number, a1: number) => {
  // angles in degrees, 0 = straight up, clockwise positive
  const p = (a: number) => [cx + r * Math.sin(a * Math.PI / 180), cy - r * Math.cos(a * Math.PI / 180)];
  const [x0, y0] = p(a0), [x1, y1] = p(a1);
  return `M ${x0} ${y0} A ${r} ${r} 0 ${Math.abs(a1 - a0) > 180 ? 1 : 0} 1 ${x1} ${y1}`;
};
export const Ring = defineBlock({
  kind: 'ring',
  size: ({ width = 560, height = 560 }: RingProps) => ({ width, height }),
  render: ({ show = 'all' }: RingProps) => {
    const cx = 280, cy = 270, r = 92;
    const w = show !== 'web', b = show !== 'wrist';
    const ray = (a: number, len: number, color: string, label: string, on: boolean, out = 1) => {
      const s = Math.sin(a * Math.PI / 180), c = -Math.cos(a * Math.PI / 180);
      const x0 = cx + s * (r + 26), y0 = cy + c * (r + 26), x1 = cx + s * len, y1 = cy + c * len;
      return <g opacity={on ? 1 : 0.15} key={label}>
        <line x1={x1} y1={y1} x2={x0} y2={y0} stroke={color} strokeWidth="2" strokeDasharray="5 6" markerEnd={`url(#ah-${color.slice(1)})`} />
        <rect x={x1 - 9} y={y1 - 9} width="18" height="18" rx="4" fill={color} />
        <text x={x1 + s * 18 * out} y={y1 + c * 18 * out + 5} textAnchor={s > 0.3 ? 'start' : s < -0.3 ? 'end' : 'middle'} fontSize="17" fill={color} fontWeight="600">{label}</text>
      </g>;
    };
    return <svg viewBox="-40 0 640 560" width="100%" height="100%" role="img" aria-label="Schematic cross-section: wrist camera covers the upper two thirds, webcam the lower third">
      <defs>{[C.wrist, C.web].map(col => <marker key={col} id={`ah-${col.slice(1)}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={col} /></marker>)}</defs>
      <line x1="60" y1={cy + r} x2="500" y2={cy + r} stroke={C.line} strokeWidth="2" opacity={b ? 0.35 : 1} />
      <text x="500" y={cy + r + 24} textAnchor="end" fontSize="14" fill={C.muted} opacity={b ? 0.35 : 1}>pick pad</text>
      <circle cx={cx} cy={cy} r={r} fill="#fff" stroke={C.line} strokeWidth="2" />
      <path d={arc(cx, cy, r + 12, -120, 120)} stroke={C.wrist} strokeWidth="14" fill="none" strokeLinecap="butt" opacity={w ? 1 : 0.15} />
      <path d={arc(cx, cy, r + 12, 120, 240)} stroke={C.web} strokeWidth="14" fill="none" strokeLinecap="butt" opacity={b ? 1 : 0.15} />
      <text x={cx} y={cy - 8} textAnchor="middle" fontSize="19" fill={C.ink} fontWeight="600">part</text>
      <text x={cx} y={cy + 18} textAnchor="middle" fontSize="14" fill={C.muted}>cross-section</text>
      {ray(0, 245, C.wrist, 'top · 190 mm', w)}
      {ray(-45, 245, C.wrist, 'oblique −45°', w)}
      {ray(45, 245, C.wrist, 'oblique +45°', w)}
      {ray(180, 215, C.web, 'under · tool at the lens', b)}
    </svg>;
  },
});

/* ---------- workcell map: top-down, world mm (x forward = up, y left = left) ---------- */
type MapProps = { view?: 'poses' | 'obstacles' | 'all'; highlight?: string[]; width?: number; height?: number };
const MX = (y: number) => 300 - y * 0.5;        // world y -> svg x
const MY = (x: number) => 400 - x * 0.5;        // world x -> svg y
export const Workcell = defineBlock({
  kind: 'workcell',
  size: ({ width = 640, height = 600 }: MapProps) => ({ width, height }),
  render: ({ view: layer = 'all', highlight }: MapProps) => {
    const hl = (k: string) => !highlight || highlight.includes(k);
    const box = (k: string, x0: number, x1: number, y0: number, y1: number, fill: string, stroke: string, label?: string, dash?: string) =>
      <g key={k} opacity={hl(k) ? 1 : 0.22}>
        <rect x={MX(y1)} y={MY(x1)} width={(y1 - y0) * 0.5} height={(x1 - x0) * 0.5} fill={fill} stroke={stroke} strokeWidth="1.5" strokeDasharray={dash} rx="3" />
        {label && <text x={MX(y1) + 8} y={MY(x0) - 8} fontSize="12" fill={stroke} fontWeight="700" letterSpacing="0.06em">{label}</text>}
      </g>;
    const pt = (k: string, x: number, y: number, color: string, label: string, dx = 12, dy = 4, anchor: 'start' | 'end' = 'start') =>
      <g key={k} opacity={hl(k) ? 1 : 0.22}>
        <circle cx={MX(y)} cy={MY(x)} r="7" fill={color} stroke="#fff" strokeWidth="2" />
        <text x={MX(y) + dx} y={MY(x) + dy} fontSize="14" fill={color} fontWeight="600" textAnchor={anchor} stroke="#fbfaf7" strokeWidth="4" paintOrder="stroke">{label}</text>
      </g>;
    const obs = layer !== 'poses', poses = layer !== 'obstacles';
    return <svg viewBox="0 0 600 640" width="100%" height="100%" role="img" aria-label="Top-down map of the workcell with measured poses and obstacles">
      <rect x="0" y="0" width="600" height="640" fill="#fbfaf7" rx="10" />
      {[...Array(13)].map((_, i) => <line key={`g${i}`} x1={i * 50} y1="0" x2={i * 50} y2="640" stroke="#efece5" />)}
      {[...Array(13)].map((_, i) => <line key={`h${i}`} x1="0" y1={i * 50 + 20} x2="600" y2={i * 50 + 20} stroke="#efece5" />)}
      {/* walls */}
      {obs && <g opacity={hl('walls') ? 1 : 0.22}><rect x="0" y={MY(790)} width="600" height="0" /><line x1="0" y1={MY(690)} x2="600" y2={MY(690)} stroke={C.ink2} strokeWidth="6" /><text x="10" y={MY(690) - 8} fontSize="13" fill={C.ink2}>front wall</text>
        <line x1={MX(-450)} y1="0" x2={MX(-450)} y2="640" stroke={C.ink2} strokeWidth="6" /><text x={MX(-450) - 8} y="200" fontSize="13" fill={C.ink2} textAnchor="end" transform={`rotate(-90 ${MX(-450) - 8} 200)`}>side wall</text></g>}
      {/* pick pad + zone */}
      {box('pad', 109, 454, 168, 531, '#e9dcc6', '#9b7b4a', undefined)}
      {box('zone', 150, 400, 200, 500, 'none', '#9b7b4a', 'pick zone', '5 4')}
      {/* bins */}
      {box('bins', 160, 495, -292, -2, obs ? '#f3e7e4' : '#faf6f4', '#8c5148')}
      {box('reject', 170, 315, -285, -10, 'none', C.bad, 'REJECT')}
      {box('good', 315, 485, -285, -10, 'none', C.good, 'GOOD')}
      {obs && box('tripod', -200, -100, -275, -175, '#e8e6f3', C.model, 'tripod')}
      {obs && box('lamp', -225 - 175, -225 + 175, -470, -360, '#e8e6f3', C.model, 'lamp')}
      <text x="12" y="628" fontSize="12" fill={C.muted}>top-down · grid 100 mm · ↑ away from the base</text>
      {/* base */}
      <circle cx={MX(0)} cy={MY(0)} r="34" fill="#fff" stroke={C.ink2} strokeWidth="2" />
      <text x={MX(0)} y={MY(0) + 5} textAnchor="middle" fontSize="13" fill={C.ink2} fontWeight="600">xArm</text>
      {/* webcam + optical axis */}
      <g opacity={hl('webcam') ? 1 : 0.22}>
        <line x1={MX(-206)} y1={MY(-101)} x2={MX(-206 + 0.123 * 420)} y2={MY(-101 + 0.982 * 420)} stroke={C.web} strokeWidth="2" strokeDasharray="6 5" />
        <rect x={MX(-206) - 11} y={MY(-101) - 8} width="22" height="16" rx="3" fill={C.web} />
        <text x={MX(-206) - 16} y={MY(-101) + 5} fontSize="14" fill={C.web} fontWeight="600" textAnchor="end">webcam</text>
      </g>
      {poses && pt('watch', 200, 310, C.wrist, 'watch', 0, 24, 'start')}
      {poses && pt('look', 363, 248, C.wrist, 'look', 12, 4)}
      {poses && pt('oblique', 307, 189, C.wrist, '+45°', 12, 5)}
      {poses && pt('oblique', 189, 537, C.wrist, 'oblique −45°', -4, -14)}
      {poses && pt('checkpoint', 285, -150, C.web, 'checkpoint', -12, 5, 'end')}
      {poses && pt('gooddrop', 400, -147, C.good, 'good drop', -12, 5, 'end')}
    </svg>;
  },
});

/* ---------- decision flow over the seven captures ---------- */
type FlowProps = { flaggedAt?: number; width?: number; height?: number };
const VIEWS: [string, 'wrist' | 'web'][] = [['Top', 'wrist'], ['Oblique +45°', 'wrist'], ['Oblique −45°', 'wrist'], ['Under', 'web'], ['End A', 'web'], ['End B', 'web']];
export const Flow = defineBlock({
  kind: 'flow',
  size: ({ width = 1300, height = 330 }: FlowProps) => ({ width, height }),
  render: ({ flaggedAt }: FlowProps) => {
    const done = flaggedAt ?? VIEWS.length;
    return <div className="flow">
      <div className="flow-row">
        {VIEWS.flatMap(([v, cam], i) => {
          const state = i < done ? 'pass' : i === flaggedAt ? 'flag' : 'skip';
          const col = cam === 'wrist' ? C.wrist : C.web;
          const card = <div key={v} className={`flow-view ${state}`}>
            
            <div className="flow-cam mono" style={{ color: col }}>{cam === 'wrist' ? 'WRIST' : 'WEBCAM'}</div>
            <div className="flow-name">{v}</div>
            <div className="flow-state">{state === 'pass' ? '✓ below threshold' : state === 'flag' ? '✕ anomalous' : 'not needed'}</div>
          </div>;
          return i === 3 ? [<div key="sep" className="flow-sep"><span>pick &amp; carry</span></div>, card] : [card];
        })}
      </div>
      <div className={`flow-out ${flaggedAt === undefined ? 'good' : 'bad'}`}>
        {flaggedAt === undefined
          ? <><b>GOOD</b> every view scored, all below threshold, no known defect → drop in the good bin</>
          : <><b>REJECT</b> at {VIEWS[flaggedAt][0]}: stop inspecting, release over the reject bin. Remaining views skipped.</>}
      </div>
    </div>;
  },
});

/* ---------- calibration timeline ---------- */
export type Phase = { n: string; title: string; when: string; how: string; result: string };
type TimelineProps = { phases: Phase[]; active?: number; width?: number; height?: number };
export const Timeline = defineBlock({
  kind: 'timeline',
  size: ({ width = 1320, height = 420 }: TimelineProps) => ({ width, height }),
  render: ({ phases, active }: TimelineProps) => (
    <div className="timeline" style={{ gridTemplateColumns: `repeat(${phases.length}, 1fr)` }}>
      {phases.map((p, i) => <div key={p.n} className="phase" style={{ opacity: active === undefined || active === i ? 1 : 0.3 }}>
        <div className="phase-dot"><span className="mono">{p.n}</span></div>
        <div className="phase-when mono">{p.when}</div>
        <div className="phase-title">{p.title}</div>
        <div className="phase-how">{p.how}</div>
        <div className="phase-result mono">{p.result}</div>
      </div>)}
    </div>
  ),
});

/* ---------- key/value table ---------- */
type RecordProps = { lines: { key: string; value: string; highlight?: boolean }[]; width?: number; height?: number; title?: string };
export const Record = defineBlock({
  kind: 'record', size: ({ width = 920, height = 390 }: RecordProps) => ({ width, height }),
  render: ({ lines, title }: RecordProps) => <div className="record">
    {title && <div className="record-title mono">{title}</div>}
    {lines.map(line => <div key={line.key} className="mono"><span>{line.key}</span><strong style={{ color: line.highlight ? C.bad : undefined }}>{line.value}</strong></div>)}
  </div>,
});

/* ---------- pose table ---------- */
type PoseRow = { name: string; how: string; value: string; kind: 'measured' | 'solved' | 'swept' };
type PosesProps = { rows: PoseRow[]; width?: number; height?: number; active?: string[] };
export const Poses = defineBlock({
  kind: 'poses', size: ({ width = 640, height = 560 }: PosesProps) => ({ width, height }),
  render: ({ rows, active }: PosesProps) => <div className="poses">
    {rows.map(r => <div key={r.name} className="pose-row" style={{ opacity: !active || active.includes(r.name) ? 1 : 0.3 }}>
      <div className="pose-head"><b>{r.name}</b><span className={`pose-kind ${r.kind}`}>{r.kind}</span></div>
      <div className="pose-how">{r.how}</div>
      <div className="pose-val mono">{r.value}</div>
    </div>)}
  </div>,
});

/* ---------- before -> after rows ---------- */
type LessonsProps = { rows: [string, string, string][]; width?: number; height?: number };
export const Lessons = defineBlock({
  kind: 'lessons', size: ({ width = 1300, height = 480 }: LessonsProps) => ({ width, height }),
  render: ({ rows }: LessonsProps) => <div className="lessons">
    <div className="lesson lesson-head mono"><span>WHAT WE SAW</span><span /><span>WHAT WE CHANGED</span><span>EVIDENCE</span></div>
    {rows.map(([a, b, c]) => <div className="lesson" key={a}><span>{a}</span><span className="arrow">→</span><span>{b}</span><span className="mono">{c}</span></div>)}
  </div>,
});

/* ---------- meter ---------- */
type MeterProps = { score: number; threshold: number; width?: number; height?: number; label?: string };
export const Meter = defineBlock({
  kind: 'meter', size: ({ width = 490, height = 140 }: MeterProps) => ({ width, height }),
  render: ({ score, threshold, label }: MeterProps) => {
    const ratio = score / threshold;
    const col = ratio > 1 ? C.bad : C.good;
    return <div className="meter">
      <div className="meter-heading"><span>{label || 'Anomaly score'}</span><span className="mono" style={{ color: col }}>{score.toFixed(2)}</span></div>
      <div className="meter-track"><div style={{ width: `${Math.min(ratio / 1.5, 1) * 100}%`, background: col }} /><i style={{ left: `${100 / 1.5}%` }} /></div>
      <div className="meter-axis"><span>0</span><span>threshold {threshold.toFixed(2)}</span></div>
    </div>;
  },
});

/* ---------- small helper for model pipeline chips ---------- */
type ChipProps = { label: string; sub?: string; color?: string; width?: number; height?: number };
export const Chip = defineBlock({
  kind: 'chip', size: ({ width = 230, height = 120 }: ChipProps) => ({ width, height }),
  render: ({ label, sub, color = C.model }: ChipProps) => <div className="chip" style={{ borderColor: tint(color, '55'), background: tint(color, '0d') }}>
    <div style={{ color, fontWeight: 600, fontSize: 22 }}>{label}</div>{sub && <div className="chip-sub">{sub}</div>}
  </div>,
});

/* ---------- horizontal bars: measured milliseconds per device ---------- */
export type BarGroup = { title: string; note: string; max: number; rows: { label: string; value: number | null; text: string; pick?: boolean }[] };
type BarsProps = { groups: BarGroup[]; width?: number; height?: number };
export const Bars = defineBlock({
  kind: 'bars', size: ({ width = 1300, height = 280 }: BarsProps) => ({ width, height }),
  render: ({ groups }: BarsProps) => <div className="bars">
    {groups.map(gr => <div key={gr.title} className="bars-group">
      <div className="bars-title">{gr.title}</div>
      <div className="bars-note">{gr.note}</div>
      {gr.rows.map(r => <div key={r.label} className="bars-row">
        <span className="bars-label mono">{r.label}</span>
        <span className="bars-track">{r.value !== null && <i style={{ width: `${Math.min(1, r.value / gr.max) * 100}%`, background: r.pick ? C.good : '#b9bdc2' }} />}</span>
        <span className="bars-value mono" style={{ color: r.pick ? C.good : r.value === null ? C.bad : C.ink }}>{r.text}</span>
      </div>)}
    </div>)}
  </div>,
});

export type { ReactNode };
