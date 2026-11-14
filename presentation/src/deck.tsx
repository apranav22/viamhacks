// [codex/unknown · op Ali · Mac.mynetworksettings.com · ali/judges-presentation · 2026-11-14]
import { deck, slide, Wire, type Shot } from '../vendor/deck/index.ts';
import { Text, Photo, Node, Meter, Record, Results, teal, red, grey } from './blocks.tsx';
import evidence from './evidence.json';

export const home = { center: { x: 720, y: 405 }, scale: 1 };
const a = evidence.assets;
const live = evidence.live.decision;
const marker = evidence.examples.marker;
const miss = evidence.examples.miss;
const source = 'Recorded run · 20261113_173234_sort / item_002';
const frame = (title: string, label: string, content: React.ReactNode, camera = home): Shot => ({ camera, scene: <>
  <Text id="chapter" text={title} width={1250} height={72} size={44} weight={500} at={{x:720,y:100}} delay={0}/>
  {content}
  <Text id="source" text={label} width={1250} height={40} size={16} color={grey} at={{x:720,y:715}} delay={0.24}/>
</> });

export const chapters = [
  { id: 'inspect', title: 'One fastener, every decision', steps: {
    opening: '[0:00–0:15] We built an inspection loop for fasteners: see the part, pick it, inspect it, and leave an audit trail. This is a real recorded cycle from armfarm04b. The screen is replaying saved evidence; no robot is connected. Track 3 asks for five minutes of design explanation after the judged run. Sources: Viam Overview p6 and reference sheet pp9–10.',
    watch: '[0:15–0:30] Start with this actual taped hex bolt. The wrist-camera watch image establishes what entered the workspace. We gate on a settled scene before attempting the grasp. That gate has also failed: a stale hand reference stalled a later run. Do not claim tested recovery from a judge moving a part.',
    locate: '[0:30–0:50] The arm takes a closer wrist-camera look. This is the saved detector box, not a new inference. The stored target is x=270.1, y=358.0 mm. Depth and the calibrated camera transform ground the grasp in robot coordinates. Measured poses stay fixed; no guessed calibration.',
    hold: '[0:50–1:10] The same item is now visibly held at the webcam. This is the actual front frame from this pick. A second viewpoint makes occlusion and grasp retention visible. Extra views have a cost and can introduce false rejects; more views are not automatically better.',
    evidence: '[1:10–1:30] This live decision was triggered by the known tape rule: top-face tape fraction 12.9%. The top anomaly score was also over its threshold, but the attribution matters: this was a tape-rule reject. The later front anomaly score was below threshold. Keep colour-rule success separate from anomaly detection.',
    decision: '[1:30–1:45] The saved destination decision is REJECT. The alternatives are the good box and an uncertainty path. This display explains the decision, not an independently verified placement. A release timestamp exists; no destination camera confirmation is recorded for this item.',
    receipt: '[1:45–2:00] The log ties item, observation, first motion, decision and release together. This item took 2.672 seconds to first motion, not the model inference time. The original row has no calibrated confidence field. We must address the judged confidence/log contract without relabeling an anomaly ratio as a probability.',
  }},
  { id: 'learn', title: 'Learn normal, expose the misses', steps: {
    normal: '[2:00–2:20] We trained a station-specific PatchCore candidate from good captures: 75 training picks, 34 calibration picks, 34 good test picks across six types. These six thumbnails are real training crops of the long hex bolt. Pick-level splits repeat physical parts, so this does not establish generalization to unseen specimens. Feature extraction ran on Intel XPU; selection and export on CPU. Candidate is not activated.',
    marker: '[2:20–2:40] A separate saved marker-labeled pick, rechecked offline on CPU, is flagged: 22.45 over 20.42. The model-input reconstruction uses part-top-v2. Its original run was COLLECTION with no model loaded. Never describe this as a live rejection or an unseen-defect success. Image SHA256 was verified against the replay row.',
    miss: '[2:40–3:00] Here is a real failure. The taped button screw is routed to a hex-nut bank and scores 18.93 below 22.89, so the model misses it. The reconstructed crop shows the head dominating the representation. Supplying the correct type still misses this pick at ratio 0.926. Routing alone does not fix it; crop quality and calibration both need attention.',
    results: '[3:00–3:25] Automatic-routing replay, top view only: 34 good test picks yield 32 clear and 2 false flags. Of 28 labeled defects, 22 are flagged, 5 are clear misses, and 1 is unknown type. Unknown means uncertain, not a successful anomaly detection. Supplying the labeled type instead gives 23/28 defects flagged and 0/34 good false flags; that is an oracle diagnostic, not automatic performance. Development repeated picks, not an independent specimen test or judge score.',
  }},
  { id: 'deploy', title: 'What the system has to earn', steps: {
    device: '[3:25–3:45] We explicitly choose the inference device. On the saved candidate CPU replay, median inference is 10.18 ms and p95 is 13.02 ms over 169 successful top calls; two unknown-type rows do not run inference. These are saved single-call timings, not an interleaved device benchmark or end-to-end latency. Organizer reference p10 reports GPU 23 ms vs CPU 75 ms for their different baseline, says PatchCore NPU compilation fails, and requires GPU f32 for nonzero anomaly maps. Do not apply those baseline numbers to our candidate. Next: matched CPU/GPU diagnostics on the final deployed bundle.',
    recovery: '[3:45–4:10] Three failures shaped the system. A stale reference blocked the watch gate; revalidate the reference and measure moved-item recovery before judging. A best-fitting wrong-type bank hid defects; the candidate instead routes by size but still has mistakes. Thin parts slipped and caused grasp failures; audit retention and bounded failure handling. These are documented findings and next work, not claims that all recovery is fixed.',
    proof: '[4:10–5:00] End on the evidence: the real taped part, the recorded reject reason, and an attributable decision row. The implementation connects Viam camera/arm/gripper resources to a local station loop, OpenVINO inference, and a saved audit trail. The remaining work is concrete: verify destination execution, fill the judged confidence contract honestly, run matched device diagnostics, and test recovery and unseen physical specimens. Let the judges inspect the image and log. This presentation does not activate models or control the arm.',
  }},
] as const;

const inspection = slide(chapters[0], step => {
  switch(step.id) {
    case 'opening': return frame('Spot it, sort it', 'Viam × Intel · Edge of Intelligence · Track 3 · 14 November 2026', <>
      <Text id="premise" text={'One fastener.\nAn inspectable decision.'} size={53} weight={400} width={650} height={170} at={{x:430,y:345}} delay={0}/>
      <Photo id="subject" image={a.detail} alt="Actual taped hex bolt from the recorded sorting cycle" width={490} height={240} at={{x:1040,y:370}} delay={0.12}/>
      <Text id="opening-note" text="Real captures from armfarm04b" size={22} width={650} at={{x:430,y:505}} color={grey} delay={0.24}/>
    </>);
    case 'watch': return frame('Find the next part',source,<>
      <Photo id="subject" image={a.watch} alt="Saved wrist watch image of the taped fastener on cardboard" width={768} height={432} at={{x:500,y:389}} delay={0}/>
      <Node id="watch" label="Watch" sub="Wait for a settled scene" active at={{x:1120,y:286}} delay={0.12}/>
      <Node id="look" label="Look" sub="Move closer" at={{x:1120,y:463}} delay={0.24}/>
      <Wire from="watch" to="look" />
    </>);
    case 'locate': return frame('Ground the grasp',source,<>
      <Photo id="subject" image={a.top} alt="Saved top frame with the original detection bounding box" box={evidence.live.bbox} width={768} height={432} at={{x:500,y:389}} delay={0}/>
      <Node id="look" label="Look" sub="Saved detection + depth" active at={{x:1120,y:286}} delay={0.12}/>
      <Text id="coordinates" text={`x  ${live.pick_xy[0].toFixed(1)} mm\ny  ${live.pick_xy[1].toFixed(1)} mm\nθ  ${live.yaw.toFixed(1)}°`} mono size={28} width={230} height={154} at={{x:1120,y:463}} delay={0.24}/>
    </>);
    case 'hold': return frame('Make the part visible',source,<>
      <Photo id="subject" image={a.held} alt="Same fastener held in the real gripper, captured by the webcam" width={768} height={432} at={{x:500,y:389}} delay={0}/>
      <Node id="look" label="Held view" sub="Webcam · front" active at={{x:1120,y:286}} delay={0.12}/>
      <Photo id="held-detail" image={a.heldCrop} alt="Saved front-view crop of gripper holding the bolt" width={175} height={220} fit="contain" at={{x:1120,y:490}} delay={0.24}/>
    </>);
    case 'evidence': return frame('Know what triggered the decision',source,<>
      <Photo id="subject" image={a.detail} alt="Close view of the taped bolt used in the actual decision" width={560} height={255} at={{x:410,y:337}} delay={0}/>
      <Text id="tape-number" text={`${(live.top_tape*100).toFixed(1)}%`} size={80} width={510} height={110} at={{x:1050,y:285}} color={red} delay={0.12}/>
      <Text id="tape-label" text="Top-face tape · decision trigger" size={25} width={510} at={{x:1050,y:368}} delay={0.12}/>
      <Meter id="anomaly" score={live.scores.top.score} threshold={live.scores.top.threshold} width={510} at={{x:1050,y:515}} delay={0.24}/>
      <Text id="distinction" text="Two signals, separate attribution" size={25} width={560} height={72} color={grey} at={{x:410,y:540}} delay={0.24}/>
    </>);
    case 'decision': return frame('Choose a destination',source,<>
      <Photo id="subject" image={a.detail} alt="The same recorded taped bolt" width={370} height={175} at={{x:410,y:389}} delay={0}/>
      <Node id="good" label="Good box" width={260} at={{x:1050,y:250}} delay={0.12}/>
      <Node id="reject" label="Reject" sub="Recorded decision" width={260} active tone={red} at={{x:1050,y:415}} delay={0.24}/>
      <Node id="uncertain" label="Uncertain" sub="Missing or unknown evidence" width={260} at={{x:1050,y:580}} delay={0.12}/>
      <Wire from="subject" to="reject" tone="danger" bend={0}/>
      <Text id="execution" text="Release logged; destination not independently verified" size={21} width={750} at={{x:505,y:585}} color={grey} delay={0.36}/>
    </>);
    default: return frame('Leave a receipt',source,<>
      <Record id="receipt" at={{x:720,y:397}} lines={[
        {key:'item',value:'002'}, {key:'t_seen',value:live.t_seen},
        {key:'t_first_motion',value:live.t_first_motion},
        {key:'response latency',value:`${live.latency_ms.toLocaleString()} ms`,highlight:true},
        {key:'decision',value:live.decision.toUpperCase(),highlight:true},
        {key:'reason',value:live.reason}, {key:'t_released',value:live.t_released},
      ]} delay={0}/>
      <Text id="confidence-gap" text="Original row has no calibrated confidence field" size={21} width={920} color={grey} at={{x:720,y:640}} delay={0.24}/>
    </>);
  }
});

const learning = slide(chapters[1], step => {
  if(step.id==='normal') return frame('Learn what normal looks like','Curated candidate · 75 training / 34 calibration / 34 good test picks · six part types',<>
    {evidence.normalImages.map((image,i)=><Photo key={image} id={`normal-${i}`} image={image} alt={`Real normal training crop ${i+1}, long hex bolt`} width={172} height={172} at={{x:220+i*200,y:365}} delay={0.12}/>)}
    <Text id="training" text="Good captures → PatchCore memory banks → OpenVINO" size={30} width={1100} height={72} at={{x:720,y:535}} align="center" delay={0.24}/>
    <Text id="split-warning" text="Pick-level splits repeat physical specimens" size={21} width={1100} color={grey} at={{x:720,y:604}} align="center" delay={0.36}/>
  </>);
  if(step.id==='marker' || step.id==='miss') {
    const ex = step.id==='marker' ? marker : miss;
    const found = step.id==='marker';
    return frame(found ? 'A defect the candidate flags' : 'A defect the candidate misses',`Offline CPU replay · ${ex.pick} · original action: COLLECT`,<>
      <Photo id="example-source" image={ex.image} alt={found ? 'Actual marker-labeled hex-bolt crop' : 'Actual tape-labeled button screw, missed by candidate'} width={540} height={230} at={{x:390,y:306}} delay={0}/>
      <Photo id="model-input" image={ex.modelImage} alt="Reconstructed part-top-v2 model input, not a heatmap" width={260} height={260} fit="contain" at={{x:390,y:568}} delay={0.12}/>
      <Text id="model-caption" text="Model input" size={17} width={210} color={grey} at={{x:650,y:565}} delay={0.12}/>
      <Meter id="example-score" score={ex.routed.score} threshold={ex.routed.threshold} width={510} at={{x:1030,y:330}} delay={0.24}/>
      <Text id="example-verdict" text={found ? 'Flagged' : 'Missed'} size={66} width={510} height={100} color={found ? teal : red} at={{x:1030,y:475}} delay={0.24}/>
      <Text id="routing" text={found ? 'Marker label · long hex-bolt bank' : 'Button screw → hex-nut bank\nCorrect-type diagnostic also misses'} size={23} width={510} height={90} color={grey} at={{x:1030,y:580}} delay={0.36}/>
    </>);
  }
  return frame('Count the misses as well as the flags','Top-view CPU replay · automatic size routing · repeated-pick development set',<>
    <Results id="results" at={{x:720,y:396}} delay={0} rows={Object.entries(evidence.groups).map(([key,value])=>({label:({good:'Good',tape:'Tape',marker:'Marker',other:'Other mark'})[key]!,...value}))}/>
    <Text id="results-note" text="28 defects: 22 flagged · 5 missed · 1 uncertain" size={28} width={1152} at={{x:720,y:641}} delay={0.24}/>
  </>);
});

const deployment = slide(chapters[2], step => {
  if(step.id==='device') return frame('Separate inference from response time','Candidate CPU replay · 169 successful top calls · saved timings, not a device comparison',<>
    <Text id="median" text={`${evidence.timing.median.toFixed(2)} ms`} size={88} width={565} height={120} at={{x:430,y:330}} color={teal} delay={0}/>
    <Text id="median-label" text="Median model inference" size={28} width={565} at={{x:430,y:424}} delay={0.12}/>
    <Text id="p95" text={`p95  ${evidence.timing.p95.toFixed(2)} ms`} size={28} mono width={565} at={{x:430,y:505}} color={grey} delay={0.24}/>
    <Text id="motion-time" text={`${(live.latency_ms/1000).toFixed(3)} s`} size={88} width={565} height={120} at={{x:1060,y:330}} delay={0}/>
    <Text id="motion-label" text="Recorded first-motion latency" size={28} width={565} at={{x:1060,y:424}} delay={0.12}/>
    <Text id="device-why" text="OpenVINO · explicit CPU\nIntel XPU feature extraction" size={26} width={565} height={100} at={{x:1060,y:520}} color={grey} delay={0.24}/>
    <Text id="device-gap" text="Next: matched CPU / GPU diagnostics on the final bundle" size={23} width={1152} at={{x:720,y:640}} delay={0.36}/>
  </>);
  if(step.id==='recovery') return frame('What failed tells us what to test next','Day-1 recap + threshold findings · observed failures / remaining work',<>
    {[
      ['Stale watch reference','No grasp started','Revalidate scene + test interventions'],
      ['Wrong-type bank','Defect looked normal','Size routing + crop audit'],
      ['Thin part slipped','Grasp retention failed','Retention checks + bounded failures'],
    ].map(([label,failed,next],i)=><Text key={label} id={`lesson-${i}`} text={`${label}\n${failed}\n\n${next}`} size={29} width={350} height={270} at={{x:320+i*400,y:390}} delay={i===0 ? 0 : 0.12}/>)}
    <Text id="recovery-gap" text="Moved-item recovery and unseen specimens still need a measured test" size={24} width={1152} height={70} color={red} at={{x:720,y:610}} delay={0.24}/>
  </>);
  return frame('The part. The evidence. The decision.',source,<>
    <Photo id="subject" image={a.top} alt="Original top capture of the taped hex bolt" width={640} height={360} at={{x:430,y:382}} delay={0}/>
    <Record id="proof" width={500} height={340} at={{x:1070,y:390}} delay={0.12} lines={[
      {key:'item',value:'002'}, {key:'decision',value:'REJECT',highlight:true},
      {key:'trigger',value:'Top-face tape'}, {key:'tape fraction',value:`${(live.top_tape*100).toFixed(1)}%`},
      {key:'latency',value:`${live.latency_ms.toLocaleString()} ms`}, {key:'execution',value:'Release logged'},
    ]}/>
    <Text id="proof-footnote" text="Recorded evidence · original log available in Sources" size={23} width={1152} at={{x:720,y:631}} color={grey} delay={0.24}/>
  </>);
});

export default deck({title:'Spot it, sort it · Viam × Intel',viewers:[],home},[inspection,learning,deployment]);
