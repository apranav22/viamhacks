# Judged demo: run of show (one page)

Judging is 15:30. Code freeze is about 14:00. The format is a **5-minute run on 6 judge items** (good, defective, at
least one unseen defect type), placed one at a time, then a **5-minute design explanation**. Scoring: detection
precision/recall from our log 30, items ending where decided 30, latency 10, device placement with a measured reason
10, design explanation 20. Keys refer to `ops/STREAMDECK.md` (row, col).

## T-15 min: setup (operator at the laptop, one teammate at the E-stop)

- [ ] Home PC: console running (`ops\console.py --host 127.0.0.1 --host 100.104.1.88`). Laptop: **OPS CONSOLE** (0,4) loads.
- [ ] Console header shows **NOT RUNNING**, health shows `armfarm04b`, release path is the one we mean to run.
- [ ] Nobody else is driving: no teammate run, dashboard Live tab idle, teleop off. Tell the team "arm is ours".
- [ ] **WEBCAM SNAP** (1,3) and **WRIST SNAP** (1,4): pad empty, gripper empty, compartments clear.
- [ ] Deck open on the laptop (`npm run preview`, :5199), on slide 1, window focused. **LIVE BOARD** (2,2) in a second tab.
- [ ] **STATION DASH** (2,3) on the venue screen if the LAN is up (Live tab shows telemetry once the run starts).

## The 5-minute run

| When | Who | Action | Key |
|---|---|---|---|
| 0:00 | E-stop person | Hand on the E-stop, says "ready" | |
| 0:05 | Operator | Arm the judged preset | **ARM JUDGED CPU** (0,1) |
| ≤5 s later | Operator | Sees "Person at E-stop?" banner, looks, confirms | **CONFIRM START** (0,2) |
| 0:15 | Operator | Header turns **sort.py RUNNING**, log shows `[1] WATCH` | page |
| 0:20 – 4:30 | Judge | Places items one at a time on the pad. Wait for `RETURN` / back at watch before the next | page log |
| each item | Narrator | Read out the decision row: decision, view, latency ms | page Decisions |
| after item 6 | Operator | Log ends, header **NOT RUNNING**. sort.py stops itself after `--items 6` | page |
| anything wrong | Anyone | E-stop for motion danger. **STOP** (0,0) ends sort.py (3–6 s) | **STOP** |

If start is refused (alert triangle), read the "Last action" box on the page. "ALREADY_RUNNING" means someone else's
run is live: stop only after talking to them. "MISSING --flag" means the preset needs a newer release.
Do not retry blindly. A mid-run failure: STOP, take both snapshots, then decide with the team whether to restart
for the remaining items.

## The 5-minute explanation (slides with PREV/NEXT (2,0)/(2,1))

| Min | Point | Evidence / key |
|---|---|---|
| 0:00 | Problem and loop: watch → pick → look → decide → sort | deck opening steps |
| 1:00 | Detection: PatchCore (ResNet-18 features + memory bank of good patches) per type/view, tape rule, `--decide top`; the unseen defect is caught as "not normal", not by a learned class | deck "Learn normal, expose the misses" |
| 2:00 | Judge log: every decision with t_seen, t_first_motion, latency, scores in `decisions.jsonl` | **DECISIONS** (2,4): this run's rows |
| 3:00 | Device placement, measured on the station (`tools/device_bench.py`, p50 ms): anomaly model CPU 10.1–12.2, GPU 11.9–23.5, NPU 9.7–10.3; type classifier CPU 12.8, GPU 1.0, NPU 1.1. Anomaly is close on CPU/NPU, GPU is slowest at these sizes, and the type classifier gains 10× off CPU | console Device bench panel |
| 4:00 | Limits stated plainly (small specimen set, picks of small parts), what we would do next | deck closing step, **LIVE BOARD** (2,2) |

After the session: **STATUS** (1,2) shows NOT RUNNING. Arm at home, gripper open. Write `ARM: released` in
`docs/AGENT_LOG.md` if the console did not (it does on STOP).
