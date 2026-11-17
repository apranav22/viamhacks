// [claude-code/claude-fable-5-2 · op Ali (git: Ali) · Alis-MacBook-Air.local · ali/judges-presentation · 2026-11-14]
// Judges deck, ordered by the rubric for the design explanation (docs/CONTEXT.md): what it does, why each choice,
// what failed, what we'd change. 13 main steps (~5 min) + a backup chapter for questions.
// Sources: config/*.json, vh/coverage.py, vh/kinematics.py, sort.py, docs/AGENT_LOG.md, docs/DAY1_RECAP.md,
// docs/THRESHOLD_FINDINGS.md, docs/INTEL.md, docs/OVERNIGHT_FINDINGS_20261114.md (ali/overnight-analysis),
// aayush/dinov2-eval agent log (backbone, type classifier, latency), src/evidence.json (day-1 top-view replay).
// Day-2 numbers come from src/today.json (presentation/set_row.py); nothing there is invented.
import { deck, slide, Wire, type Shot } from '../vendor/deck/index.ts';
import { Text, Head, Photo, Rail, Card, Stat, Ring, Workcell, Flow, Timeline, Record, Poses, Lessons, Meter, Chip, Bars, C, type Stage, type Phase, type BarGroup } from './blocks.tsx';
import evidence from './evidence.json';
import todayRaw from './today.json';
import type { ReactNode } from 'react';

type Eval = { good_passed: number; good_total: number; defects_flagged: number; defects_total: number; note?: string };
type Row = { item: number; t_seen?: string; t_first_motion?: string; latency_ms?: number; decision: string; reason?: string; decided_at_view?: string | null; confidence?: number | null; t_released?: string; _source?: string };
const today = todayRaw as unknown as { device: string | null; eval: Eval | null; row: Row | null };

export const home = { center: { x: 720, y: 405 }, scale: 1 };
const day1 = evidence.live.decision;
const marker = evidence.examples.marker;
const g = evidence.groups;
const defects = g.tape.total + g.marker.total + g.other.total;
const flagged = g.tape.flagged + g.marker.flagged + g.other.flagged;
const IMAGES = 'Hex bolt · wrist views runs/20261114_103009_collect/item_002 · webcam views runs/20261114_104514_collect/item_001';

const frame = (eyebrow: string, title: string, lede: string | undefined, accent: string, content: ReactNode, source = ''): Shot => ({
  camera: home, scene: <>
    <Head id="head" eyebrow={eyebrow} title={title} lede={lede} accent={accent} width={1300} height={lede ? 190 : 110} at={{ x: 720, y: lede ? 140 : 105 }} delay={0} />
    {content}
    <Text id="source" text={source} width={1300} height={30} size={13} color={C.muted} at={{ x: 720, y: 752 }} delay={0.2} />
  </>,
});

const STAGES: Stage[] = [
  { key: 'watch', label: 'Watch', sub: 'Wrist camera over the pad waits until a part is placed and the hand has left.', cam: 'wrist' },
  { key: 'look', label: 'Look', sub: 'Top view plus two oblique views at ±45°: the upper ⅔ of the part.', cam: 'wrist', scored: true },
  { key: 'pick', label: 'Pick', sub: 'Grip at the middle of its length, jaws across; lift straight up.' },
  { key: 'present', label: 'Present', sub: 'At the webcam: the underside, then both end faces.', cam: 'web', scored: true },
  { key: 'decide', label: 'Decide & drop', sub: 'Reject at the first anomalous view; good only if every view is clear.' },
  { key: 'log', label: 'Log', sub: 'One row per item: timestamps, latency, every view’s score, the reason.' },
];

/* ================================================================== 1 · WHAT IT DOES */
const what = slide({ id: 'what', title: 'What it does', steps: {
  title: '[0:00–0:10] You just watched it run. In one sentence: the cell looks at every surface of a fastener, top, sides, underside and both ends, scores each view for anomalies, and sorts the part. These four images are real captures from this morning.',
  cycle: '[0:10–0:30] The cycle. Watch until a part is placed and the hand is gone. Look: three wrist views. Pick at mid-length. Present three more views to the fixed webcam. Decide: the first anomalous view rejects. Log one row per item. Six captures, each scored by its own model in a few milliseconds.',
  coverage: '[0:30–0:50] Why six views. Lying on the pad, only the upper two-thirds of a part is visible, so the wrist camera takes that from three angles. The underside and the two end faces only exist for a camera once the part is in the gripper, so the webcam takes those. Tape can face the table; yesterday’s single top view could not see it.',
} }, step => {
  if (step.id === 'title') return { camera: home, scene: <>
    <Text id="eyebrow" text="VIAM × INTEL · EDGE OF INTELLIGENCE · TRACK 3" size={15} weight={600} tracking={2.4} color={C.wrist} width={640} height={30} at={{ x: 420, y: 230 }} delay={0} />
    <Text id="title" text={'Spot it,\nsort it.'} size={104} weight={700} tracking={-3} lh={0.98} width={640} height={230} at={{ x: 420, y: 370 }} delay={0.05} />
    <Text id="subtitle" text="A robot cell that inspects every surface of a fastener — top, sides, underside and both ends — and sorts it in a single pass." size={25} color={C.ink2} lh={1.4} width={640} height={110} at={{ x: 420, y: 550 }} delay={0.12} />
    <Text id="kit" text="xArm 850 · RealSense wrist camera · 1080p webcam · PatchCore on OpenVINO" size={15} color={C.muted} width={640} height={30} at={{ x: 420, y: 650 }} delay={0.2} />
    <Photo id="p-top" image="judges-cov-top.jpg" alt="Wrist camera top view of a hex bolt on the cardboard pad" width={265} height={265} tag="wrist · top" tagColor={C.wrist} at={{ x: 950, y: 270 }} delay={0.1} />
    <Photo id="p-obl" image="judges-cov-obl-p.jpg" alt="Wrist camera oblique view of the bolt" width={265} height={265} tag="wrist · +45°" tagColor={C.wrist} at={{ x: 1225, y: 270 }} delay={0.16} />
    <Photo id="p-under" image="judges-cov-under.jpg" alt="Webcam view of the bolt held with the tool pointing at the lens" width={265} height={265} tag="webcam · under" tagColor={C.web} at={{ x: 950, y: 545 }} delay={0.22} />
    <Photo id="p-end" image="judges-cov-end_a.jpg" alt="Webcam end-on view of the bolt" width={265} height={265} tag="webcam · end" tagColor={C.web} at={{ x: 1225, y: 545 }} delay={0.28} />
  </> };
  if (step.id === 'cycle') return frame('What it does', 'Look from above, then present the underside', undefined, C.wrist, <>
    <Rail id="rail" stages={STAGES} width={1320} height={230} at={{ x: 720, y: 330 }} delay={0.05} />
    <Stat id="s-views" value="6" label="captures per part" note="3 wrist on the pad · 3 webcam in the gripper" accent={C.ink} width={340} height={170} at={{ x: 270, y: 560 }} delay={0.15} />
    <Stat id="s-scored" value="6 / 6" label="captures scored for anomalies" note="one model per part type × view; a blue-tape colour rule alongside" accent={C.model} width={380} height={170} at={{ x: 680, y: 560 }} delay={0.2} />
    <Stat id="s-ms" value="6.3 ms" label={`median inference per view${today.device ? ` · ${today.device}` : ''}`} note="station CPU, five-view ResNet-18 bundle (docs/INTEL.md)" accent={C.ink} width={400} height={170} at={{ x: 1120, y: 560 }} delay={0.25} />
  </>, 'sort.py --views coverage · vh/coverage.py');
  return frame('What it does · coverage', 'Six views, split by what each camera can see', 'On the pad only what faces up is visible. The underside and both ends appear once the part is in the gripper.', C.wrist, <>
    <Ring id="ring" width={400} height={400} at={{ x: 250, y: 490 }} delay={0.05} />
    <Photo id="v-m" image="judges-cov-obl-m.jpg" alt="Oblique −45 degree wrist view" width={290} height={218} tag="wrist · oblique −45°" tagColor={C.wrist} at={{ x: 625, y: 345 }} delay={0.08} />
    <Photo id="v-top" image="judges-cov-top.jpg" alt="Top wrist view" width={290} height={218} tag="wrist · top · 190 mm" tagColor={C.wrist} at={{ x: 930, y: 345 }} delay={0.12} />
    <Photo id="v-p" image="judges-cov-obl-p.jpg" alt="Oblique +45 degree wrist view" width={290} height={218} tag="wrist · oblique +45°" tagColor={C.wrist} at={{ x: 1235, y: 345 }} delay={0.16} />
    <Photo id="v-under" image="judges-cov-under.jpg" alt="Webcam underside view: tool pointing at the lens" width={290} height={250} tag="webcam · under" tagColor={C.web} at={{ x: 625, y: 600 }} delay={0.2} />
    <Photo id="v-a" image="judges-cov-end_a.jpg" alt="Webcam end A view" width={290} height={250} tag="webcam · end A" tagColor={C.web} at={{ x: 930, y: 600 }} delay={0.24} />
    <Photo id="v-b" image="judges-cov-end_b.jpg" alt="Webcam end B view" width={290} height={250} tag="webcam · end B" tagColor={C.web} at={{ x: 1235, y: 600 }} delay={0.28} />
  </>, IMAGES + ' · diagram is a schematic');
});

/* ================================================================== 2 · WHY EACH CHOICE */
const DEVICE: BarGroup[] = [
  { title: 'Our per-view banks', note: 'ResNet-18 PatchCore, batch 1, p50 per view on armfarm04b', max: 10, rows: [
    { label: 'CPU', value: 6.3, text: '6.3 ms', pick: true }, { label: 'NPU', value: 7.7, text: '7.7 ms' }, { label: 'GPU', value: 8.5, text: '8.5 ms' }] },
  { title: 'Event reference PatchCore', note: '256 px, the organisers’ baseline model, same station', max: 160, rows: [
    { label: 'GPU', value: 27, text: '23–31 ms', pick: true }, { label: 'CPU', value: 76, text: '75–77 ms' }, { label: 'NPU', value: 158, text: '158 ms / no compile' }] },
];
const why = slide({ id: 'why', title: 'Why each choice', steps: {
  model: '[0:50–1:20] Choice one: an anomaly model that only ever sees good parts, because the judged set includes a defect type we have never seen. Three measurements behind it. A blue-tape colour rule catches 22 of our 28 saved defects, all the blue ones; the other six are only caught by the anomaly model, and it caught all six. We compared backbones: ResNet-18 flagged 12 of 28 with no tuned margin against 6 for DINOv2-small, at a sixth of the CPU time. And one bank per part type and view, with the type fixed before scoring: letting the best-fitting bank score a part sent two taped parts to the good bin yesterday.',
  decide: '[1:20–1:35] Choice two: decide after every capture. The first anomalous view ends the inspection; here the underside flags, the arm is already over the reject bin, and it releases there. Good requires every view to be scored and clear. A missing or invalid score never counts as good: it rejects as uncertain.',
  device: '[1:35–2:00] Choice three: device placement, measured, not assumed. For the organisers’ reference PatchCore the GPU wins clearly, 23 to 31 milliseconds against 75 on CPU, and the NPU is slowest or fails to compile. Our per-view banks are much smaller, and at batch one the GPU’s overhead costs more than it saves: CPU 6.3, NPU 7.7, GPU 8.5. So inference runs on the CPU, the Intel GPU does feature extraction when we train, and every model is compiled and warmed before the arm moves, with no silent device fallback. SAY which device today’s run used if it differs.',
  motion: '[2:00–2:25] Choice four: motion. Viam’s planner took four to seven seconds on our long legs at bring-up and sometimes wrapped joints, so every move between known poses is a direct joint move. That means we own collision checking: forward kinematics from the URDF the arm reports, the arm, gripper and held part as spheres, sixty samples along the joint path against seven measured boxes, about ten milliseconds. Speed is set per move so the tool stays under 0.9 metres per second, 0.8 with a part, and the arm settles 0.35 seconds before each capture. Descend and lift are straight-line moves.',
  measured: '[2:25–2:50] Choice five: nothing is tuned by eye. Fixed poses are measured on the arm, part-dependent poses are solved from those measurements with IK, and each calibration is a measurement: fingertip touch for heights because depth was ±7 millimetres, eighteen fingertip positions to calibrate the webcam, wrist depth for the obstacles. Team rule: a constant changes only with a new measurement, and its comment says when, how and who. Backup slides have the detail.',
  latency: '[2:50–3:10] Latency and recovery are choices too. With no hand in view, first motion comes about 385 milliseconds after the part appears: a 0.3 second stillness check plus one frame. If a hand placed it, we wait 0.8 seconds after the hand leaves; we kept that on purpose. The loop runs on the station because each laptop RPC costs 85 to 230 milliseconds. Recovery: a moved part is re-located, a missed grasp retries with the jaws turned, a dropped part is logged as dropped, and a blocked view is skipped rather than forced.',
} }, step => {
  if (step.id === 'model') return frame('Why · detection', 'Learn what good looks like; flag anything that isn’t', 'The judged set includes a defect type we have never seen, so the model is built from good parts only.', C.model, <>
    <Chip id="m1" label="Part crop" sub="from the view’s geometry" color={C.ink2} width={260} height={110} at={{ x: 220, y: 320 }} delay={0.05} />
    <Chip id="m2" label="Patch features" sub="frozen ResNet-18" width={260} height={110} at={{ x: 553, y: 320 }} delay={0.1} />
    <Chip id="m3" label="Memory bank" sub="PatchCore, good parts only" width={260} height={110} at={{ x: 886, y: 320 }} delay={0.15} />
    <Chip id="m4" label="Score ÷ threshold" sub="> 1 is anomalous" color={C.bad} width={260} height={110} at={{ x: 1219, y: 320 }} delay={0.2} />
    <Wire from="m1" to="m2" tone="data" /><Wire from="m2" to="m3" tone="data" /><Wire from="m3" to="m4" tone="data" />
    <Card id="k1" kicker="Why not only a colour rule" title="6 / 6 non-blue defects caught by the model" body="A blue-tape rule flags 22 of our 28 saved defects: every blue one. The other 6 it cannot see." accent={C.model} size={21} width={420} height={235} at={{ x: 280, y: 575 }} delay={0.25} />
    <Card id="k2" kicker="Why ResNet-18" title="12 / 28 vs 6 / 28 for DINOv2-S" body="Same crops, leave-one-run-out, untuned margin. 14.8 vs 88.8 ms per crop on CPU." accent={C.model} size={21} width={420} height={235} at={{ x: 720, y: 575 }} delay={0.3} />
    <Card id="k3" kicker="Why one bank per type × view" title="Type fixed before scoring" body="Letting the best-fitting bank score a part sent two taped parts to GOOD on day 1." accent={C.model} size={21} width={420} height={235} at={{ x: 1160, y: 575 }} delay={0.35} />
  </>, 'OVERNIGHT_FINDINGS_20261114.md (colour rule vs model) · exp/backbone_top (aayush/dinov2-eval) · THRESHOLD_FINDINGS.md (173234_sort) · development picks');
  if (step.id === 'decide') return frame('Why · decision', 'Every capture is scored; the first anomaly ends the inspection', 'A missing or invalid score never counts as good: it rejects as uncertain. A blue-tape colour rule runs alongside the model.', C.model, <>
    <Flow id="flow" flaggedAt={3} width={1320} height={260} at={{ x: 720, y: 430 }} delay={0.05} />
    <Text id="flow-good" text="GOOD needs all six views scored and below threshold." size={20} color={C.ink2} width={1320} height={40} at={{ x: 720, y: 585 }} delay={0.2} />
  </>, 'sort.py score_oblique() / inspect() · vh/anomaly.py reject_reason()');
  if (step.id === 'device') return frame('Why · device placement', 'We measured: for our model, the CPU wins', 'The reference model is faster on the GPU. Our per-view banks are small enough that, at batch 1, GPU overhead costs more than it saves.', C.good, <>
    <Bars id="bars" groups={DEVICE} width={1300} height={250} at={{ x: 720, y: 395 }} delay={0.05} />
    <Card id="d1" kicker="Inference" title="CPU, explicit, no fallback" accent={C.good} size={21} width={420} height={150} at={{ x: 280, y: 640 }} delay={0.15} />
    <Card id="d2" kicker="Training" title="Feature extraction on the Intel GPU (XPU)" accent={C.model} size={21} width={420} height={150} at={{ x: 720, y: 640 }} delay={0.2} />
    <Card id="d3" kicker="Before first motion" title="Every model compiled and warmed" accent={C.ink2} size={21} width={420} height={150} at={{ x: 1160, y: 640 }} delay={0.25} />
  </>, 'docs/INTEL.md device_report.json (CPU/GPU, 10 images × 10 repeats) · docs/THRESHOLD_FINDINGS.md (NPU) · docs/CONTEXT.md (reference model)');
  if (step.id === 'motion') return frame('Why · motion', 'Known moves are joint moves, each checked before it is sent', 'Viam’s planner took 4–7 s on our long legs and sometimes wrapped joints, so we drive joints directly and own the collision check.', C.ink2, <>
    <Workcell id="map" view="obstacles" width={400} height={427} at={{ x: 265, y: 500 }} delay={0.05} />
    <Card id="mo1" kicker="Collision check" title="≈10 ms per move" body="FK from the arm’s own URDF. Arm, gripper and held part as spheres, 60 samples along the joint path, 7 measured boxes." accent={C.good} size={22} width={430} height={205} at={{ x: 725, y: 395 }} delay={0.1} />
    <Card id="mo2" kicker="If blocked" title="No motion" body="Try the next standoff or a raised waypoint; otherwise skip the view and log why." accent={C.bad} size={22} width={430} height={205} at={{ x: 1175, y: 395 }} delay={0.15} />
    <Card id="mo3" kicker="Speed" title="Set per move" body="Fastest joint speed that keeps the tool under 0.9 m/s, 0.8 m/s with a part. 0.35 s settle before each capture." accent={C.wrist} size={22} width={430} height={205} at={{ x: 725, y: 620 }} delay={0.2} />
    <Card id="mo4" kicker="Near the table" title="Straight down, straight up" body="Descend and lift use Viam motion with a linear constraint." accent={C.ink2} size={22} width={430} height={205} at={{ x: 1175, y: 620 }} delay={0.25} />
  </>, 'docs/AGENT_LOG.md 13 Nov 14:55 (planner) · vh/kinematics.py check_path() / safe_joint_speed() · sort.py SETTLE_S · config/obstacles.json');
  if (step.id === 'measured') return frame('Why · poses and calibration', 'Every pose and constant is a measurement', 'Team rule: a constant changes only with a new measurement, and its config comment records the date, the method and who measured it.', C.wrist, <>
    <Workcell id="map" view="all" width={400} height={427} at={{ x: 265, y: 500 }} delay={0.05} />
    <Poses id="pose-col" width={440} height={440} at={{ x: 715, y: 500 }} delay={0.1} rows={[
      { name: 'Watch', kind: 'measured', how: 'Recorded joints; sees the whole pad.', value: 'TCP (200, 310, 330) · 0.77 mm/px' },
      { name: 'Look', kind: 'swept', how: 'Lens height swept 260 / 220 / 190 mm.', value: 'lens 190 mm · 0.21 mm/px' },
      { name: 'Obliques, webcam views', kind: 'solved', how: 'IK from the part pose and the checkpoint.', value: '225 / 240 oblique targets clear' },
      { name: 'Checkpoint, bins', kind: 'measured', how: 'Over reject, 400 mm from the lens.', value: 'TCP (285, −150, 260) · bins re-measured today' },
    ]} />
    <Poses id="cal-col" width={440} height={440} at={{ x: 1165, y: 500 }} delay={0.18} rows={[
      { name: 'Heights by touch', kind: 'measured', how: 'Closed fingertips on table and pad; depth was ±7 mm.', value: 'table −1.3 · pad 6.5 · tips 20.5 mm past TCP' },
      { name: 'Webcam projection', kind: 'measured', how: 'Fingertips found at 18 arm positions.', value: 'mean reprojection 8 px at 1080p' },
      { name: 'Obstacles', kind: 'measured', how: 'Tripod, lamp and bins with wrist depth.', value: '7 boxes · config/obstacles.json' },
      { name: 'Image recipe', kind: 'measured', how: 'Exposure locked, LED added, set every run.', value: '1280×720 · 10 ms exposure' },
    ]} />
  </>, 'config/checkpoint.json · config/poses.json · config/obstacles.json · AGENTS.md §6 · oblique reachability: aayush/dinov2-eval log 11:05');
  return frame('Why · latency and recovery', 'Latency and recovery are choices too', undefined, C.ink2, <>
    <Stat id="la1" value="≈385 ms" label="part appears → first motion, no hand" note="0.3 s stillness check + one frame; the first motion is the move to look" accent={C.ink} width={400} height={180} at={{ x: 270, y: 300 }} delay={0.05} />
    <Stat id="la2" value="+0.8 s" label="if a hand placed it" note="we wait until the hand has left the frame: kept on purpose" accent={C.web} width={400} height={180} at={{ x: 270, y: 490 }} delay={0.1} />
    <Text id="la3" text={'Loop runs on the station:\na laptop adds 85–230 ms per RPC.'} size={18} color={C.ink2} width={400} height={60} at={{ x: 270, y: 660 }} delay={0.15} />
    {([
      ['Part moved before the grasp', 'The close look re-measures it. Gone: back to watching, no grab.'],
      ['Grasp missed', 'Finger position says empty: retry with the jaws turned 90°.'],
      ['Part dropped in transit', 'Grip re-checked at every webcam view; logged as dropped, never sorted.'],
      ['View blocked or score missing', 'Skip the view, never force it. Missing evidence rejects as uncertain.'],
    ] as const).map(([t, b], i) => <Card key={t} id={`re-${i}`} kicker="Recovery" title={t} body={b} accent={C.wrist} size={21} width={400} height={215} at={{ x: 760 + (i % 2) * 420, y: 355 + Math.floor(i / 2) * 235 }} delay={0.1 + 0.05 * i} />)}
  </>, 'aayush/dinov2-eval log 09:55 (latency from saved logs) · sort.py STILL_S / HAND_HOLDOFF_S / pick() / inspect() · docs/CONTEXT.md (RPC timings)');
});

/* ================================================================== 3 · WHAT FAILED */
const failed = slide({ id: 'failed', title: 'What failed', steps: {
  record: '[3:10–3:35] What failed. Day one, honestly: across six short live sort runs, 13 of our 16 rejects came from a blue-tape colour rule and only 2 from the anomaly model. Two taped parts went to the good bin. We hit the E-stop twice: an upright bolt touched the gripper on the way down, and repeated misses on a short bolt tore the pad. A rule that only knows blue tape cannot catch a defect it has never seen, so day two went into coverage and the anomaly model.',
  lessons: '[3:35–4:00] Each failure changed the design, and each change has a run behind it. Pick the two most relevant to what the judges just saw; do not read the table.',
} }, step => {
  if (step.id === 'record') return frame('What failed · day 1', 'Day 1: a colour rule did most of the rejecting', 'Six short live sort runs on the station and laptop, 30 items decided.', C.bad, <>
    <Stat id="f1" value="13 / 16" label="rejects came from the blue-tape colour rule" accent={C.bad} width={300} height={170} at={{ x: 220, y: 360 }} delay={0.05} />
    <Stat id="f2" value="2 / 16" label="rejects came from the anomaly model" accent={C.model} width={300} height={170} at={{ x: 555, y: 360 }} delay={0.1} />
    <Stat id="f3" value="2" label="taped parts sent to GOOD" note="wrong bank; no bank for that part" accent={C.bad} width={300} height={170} at={{ x: 890, y: 360 }} delay={0.15} />
    <Stat id="f4" value="2" label="E-stops" note="upright bolt hit the gripper; repeated misses tore the pad" accent={C.bad} width={300} height={170} at={{ x: 1225, y: 360 }} delay={0.2} />
    <Card id="f-why" kicker="Why it mattered" title="The judged set includes a defect type we have never seen. A rule that only knows blue tape cannot catch it." body="So day 2 went into coverage and the anomaly model: six views per part, and a bank for every view." accent={C.ink} size={24} width={1320} height={190} at={{ x: 720, y: 615 }} delay={0.3} />
  </>, 'docs/DAY1_RECAP.md "What the live sort runs showed" · docs/THRESHOLD_FINDINGS.md');
  return frame('What failed · and what it changed', 'Every change came from something we saw on the arm', undefined, C.ink2, <>
    <Lessons id="lessons" width={1320} height={540} at={{ x: 720, y: 460 }} delay={0.05} rows={[
      ['One top view cannot see tape facing the table', 'Six views: upper ⅔ on the pad, underside and ends at the webcam', '20261114_103009_collect'],
      ['Tilting the part ±60° showed its side, not its underside', 'Underside view with the tool pointed at the lens', 'AGENT_LOG 14 Nov 10:50'],
      ['Best-fitting model bank let two taped parts through', 'Fix the part type before scoring', '20261113_173234_sort'],
      ['Planner took 4–7 s per long leg, sometimes wrapped joints', 'Checked joint moves to recorded / solved joints', 'AGENT_LOG 13 Nov 14:55'],
      ['Depth read the pad surface ±7 mm', 'Touch calibration with the closed fingertips', 'pad_touch_20261113_171209'],
      ['An upright bolt hit the gripper on descent (E-stop)', 'Upright grasp off until it is measured safe', 'AGENT_LOG 13 Nov 15:48'],
    ]} />
  </>, 'docs/DAY1_RECAP.md · docs/AGENT_LOG.md · vh/coverage.py');
});

/* ================================================================== 4 · WHAT WE'D CHANGE + CLOSE */
const next = slide({ id: 'next', title: 'What we’d change', steps: {
  change: '[4:00–4:35] What we would change with another day. First, the data: our train, calibration and test picks repeat the same few physical parts, so our numbers are development numbers; we would split by physical part and hold some back untouched. Second, ship the repaired crop we tested offline overnight. Third, choose the part type with the small classifier we built this morning and put a confidence in every log row. Fourth, upright parts and re-acquiring a part taken from the gripper. UPDATE this slide if the classifier or confidence shipped before the run.',
  receipt: '[4:35–5:00] And every item leaves a receipt: when we saw it, when the arm first moved, every view’s score, the decision and why. This is the log you scored us from. Thank you; the dashboard, the logs and the arm are here for questions.',
} }, step => {
  if (step.id === 'change') return frame('What we’d change', 'With another day', undefined, C.wrist, <>
    {([
      ['Data', 'Split by physical part', 'Our train / calibration / test picks repeat the same few parts, so today’s numbers are development numbers. A 5% false-reject budget needs about 19 independent good parts per type.', C.model],
      ['Crop', 'Ship the repaired part crop', 'Offline it lifts top-view detection from 22–24 to 25–26 of 28 defects with no extra false rejects, across three seeds.', C.model],
      ['Routing and log', 'Type by classifier; confidence in every row', 'A ResNet-18 type classifier gets 103 / 112 on held-out runs against 78 / 112 for the size rule. Built this morning; needs validation on the station.', C.wrist],
      ['Handling', 'Upright parts, and parts taken mid-carry', 'Upright grasp is off after the collision. A part removed from the gripper is detected and logged, but not re-acquired.', C.web],
    ] as const).map(([k, t, b, a], i) => <Card key={t} id={`ch-${i}`} kicker={k} title={t} body={b} accent={a} size={24} width={640} height={250} at={{ x: 385 + (i % 2) * 670, y: 320 + Math.floor(i / 2) * 275 }} delay={0.06 * i} />)}
  </>, 'docs/ANOMALY_CALIBRATION.md · docs/OVERNIGHT_FINDINGS_20261114.md · aayush/dinov2-eval log 11:30');
  const row: Row = today.row ?? { ...day1, _source: 'runs/20261113_173234_sort/decisions.jsonl · item 2 (day 1, classic views)' };
  const lines = [
    { key: 'item', value: String(row.item) },
    ...(row.t_seen ? [{ key: 't_seen', value: row.t_seen }] : []),
    ...(row.t_first_motion ? [{ key: 't_first_motion', value: row.t_first_motion }] : []),
    ...(row.latency_ms != null ? [{ key: 'latency_ms', value: row.latency_ms.toLocaleString() }] : []),
    { key: 'decision', value: row.decision.toUpperCase(), highlight: row.decision === 'reject' },
    ...(row.confidence != null ? [{ key: 'confidence', value: String(row.confidence) }] : []),
    ...(row.reason ? [{ key: 'reason', value: row.reason }] : []),
    ...(row.decided_at_view ? [{ key: 'decided_at_view', value: row.decided_at_view }] : []),
    ...(row.t_released ? [{ key: 't_released', value: row.t_released }] : []),
  ];
  return frame('Audit trail', 'Every item leaves a receipt', undefined, C.ink2, <>
    <Record id="receipt" title={row._source ?? 'decisions.jsonl'} width={760} height={430} at={{ x: 450, y: 450 }} delay={0.05} lines={lines} />
    <Card id="recap" kicker="In one pass" title="Spot it, sort it." accent={C.wrist} size={34} body={'Six views per part, every one scored\nEvery move checked against the measured workcell\nEvery pose and constant measured, never guessed\nEvery decision logged with its evidence'} width={500} height={330} at={{ x: 1110, y: 450 }} delay={0.15} />
  </>, today.row ? 'One JSON row per item, written as it happens' : 'Day-1 row shown until today’s run is loaded with presentation/set_row.py');
});

/* ================================================================== BACKUP (for questions) */
const PHASES: Phase[] = [
  { n: '1', title: 'Frames & jaws', when: 'DAY 1 · 13:00', how: 'Checked Viam’s orientation maths against the frame system; tested which way the jaws close.', result: 'agree to 1e-4\njaws close along gripper y' },
  { n: '2', title: 'Contact heights', when: 'DAY 1 · 13:00–17:12', how: 'Touched the table and the pad with closed fingertips. Depth alone was too noisy (±7 mm).', result: 'table z −1.3 mm\ntips 20.5 mm past TCP\npad z 6.5 mm' },
  { n: '3', title: 'Webcam', when: 'DAY 1 · 14:55', how: 'After the webcam moved to a tripod: fingertips at 18 arm poses, projection fit (DLT).', result: 'mean error 8 px\nlens (−101, −206, 347)' },
  { n: '4', title: 'Image recipe', when: 'DAY 1 · 16:00–17:35', how: 'Locked wrist exposure and brightness, swept look heights, added an LED to remove the arm’s shadow.', result: '1280×720 · 10 ms\nlens 190 mm' },
  { n: '5', title: 'Workcell', when: 'DAY 1 14:30 · DAY 2 10:25', how: 'Tripod, lamp and bins measured with wrist depth; bins re-measured after they moved.', result: '7 obstacle boxes\nbins updated in config' },
  { n: '6', title: 'Coverage poses', when: 'DAY 2 · 10:18–11:45', how: 'Empty-gripper survey of 9 webcam poses, oblique reachability, live pilots; tilt ±60° dropped for the underside view.', result: 'under + 2 end-on\n225 / 240 obliques' },
];
const backup = slide({ id: 'backup', title: 'Backup', steps: {
  results: '[backup] Model results. If today’s evaluation is loaded it is shown here; otherwise the day-1 top-view replay: automatic type routing, development picks that repeat physical parts.',
  calibration: '[backup] The six calibration phases in order, each a measurement on the arm.',
  webcam: '[backup] Webcam calibration: 18 closed-gripper positions, fingertips found in each frame, 3×4 projection solved. Mean reprojection 8 px, about 1.3 mm at the checkpoint. It places the crop around the part in every webcam view.',
  grasp: '[backup] The six grasp and hold checks.',
} }, step => {
  if (step.id === 'results') {
    const e = today.eval;
    return frame('Backup · model results', e ? 'Results on today’s coverage banks' : 'Day-1 results: top view only', e ? (e.note ?? 'Held-out picks from today’s collection.') : 'Offline replay of saved captures with automatic type routing. Development data: the same physical parts were picked many times.', C.model, <>
      <Photo id="ev-img" image={marker.image} alt="Marker-labelled hex bolt from a saved capture" width={540} height={240} fit="contain" tag="marker defect · day 1" tagColor={C.bad} at={{ x: 340, y: 400 }} delay={0.05} />
      <Meter id="ev-meter" score={marker.routed.score} threshold={marker.routed.threshold} label="Anomaly score · flagged" width={540} at={{ x: 340, y: 610 }} delay={0.12} />
      <Stat id="ev-def" value={e ? `${e.defects_flagged} / ${e.defects_total}` : `${flagged} / ${defects}`} label="labelled defects flagged" accent={C.bad} width={280} height={170} size={56} at={{ x: 830, y: 420 }} delay={0.15} />
      <Stat id="ev-good" value={e ? `${e.good_passed} / ${e.good_total}` : `${g.good.clear} / ${g.good.total}`} label="good parts passed" accent={C.good} width={280} height={170} size={56} at={{ x: 1150, y: 420 }} delay={0.2} />
    </>, e ? 'presentation/src/today.json' : `runs/_analysis/curated-candidate-top-replay.json · marker example ${marker.pick} (collected without a model; scored later)`);
  }
  if (step.id === 'calibration') return frame('Backup · calibration', 'Six phases, each one a measurement on the arm', undefined, C.wrist, <>
    <Timeline id="tl" phases={PHASES} width={1320} height={400} at={{ x: 720, y: 440 }} delay={0.05} />
  </>, 'docs/AGENT_LOG.md · config/poses.json (_tcp_to_tip, _surface_z) · config/checkpoint.json (how_measured) · config/obstacles.json');
  if (step.id === 'webcam') return frame('Backup · webcam calibration', 'The robot measures its own camera', 'With the gripper closed, the arm visited 18 positions. We found the fingertips (red dot) in each frame and solved the projection from world millimetres to pixels.', C.web, <>
    <Photo id="cal-grid" image="judges-cov-calib-grid.jpg" alt="Eighteen webcam frames of the closed gripper at different calibration positions" width={1180} height={332} fit="contain" at={{ x: 720, y: 405 }} delay={0.05} />
    <Stat id="cal-n" value="18" label="fingertip positions" note="x 260/340/420 · y −220/−130/−40 · z 230/320 mm" width={340} height={120} size={42} at={{ x: 230, y: 655 }} delay={0.12} />
    <Stat id="cal-e" value="8 px" label="mean reprojection error" note="max 49 px · 1920×1080 · no distortion model" width={340} height={120} size={42} at={{ x: 590, y: 655 }} delay={0.16} />
    <Stat id="cal-s" value="≈6 px/mm" label="at the checkpoint" note="a 16 mm shank is ~95 px" width={340} height={120} size={42} at={{ x: 950, y: 655 }} delay={0.2} />
    <Stat id="cal-r" value="2×" label="calibrated" note="re-done after the webcam moved to a tripod" width={300} height={120} size={42} at={{ x: 1240, y: 655 }} delay={0.24} />
  </>, 'config/checkpoint.json webcam.how_measured · site/img/webcam_calib_grid.jpg');
  return frame('Backup · grasp', 'Grasping and holding, checked at every step', undefined, C.ink2, <>
    {([
      ['Grip mid-length', 'Grasp the midpoint of the part’s length, not the blob centroid, so both halves stay visible at the webcam. 0–7 mm shift over 26 parts.', C.wrist],
      ['Jaws across the part', 'Wrist angle computed from the part’s yaw; closed fingertips 2 mm above the surface (20.5 mm past the TCP).', C.wrist],
      ['Re-look first', 'If the part is no longer where we saw it, go back to watching instead of grabbing at empty space.', C.wrist],
      ['Confirm the grip', 'Read finger position once it stops changing; near-closed means empty. Sort mode retries with the jaws turned 90°.', C.web],
      ['Watch for drops', 'Finger position re-read at every webcam view. A dropped part is logged as dropped, never sorted.', C.web],
      ['Release for real', 'gripper.open() can return before the fingers open, so we wait until they read open before moving.', C.web],
    ] as const).map(([t, b, a], i) => <Card key={t} id={`gr-${i}`} title={t} body={b} accent={a} size={22} width={420} height={210} at={{ x: 270 + (i % 3) * 450, y: 330 + Math.floor(i / 3) * 235 }} delay={0.04 * i} />)}
  </>, 'sort.py pick() / inspect() / release() · config/poses.json grasp');
});

export default deck({ title: 'Spot it, sort it · Viam × Intel', viewers: [], home }, [what, why, failed, next, backup]);
