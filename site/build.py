"""Builds site/index.html (static, no dependencies). Run: python3 site/build.py && python3 -m http.server 8899 -d site"""
import math
from pathlib import Path

HERE = Path(__file__).parent


def arc(cx, cy, r, a0, a1):
    """SVG arc path from angle a0 to a1 (degrees, math convention: 0 = right, 90 = up)."""
    p = lambda a: (cx + r * math.cos(math.radians(a)), cy - r * math.sin(math.radians(a)))
    (x0, y0), (x1, y1) = p(a0), p(a1)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M{x0:.1f},{y0:.1f} A{r},{r} 0 {large} 0 {x1:.1f},{y1:.1f}"


def coverage_svg():
    cx, cy, r = 300, 165, 62
    rings = [  # (radius, a0, a1, color, label)
        (80, 30, 150, "#22c55e", "wrist cam, top-down (before grasp)"),
        (92, 210, 330, "#3b82f6", "fingertips at camera (underside)"),
        (104, 165, 285, "#f59e0b", "tilt −45°"),
        (104, 255, 375, "#f59e0b", "tilt +45°"),
    ]
    parts = [f'<svg viewBox="0 0 900 330" class="diagram" role="img" aria-label="coverage of a bolt shank cross-section">']
    parts.append(f'<line x1="20" y1="{cy + r + 2}" x2="460" y2="{cy + r + 2}" stroke="#94a3b8" stroke-width="3" stroke-dasharray="6 5"/>')
    parts.append(f'<text x="20" y="{cy + r - 6}" class="small mute">table (before the grasp)</text>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#cbd5e1" stroke="#475569" stroke-width="2"/>')
    parts.append(f'<text x="{cx}" y="{cy + 5}" text-anchor="middle" class="small dark">shank cross-section</text>')
    for rad, a0, a1, col, _ in rings:
        parts.append(f'<path d="{arc(cx, cy, rad, a0, a1)}" fill="none" stroke="{col}" stroke-width="7" stroke-linecap="round" opacity="0.9"/>')
    # finger pads at 0 and 180 deg
    w = 14
    for x in (cx + r + 1, cx - r - 1 - w):
        parts.append(f'<rect x="{x}" y="{cy - 22}" width="{w}" height="44" rx="3" fill="#ef4444"/>')
    # weak bands (grazing only)
    for a0, a1 in ((12, 30), (150, 168)):
        parts.append(f'<path d="{arc(cx, cy, r - 6, a0, a1)}" fill="none" stroke="#a855f7" stroke-width="8"/>')
    ly = 40
    legend = [(c, l) for _, _, _, c, l in rings[:3]] + [("#ef4444", "finger pads (contact patches hidden)"), ("#a855f7", "weak band: only grazing views")]
    legend[2] = ("#f59e0b", "tilted views ±45° (sides)")
    for col, lab in legend:
        parts.append(f'<rect x="500" y="{ly - 11}" width="16" height="12" rx="2" fill="{col}"/><text x="524" y="{ly}" class="small">{lab}</text>')
        ly += 26
    parts.append('<text x="500" y="200" class="small mute">Arcs = surface seen at a useful angle</text>')
    parts.append('<text x="500" y="218" class="small mute">(within ~60° of the view direction).</text>')
    parts.append('<text x="500" y="246" class="small mute">Gripping across the shank puts the pads</text>')
    parts.append('<text x="500" y="264" class="small mute">exactly where every view is grazing.</text>')
    parts.append('<text x="500" y="292" class="small mute">Fix: grip the head, or regrasp once</text>')
    parts.append('<text x="500" y="310" class="small mute">for items that look good.</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def score_bar():
    segs = [("Decision", 30, "#2563eb", "precision + recall of defects, from our log"),
            ("Execution", 30, "#16a34a", "item ends where we decided"),
            ("Latency", 10, "#f59e0b", "item seen → first arm motion (correct items)"),
            ("Devices", 10, "#9333ea", "device placement, measured via diagnostics"),
            ("Design", 20, "#64748b", "5-min explanation")]
    bar = "".join(f'<div class="seg" style="flex:{w};background:{c}" title="{d}"><b>{n}</b><span>{w}%</span></div>' for n, w, c, d in segs)
    legend = "".join(f'<li><i style="background:{c}"></i><b>{n} {w}%</b> {d}</li>' for n, w, c, d in segs)
    return f'<div class="bar">{bar}</div><ul class="legend">{legend}</ul>'


CASES = [
    # (case, difficulty, who sees it, failure mode, mitigation)
    ("Tape facing up", "easy", "Wrist close-up (top)", "None really; tape is high-contrast", "Early exit → reject, skip presenting"),
    ("Tape facing the table", "medium", "Underside view (fingertips at camera)", "Top view says clean → would box it", "Pick everything; present underside before deciding"),
    ("Tape where the fingers grip", "hard", "Only grazing views / nobody", "Pads cover it; looks clean everywhere", "Grip bolts by the head; tilt views; regrasp once if ‘good’"),
    ("Tiny tape (e.g. bolt tip)", "medium", "Close-up views only", "Too few pixels at survey height (1 mm/px)", "Decide from close-ups, never from the survey frame"),
    ("Good item", "hard", "Must see all surfaces", "Any one view false-alarms → false reject", "Coverage + per-view thresholds set jointly for a false-alarm budget"),
    ("Unseen defect: appearance (marker, sticker, rust, paint)", "medium", "Anomaly model, any view", "Tape rule misses it; subtle ones score low", "PatchCore trained on good only; test on a held-out defect set"),
    ("Unseen defect: shape (bent, wrong length, stripped thread)", "medium", "Silhouette + depth", "Texture model may not care about shape", "Primitive fit: length/width/straightness vs known part types"),
    ("Judge moves an item", "medium", "Survey re-look", "Grasp misses, stale position", "Re-look before grasp; IsHoldingSomething; retry ×2"),
]

RECON = [
    ("3DGS / NeRF / MERF", "Photoreal novel views from many posed images",
     "30–100+ views, accurate poses, minutes of GPU per item; mostly CUDA code; not an OpenVINO model",
     "Can only re-render what some camera saw. Hidden faces stay hidden (or get hallucinated). It doesn't add evidence.", "no"),
    ("Primitive models + coverage map", "Which % of each part's surface was seen, in which view, at what resolution",
     "Cylinder / hex prism per part type, view poses we already know; ms of CPU", "Turns ‘looks clean’ into ‘looked clean over 93% of the surface’ → honest confidence, tells us when to take another view", "yes"),
    ("Primitive fit for shape defects", "Length, width, straightness, head size vs known types",
     "Silhouette from the survey / close-up + depth; ms of CPU", "Catches geometric unseen defects (bent, wrong length) a texture model may miss", "yes"),
    ("Unwrap the shank onto a strip (texture atlas)", "One canonical ‘unrolled’ image per part from all views",
     "View poses + cylinder model + blending; a few hours to build", "Clean input for the anomaly model and a great demo visual; not needed to win", "stretch"),
]


def html():
    cases = "".join(
        f'<tr><td><b>{c}</b></td><td><span class="pill {d}">{d}</span></td><td>{w}</td><td>{f}</td><td>{m}</td></tr>'
        for c, d, w, f, m in CASES)
    recon = "".join(
        f'<tr><td><b>{n}</b></td><td>{g}</td><td>{cost}</td><td>{why}</td><td><span class="pill v-{v}">{v}</span></td></tr>'
        for n, g, cost, why, v in RECON)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Track 3: Spot it, sort it</title>
<style>
:root{{--bg:#f8fafc;--card:#fff;--ink:#0f172a;--mute:#64748b;--line:#e2e8f0;--acc:#2563eb}}
*{{box-sizing:border-box}} body{{margin:0;font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;color:var(--ink);background:var(--bg)}}
header{{background:linear-gradient(120deg,#0f172a,#1e3a8a);color:#fff;padding:42px 6vw 30px}}
header h1{{margin:0 0 6px;font-size:34px}} header p{{margin:0;opacity:.85;max-width:900px}}
nav{{position:sticky;top:0;z-index:5;background:#0f172aee;backdrop-filter:blur(6px);padding:10px 6vw;display:flex;gap:18px;flex-wrap:wrap}}
nav a{{color:#cbd5e1;text-decoration:none;font-size:14px}} nav a:hover{{color:#fff}}
main{{padding:10px 6vw 80px;max-width:1300px}}
section{{margin:34px 0}} h2{{font-size:24px;margin:0 0 4px}} .lead{{color:var(--mute);margin:0 0 16px;max-width:900px}}
.grid{{display:grid;gap:16px}} .g2{{grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}} .g3{{grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;box-shadow:0 1px 2px #0000000a}}
.card h3{{margin:0 0 8px;font-size:17px}} .card ul{{margin:6px 0 0;padding-left:18px}} .card li{{margin:3px 0}}
.state{{border-top:5px solid var(--acc)}} .state.end{{border-top-color:#16a34a}}
.flow{{display:flex;flex-wrap:wrap;align-items:stretch;gap:8px}}
.step{{flex:1 1 105px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;position:relative}}
.step b{{display:block;font-size:13px;letter-spacing:.04em;color:var(--acc)}} .step span{{font-size:14px}}
.step.mark{{border:2px solid #f59e0b}} .step.mark b{{color:#b45309}}
.arrow{{align-self:center;color:#94a3b8;font-size:22px}}
.bar{{display:flex;height:58px;border-radius:12px;overflow:hidden;box-shadow:inset 0 0 0 1px #0001}}
.seg{{color:#fff;display:flex;flex-direction:column;justify-content:center;padding:0 12px;font-size:13px}} .seg span{{opacity:.9}}
.legend{{list-style:none;padding:0;margin:12px 0 0;display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:6px 18px;font-size:14px}}
.legend i{{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:6px}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;font-size:14px}}
th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}} th{{background:#f1f5f9;font-size:13px;color:#334155}}
.pill{{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600}}
.easy{{background:#dcfce7;color:#166534}} .medium{{background:#fef3c7;color:#92400e}} .hard{{background:#fee2e2;color:#991b1b}}
.v-yes{{background:#dcfce7;color:#166534}} .v-no{{background:#fee2e2;color:#991b1b}} .v-stretch{{background:#e0e7ff;color:#3730a3}}
.diagram{{width:100%;height:auto;background:var(--card);border:1px solid var(--line);border-radius:14px}}
.diagram .small{{font-size:13px;fill:#334155}} .diagram .dark{{fill:#0f172a}} .diagram .mute{{fill:#64748b}}
.big{{font-size:20px;font-weight:650;margin:0}} .callout{{background:#eff6ff;border:1px solid #bfdbfe;border-radius:14px;padding:16px 20px}}
.callout.warn{{background:#fff7ed;border-color:#fed7aa}}
figure{{margin:0}} figure img{{width:100%;border-radius:10px;border:1px solid var(--line)}} figcaption{{font-size:13px;color:var(--mute);margin-top:6px}}
code{{background:#f1f5f9;padding:1px 5px;border-radius:5px;font-size:13px}}
.eq{{font-family:ui-monospace,Menlo,monospace;background:#0f172a;color:#e2e8f0;border-radius:10px;padding:12px 16px;font-size:14px;overflow:auto}}
</style></head><body>
<header><h1>Track 3: Spot it, sort it</h1>
<p>Six judge items, five minutes. Find every defect (including one we've never seen), put each item where we said we would, and prove it in a log.
This page: the run from first to last state, what the judges measure, where detection breaks, and whether 3D reconstruction helps.</p></header>
<nav><a href="#states">Start → end</a><a href="#scoring">Scoring</a><a href="#asym">The core problem</a><a href="#cases">Cases</a><a href="#coverage">Coverage</a>
<a href="#decide">Decision rule</a><a href="#recon">3D reconstruction?</a><a href="#evals">Our evals</a><a href="#station">What we see</a><a href="#open">Open questions</a></nav>
<main>

<section id="states"><h2>Start state → end state</h2><p class="lead">What the judged run looks like, as we currently assume it.</p>
<div class="grid g2">
<div class="card state"><h3>Initial state</h3><ul>
<li>6 fasteners on the white table, <b>separated</b> (no overlap, no occlusion between items), random positions and orientations</li>
<li>Some defective: blue tape, <b>possibly facing the table</b>; at least one <b>defect type we've never seen</b></li>
<li>Box (good) and reject bin (defective / unsure) at fixed, taught positions</li>
<li>Arm at home (= survey pose), gripper open, models loaded and warm on the GPU, our loop running on the station</li></ul></div>
<div class="card state end"><h3>Final state</h3><ul>
<li>All 6 items in the box or the reject bin, none dropped, table clear</li>
<li><b>Log: exactly one line per item</b>: number, decision, confidence, timestamp (+ our extra fields)</li>
<li>Arm back home, gripper empty, no faults</li>
<li>Diagnostics saved: per-device benchmarks, live latency stats, per-item views and heatmaps for the explanation</li></ul></div>
</div>
<h3 style="margin:22px 0 10px">Per item</h3>
<div class="flow">
<div class="step"><b>SURVEY</b><span>home view, find blobs → world XY + yaw</span></div><div class="arrow">→</div>
<div class="step mark"><b>MOVE ABOVE</b><span>first motion: latency clock stops here</span></div><div class="arrow">→</div>
<div class="step"><b>TOP LOOK</b><span>wrist close-up: anomaly + tape</span></div><div class="arrow">→</div>
<div class="step"><b>PICK</b><span>grab, verify holding (retry if moved)</span></div><div class="arrow">→</div>
<div class="step"><b>PRESENT</b><span>underside + 2 tilts to the fixed camera (skip if already clearly defective)</span></div><div class="arrow">→</div>
<div class="step"><b>DECIDE + LOG</b><span>any view anomalous → reject</span></div><div class="arrow">→</div>
<div class="step"><b>PLACE</b><span>box / reject, back to survey</span></div>
</div>
<p class="lead" style="margin-top:10px">≈18–22 s per item at the arm's 60 deg/s → ~2 min for 6 items; plenty of slack in 5 minutes for a regrasp or a retry.</p>
</section>

<section id="scoring"><h2>What the judges measure</h2><p class="lead">Reference sheet weights. Detection is scored from <b>our own log</b>: no log, no decision or latency points.</p>
{score_bar()}
<div class="grid g3" style="margin-top:16px">
<div class="card"><h3>Decision (30%) in practice</h3>With 6 items, every mistake is ~15–30% of this bucket. A false reject (good → reject) costs <b>precision</b>; a missed defect (defect → box) costs <b>recall</b>.</div>
<div class="card"><h3>Execution (30%) is separate</h3>A wrong decision placed correctly still scores execution: the item ended where <i>we</i> decided. Grasp reliability is worth as much as detection.</div>
<div class="card"><h3>Latency only counts correct items</h3>Inspection moves count as the response, so latency is the time to <i>notice</i> the part, not to classify it.</div>
</div></section>

<section id="asym"><h2>The core problem: defect and good are not symmetric</h2>
<div class="grid g2">
<div class="callout"><p class="big">“Defective” needs one piece of evidence.</p>One view with tape or a strong anomaly is enough. That's why the tape-up case is easy.</div>
<div class="callout warn"><p class="big">“Good” needs the absence of evidence everywhere.</p>“I didn't see a defect” only means “good” if we looked at the whole surface, well enough to have seen one. The no-defect case and the hidden-tape case are <b>the same problem: coverage.</b></div>
</div>
<div class="grid g2" style="margin-top:16px">
<div class="card"><h3>More views → fewer misses…</h3>Each extra view uncovers surface where a defect could hide, so recall goes up.</div>
<div class="card"><h3>…but more chances to false-alarm</h3>Each view of a good part is another chance for a spurious high score. With N views, per-view false alarms add up: set per-view thresholds so the <b>whole item</b> stays within a false-alarm budget (e.g. per-view ≈ budget / N).</div>
</div></section>

<section id="cases"><h2>Cases, ranked by how they fail</h2><p class="lead">Separated items mean finding parts is simple blob detection on a white table. These are the detection cases we need to cover.</p>
<table><tr><th>Case</th><th>Difficulty</th><th>Who can see it</th><th>How it fails</th><th>Mitigation</th></tr>{cases}</table></section>

<section id="coverage"><h2>Coverage: can two cameras see 360°?</h2>
<p class="lead">Almost. A top-down grasp leaves the face that was on the table facing out past the fingertips. So <b>pointing the fingertips at the fixed camera shows exactly the hidden side</b>. Spinning about the gripper's own axis only rotates the picture; <b>tilting</b> shows the sides.</p>
{coverage_svg()}
<div class="grid g3" style="margin-top:16px">
<div class="card"><h3>Views per item</h3><ol style="margin:0;padding-left:18px"><li>Wrist close-up, top-down, before the grasp</li><li>Fingertips at the fixed camera (underside)</li><li>Tilt −45°</li><li>Tilt +45°</li></ol></div>
<div class="card"><h3>The blind spot</h3>The finger contact patches sit at the shank's “equator”, which every view sees only at a grazing angle. Tape exactly there is our worst case.</div>
<div class="card"><h3>Closing it</h3><ul><li>Grip bolts by the <b>head</b>, so the whole shank is free</li><li>For items that still look good: put down, regrasp rotated 90°, one more underside view (~6 s, only on ‘good’ items)</li></ul></div>
</div></section>

<section id="decide"><h2>Decision rule and confidence</h2>
<div class="eq">reject  if  max over views ( anomaly_score_v / threshold_v ) ≥ 1   or   tape_fraction ≥ t_tape<br>
box     if  all views below threshold   and   coverage ≥ C_min<br>
else    → one more view (regrasp) if time allows, otherwise reject (unsure = reject)<br><br>
confidence(reject) = how far the worst view is past its threshold (calibrated on validation scores)<br>
confidence(box)    = coverage × how far the worst view is below its threshold</div>
<p class="lead" style="margin-top:10px">Coverage comes from the primitive model below: the fraction of the part's surface seen at a useful angle and resolution.</p></section>

<section id="recon"><h2>Is there alpha in 3D reconstruction (3DGS, NeRF, MERF)?</h2>
<div class="callout warn"><p class="big">Not for detection. Reconstruction can only re-render what some camera already saw.</p>
Our failure mode is <i>unobserved</i> surface. A radiance field doesn't create evidence for a face nobody imaged; it would hallucinate it. It also needs dozens of posed views and minutes of GPU per item, mostly in CUDA code. It isn't an OpenVINO model, so it doesn't help the device-placement story either.
And depth won't find tape: the wrist camera <i>is</i> RGB-D, but tape is ~0.1 mm thick.</div>
<p class="lead" style="margin-top:14px">The 3D idea that <b>does</b> pay is cheap and geometric: model each part type as primitives (cylinder shank, hex head/nut) and use that to account for coverage and catch shape defects.</p>
<table><tr><th>Approach</th><th>What it gives</th><th>Cost</th><th>Why it matters (or not)</th><th>Verdict</th></tr>{recon}</table></section>

<section id="evals"><h2>Our evals (mirror the judging)</h2>
<div class="grid g2" style="grid-template-columns:repeat(2,minmax(0,1fr))">
<div class="card"><h3>1. Offline replay (no arm needed)</h3>Every rehearsal saves all views of every item. Re-run detection with new models or thresholds over the whole history in seconds. Report:<ul>
<li>Precision / recall / confusion per case (rows of the table above)</li><li>Per-view and per-item false-alarm rate on good parts</li><li>Score margins: how far good and defective sit from the threshold</li></ul></div>
<div class="card"><h3>2. Rehearsal kits (arm in the loop)</h3>Scripted 6-item kits, timed 5-minute runs, a teammate as judge:<ul>
<li>Kit A: tape up/down mix · Kit B: tape at the grip · Kit C: all good · Kit D: unseen defects · Kit E: a judge moves items mid-run</li>
<li>Score each run exactly like the judges: decision P/R from the log, execution, latency of correct items</li></ul></div>
<div class="card"><h3>3. Held-out defect discipline</h3>Keep a set of defects <b>nobody trains or tunes on</b> (marker, sticker, bent bolt, paint, other-colored tape). It's our only honest stand-in for the judges' unseen type. Tuning on it means fooling ourselves.</div>
<div class="card"><h3>4. Numbers for the pitch</h3>Per-device benchmark table (ov-diag), per-stage latency waterfall, confusion matrix per kit, coverage per item, and a short list of what failed and what we changed.</div>
</div></section>

<section id="station"><h2>What the station sees today</h2>
<div class="grid g2">
<figure><img src="img/survey_annotated.jpg" alt=""><figcaption>Survey from home: wrist cam straight down from ~64 cm, 1.06 mm/px. Every zinc part found with world XY and yaw. Stainless parts partly missed; touching parts merge; the gripper finger (bottom right) needs a mask.</figcaption></figure>
<figure><img src="img/overview_now.jpg" alt=""><figcaption>overview-cam as placed: ~1 m away, low angle, busy background. Too far for the underside views; we want the stand moved 20–30 cm from a presentation spot with a white card behind it.</figcaption></figure>
<figure><img src="img/cam_color.jpg" alt=""><figcaption>Wrist close-up at ~17 cm: threads are clearly visible; this is the scale for anomaly crops.</figcaption></figure>
<figure><img src="img/home_color.jpg" alt=""><figcaption>The raw survey frame before segmentation.</figcaption></figure>
</div></section>

<section id="open"><h2>Open questions</h2>
<div class="grid g3">
<div class="card"><h3>For staff</h3><ul><li>May we move the overview-cam stand and add a backdrop?</li><li>Are all 6 items on the table at the start, or added one by one?</li><li>Which log timestamp do they use for latency?</li></ul></div>
<div class="card"><h3>For us to test</h3><ul><li>Webcam focus and resolution at 20 / 30 / 40 cm</li><li>Grasp by the head vs the shank, per part type</li><li>Per-view false-alarm rate on good parts</li></ul></div>
<div class="card"><h3>Assumptions on this page</h3><ul><li>Items are separated</li><li>Unsure = reject (reject bin = hold area)</li><li>Inspection moves count as the response</li></ul></div>
</div></section>
</main></body></html>"""


if __name__ == "__main__":
    (HERE / "index.html").write_text(html())
    print("wrote", HERE / "index.html")
