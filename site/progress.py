"""Progress section for site/index.html: workstream bars, milestone timeline, parallel lanes.

Edit the tables below as work lands, then `python3 site/build.py`. Each task carries its evidence; `done` is a fraction
(1 = done and verified, 0 < x < 1 = partial, 0 = not started). Weight = rough effort, so the bars mean "share of the
work", not "share of the tickboxes".
"""
from html import escape

AS_OF = "Fri 13 Nov, 15:35 (day 1)"

# needs: arm = the shared arm (one driver at a time) · station = station shell, arm untouched · offline = laptop only ·
# people = staff / teammates
NEEDS = {"arm": ("arm", "#fee2e2", "#991b1b"), "station": ("station", "#e0e7ff", "#3730a3"),
         "offline": ("offline", "#dcfce7", "#166534"), "people": ("people", "#fef3c7", "#92400e")}

# (workstream, owner, colour, [(task, done, weight, needs, evidence)])
STREAMS = [
    ("Perception and model", "A", "#2563eb", [
        ("Tape colour rule on the top look and every webcam view", 1, 2, "offline", "sort.py tape_fraction, TAPE_FRAC 0.02, decides live"),
        ("Collect mode: per pick top + webcam views + meta.json", 1, 2, "arm", "runs/*_collect: 25 picks so far"),
        ("Empty-gripper webcam references, 8 views", 1, 1, "arm", "config/webcam_refs/"),
        ("PatchCore → OpenVINO training + runtime, verified vs torch", 1, 2, "offline", "sorter/: AUROC 1.0 on MVTec, |Δscore| 0.0015, 73 ms CPU f16 (r18)"),
        ("Good-part data for every SKU", 0.15, 3, "arm", "8 picks of 1 clean SKU (button-head) out of ~7"),
        ("Taped-part data", 0.4, 1, "arm", "hex nut ×4, short hex bolt ×5: 2 of ~5 taped SKUs"),
        ("Holdout unseen-defect set (marker, sticker, other tape)", 0, 1, "arm", "none yet; never used for tuning"),
        ("Dataset builder: runs/ → train / val / holdout, split by pick", 0, 1, "offline", "DATA_PLAN.md specifies it"),
        ("Per-view PatchCore banks trained on our crops", 0, 3, "offline", "top/lying, top/upright + one per webcam view"),
        ("Anomaly score wired into DECIDE", 0, 2, "offline", "sort.py: anomaly = None placeholder"),
        ("Thresholds from val/good, calibrated on the deploy device", 0, 1, "station", "f16 shifts scores up to 0.1"),
    ]),
    ("Motion and grasping", "B", "#16a34a", [
        ("Measured poses, table z, obstacles", 1, 2, "arm", "config/poses.json, obstacles.json"),
        ("Webcam calibrated, checkpoint over the reject compartment", 1, 2, "arm", "DLT from 18 fingertip positions; view joints recorded"),
        ("Lying parts: pick, views, place", 1, 2, "arm", "taped nut + bolt, latency 366–433 ms, cycle 12.5–17 s"),
        ("Upright parts: height check, grasp halfway, side views", 0.75, 2, "arm", "one run (5 picks); threshold moved 40 → 15 mm"),
        ("Every SKU grasped at least once", 0.55, 2, "arm", "nut, short hex bolt, socket screw, button-head: 4 of ~7"),
        ("Releases wait for open fingers; pick zone on the bare table", 1, 1, "arm", "fixes from the 15:20 runs"),
        ("Long legs as recorded joint moves", 0.5, 2, "arm", "were 4.0 s and 7.3 s via the planner; joint moves in sort.py, check every leg"),
        ("Recovery L1 (item moved) + L2 (missed grasp)", 1, 2, "offline", "built, emits recovery events"),
        ("Recovery L3: item taken from the gripper in transit", 0, 2, "offline", "poll holding + jaw ~10 Hz, stop(); then one arm test"),
    ]),
    ("Station and diagnostics", "C", "#9333ea", [
        ("Live dashboard: both cameras, inspection strip, map", 1, 2, "offline", "dashboard/server.py :8765"),
        ("Telemetry overhead measured", 1, 1, "offline", "23–74 µs per event, never blocks"),
        ("First-motion latency measured", 1, 1, "arm", "366–433 ms on live picks"),
        ("Benchmark tool for CPU / GPU / NPU", 1, 1, "offline", "sorter/benchmark.py (run on the M2 only)"),
        ("Benchmark run on the station's CPU / GPU / NPU", 0, 2, "station", "Devices = 10% of the score"),
        ("Loop deployed and running on the station", 0, 3, "station", "laptop RPCs add 85–230 ms each"),
        ("Device-placement story with numbers", 0, 1, "offline", "which model on which device, and why"),
    ]),
    ("Integration and story", "D", "#64748b", [
        ("sort.py loop end to end on the arm (collect mode)", 1, 3, "arm", "watch → pick → checkpoint → place, live"),
        ("Judge log with ms timestamps", 1, 1, "offline", "runs/<run>/decisions.jsonl"),
        ("Sort mode (the judged run) live on the arm", 0.4, 2, "arm", "built, decides on tape; every live run so far is collect"),
        ("Log format + latency timestamp confirmed with staff", 0, 1, "people", "open question since 13:00"),
        ("Five-minute rehearsals, teammate as judge (≥5)", 0, 3, "arm", "0 of 5"),
        ("Design explanation (5 min)", 0.3, 2, "offline", "this site + NOTES.md; no slides yet"),
    ]),
]

# (when, title, status, [(item, mark)])   mark: y = done, p = partial, n = missed / not yet
MILESTONES = [
    ("Fri 9:30", "Kickoff", "done", [("Station probed, Track 3 scoped", "y")]),
    ("Fri 13:00", "First contact", "partial", [("Table obstacle on", "y"), ("Hover test", "y"), ("Webcam tested", "y"),
                                              ("First anomaly scores on our camera", "n"), ("Staff questions answered", "p")]),
    ("NOW 15:35", "", "now", []),
    ("Fri 18:00", "Own model + real picks", "risk", [("Pick → present → place on real parts", "y"), ("Own top-view model", "n"),
                                                    ("Diagnostics numbers", "p")]),
    ("Fri 21:00", "Full loop", "todo", [("Webcam-view model", "n"), ("L3 recovery", "n"), ("Loop on the station", "n"),
                                       ("≥5 rehearsals", "n")]),
    ("Sat 9:30", "Hardening", "todo", [("Rehearse, fix, rehearse", "n")]),
    ("Sat 14:00", "Code freeze", "todo", [("Numbers + explanation", "n")]),
    ("Sat 15:30", "Demos + judging", "todo", []),
]

# Parallel lanes: who can work at the same time without touching the arm. Lane 1 is the only one that needs it.
LANES = [
    ("1 · Arm lane (one driver, serial)", "arm",
     ["Collect good parts of every SKU (biggest gap), then taped variants, then the holdout set",
      "Verify every long leg is a recorded joint move", "Live sort-mode runs, then rehearsals with a teammate as judge"],
     "Feeds lane 2 with data. Everything else is built to plug into it without blocking it."),
    ("2 · Model agent", "offline",
     ["Dataset builder: runs/ → train / val / holdout by pick", "Train per-view PatchCore banks with sorter/train_detector.py on the 25 picks we have; retrain as lane 1 adds data",
      "Validate with synthetic defects; per-view false-alarm rate on good parts"],
     "Outputs model files + thresholds for lane 3. Can start now on the existing runs."),
    ("3 · Integration agent", "offline",
     ["Anomaly score into DECIDE (behind a flag, tape rule stays)", "L3: holding + jaw poll during moves, stop(), re-run as the same item",
      "Test both on the fake station"],
     "Build in vh/ and hook into sort.py in one small diff: sort.py is being edited by the arm session."),
    ("4 · Station agent", "station",
     ["setup on the station, run the loop there in dry run", "benchmark.py on CPU / GPU / NPU; check PatchCore compiles on the NPU",
      "Calibrate thresholds on the deploy device"],
     "Never moves the arm. Gives the Devices score (10%) its numbers."),
    ("5 · Story (human + agent)", "people",
     ["Confirm log format and latency timestamp with staff", "Draft the 5-min explanation from NOTES.md and this site"],
     "No code dependencies; can run all evening."),
]


def pct(tasks):
    w = sum(t[2] for t in tasks)
    return 100 * sum(t[1] * t[2] for t in tasks) / w


def bar(p, colour, h=12):
    return (f'<div class="pbar" style="height:{h}px"><i style="width:{p:.0f}%;background:{colour}"></i></div>')


def chip(needs):
    label, bg, fg = NEEDS[needs]
    return f'<span class="pill" style="background:{bg};color:{fg}">{label}</span>'


def state(done):
    if done >= 1:
        return '<span class="pill easy">done</span>'
    if done > 0:
        return f'<span class="pill medium">{100 * done:.0f}%</span>'
    return '<span class="pill hard">to do</span>'


def stream_card(name, owner, colour, tasks):
    p = pct(tasks)
    n_done = sum(1 for t in tasks if t[1] >= 1)
    rows = "".join(
        f'<tr><td>{state(d)}</td><td>{escape(t)}<div class="ev">{escape(ev)}</div></td><td>{chip(nd)}</td></tr>'
        for t, d, _, nd, ev in tasks)
    return f"""<div class="card" style="border-top:5px solid {colour}">
<div class="phead"><h3>{escape(name)} <span class="mute">({owner})</span></h3><b style="color:{colour}">{p:.0f}%</b></div>
{bar(p, colour)}<p class="ev" style="margin:6px 0 10px">{n_done} of {len(tasks)} tasks done</p>
<details><summary>Tasks</summary><table class="ptab">{rows}</table></details></div>"""


def timeline():
    mark = {"y": "✓", "p": "◐", "n": "✗"}
    col = {"done": "#16a34a", "partial": "#f59e0b", "risk": "#ef4444", "todo": "#cbd5e1", "now": "#2563eb"}
    out = []
    for when, title, st, items in MILESTONES:
        if st == "now":
            out.append(f'<div class="ms now"><b>{when}</b><span>we are here</span></div>')
            continue
        lis = "".join(f'<li class="m{m}">{mark[m]} {escape(i)}</li>' for i, m in items)
        tag = {"done": "done", "partial": "partly met", "risk": "at risk", "todo": "ahead"}[st]
        out.append(f'<div class="ms" style="border-top-color:{col[st]}"><b>{when}</b><span class="mt">{escape(title)}</span>'
                   f'<span class="tag" style="color:{col[st] if st != "todo" else "#64748b"}">{tag}</span><ul>{lis}</ul></div>')
    return '<div class="tl">' + "".join(out) + "</div>"


def lanes():
    cards = []
    for title, needs, items, note in LANES:
        lis = "".join(f"<li>{escape(i)}</li>" for i in items)
        cards.append(f'<div class="card"><h3>{escape(title)} {chip(needs)}</h3><ul>{lis}</ul><p class="ev" style="margin-top:8px">{escape(note)}</p></div>')
    return '<div class="grid g3">' + "".join(cards) + "</div>"


CSS = """
.pbar{background:#e2e8f0;border-radius:999px;overflow:hidden} .pbar i{display:block;height:100%;border-radius:999px}
.phead{display:flex;justify-content:space-between;align-items:baseline} .phead b{font-size:22px} .mute{color:var(--mute);font-weight:400}
.ev{font-size:12.5px;color:var(--mute)} details summary{cursor:pointer;font-size:14px;color:var(--acc)}
.ptab{border:0;margin-top:8px;font-size:13.5px} .ptab td{padding:6px 6px;border-bottom:1px solid var(--line)} .ptab td:first-child{width:62px}
.overall{display:grid;grid-template-columns:auto 1fr;gap:6px 22px;align-items:center}
.overall .big2{font-size:52px;font-weight:750;line-height:1;color:var(--ink)}
.tl{display:flex;gap:8px;overflow-x:auto;padding-bottom:6px}
.ms{flex:1 0 150px;background:var(--card);border:1px solid var(--line);border-top:5px solid #cbd5e1;border-radius:12px;padding:10px 12px;font-size:13px}
.ms b{display:block;font-size:13px} .ms .mt{display:block;font-weight:600;font-size:14px} .ms .tag{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}
.ms ul{list-style:none;padding:0;margin:6px 0 0} .ms li{margin:2px 0} .my{color:#166534} .mp{color:#92400e} .mn{color:#991b1b}
.ms.now{flex:0 0 96px;background:#2563eb;color:#fff;border-color:#2563eb;display:flex;flex-direction:column;justify-content:center;text-align:center}
"""


def section():
    every = [t for _, _, _, ts in STREAMS for t in ts]
    total = pct(every)
    off_arm = [t for t in every if t[1] < 1 and t[3] != "arm"]
    left_w = sum(t[2] * (1 - t[1]) for t in every)
    off_w = sum(t[2] * (1 - t[1]) for t in off_arm)
    mini = "".join(f'<div>{escape(n)}</div><div style="display:flex;gap:10px;align-items:center">{bar(pct(ts), c, 10)}<b style="min-width:42px">{pct(ts):.0f}%</b></div>'
                   for n, _, c, ts in STREAMS)
    cards = "".join(stream_card(*s) for s in STREAMS)
    return f"""<section id="progress"><h2>Progress</h2>
<p class="lead">Planning snapshot · {AS_OF}. Historical estimates, not live completion or model results. Use the data overview above for measured capture counts.</p>
<details class="fold"><summary>Workstreams, task evidence &amp; timeline · dated planning estimate</summary><div class="fold-body">
<p class="reference-note">Bars weight tasks by rough effort. Evidence and status below are preserved as of the planning date, not re-verified by this page build.</p>
<div class="grid g2">
<div class="card"><div class="overall"><div class="big2">{total:.0f}%</div>
<div>{bar(total, "linear-gradient(90deg,#2563eb,#16a34a)", 18)}<p class="ev" style="margin:6px 0 0">whole project, {sum(1 for t in every if t[1] >= 1)} of {len(every)} tasks done</p></div></div>
<div class="overall" style="margin-top:16px;font-size:14px">{mini}</div></div>
<div class="callout warn"><p class="big">Motion is ahead of plan; perception is the critical path.</p>
<p style="margin:8px 0 0">Live pick → checkpoint → place already works (an 18:00 goal). The 13:00 goal "first anomaly scores on our camera" hasn't happened,
and DECIDE still runs on the tape rule alone, which can't catch the judges' unseen defect. The gap is good-part data for most SKUs and a trained model.
<b>{100 * off_w / left_w:.0f}% of the remaining work doesn't need the arm</b>, so it can run in parallel (lanes below).</p></div>
</div>
<h3 style="margin:22px 0 10px">Workstreams</h3>
<div class="grid g2">{cards}</div>
<h3 style="margin:22px 0 10px">Timeline</h3>
{timeline()}
<h3 style="margin:22px 0 6px">What can run in parallel</h3>
<p class="lead">The arm is the one serial resource (one driver at a time). Lanes 2–5 never move it, so separate agents can take them now.
Data flows 1 → 2 → 3; lane 4 calibrates what lane 2 trains.</p>
{lanes()}
</div></details>
</section>"""
