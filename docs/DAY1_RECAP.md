# Day 1 recap (2026-11-13)

[claude-code/claude-fable-5-2 · op Ali · Alis-MacBook-Air · ali/pipeline · 22:55]

A recap only: what was built, what was captured, what went wrong. Nothing here proposes a fix. Sources:
`docs/AGENT_LOG.md` (times are its clock, EST), the files under `runs/`, the model manifests, `git log`.
Numbers about runs come from `python3 catalog.py`; regenerate rather than edit them.

## In one minute

- The whole Track 3 loop exists and ran on the station: watch → look (wrist, top view) → pick → hold in front of the
  webcam → decide → box or reject, with a log row per item. It was exercised in six short live sort runs (30 items
  decided).
- 42 collect runs produced **205 captured picks** (2,380 images). On the current capture recipe, 171 are usable as
  logged: 143 good, 28 defective (16 tape, 6 marker, 6 other mark), over six part types.
- Nine anomaly bundles were trained. The first station sort run used `each_cardboard_v3/bundle_m103`; the last two
  runs used `each_cardboard_v4`, which has no evaluation and exists only on the station.
- In the live runs, **13 of 16 rejects came from the blue-tape colour rule**, 2 from the anomaly model, 1 from an
  upright-part skip. Two known escapes (taped parts sent to GOOD) and one known false reject are in the log.
- Three part types are not picked reliably by `sort.py` as committed: `socket_thin_short`, `hex_nut`,
  `hex_bolt_short`. Their captures came from ad-hoc scripts or ended in an E-stop.
- Two operator E-stops (15:48 upright descent, 19:03 repeated misses on a short bolt), and three ways a loop kept
  running or hung when it should not have.

## Where to look

| For | Open |
|---|---|
| Every run with its pictures and metadata | `open runs/index.html` (after `python3 catalog.py`) |
| The same as a table, in git | [`RUN_CATALOG.md`](RUN_CATALOG.md) |
| Why a run is flagged | [`run_notes.json`](run_notes.json): one sourced note per run |
| Minute-by-minute evidence | [`AGENT_LOG.md`](AGENT_LOG.md) |
| Threshold experiments and the mistakes behind each rule | [`THRESHOLD_FINDINGS.md`](THRESHOLD_FINDINGS.md) |
| Getting the data | `python sync_data.py pull` ([`DATA_PLAN.md`](DATA_PLAN.md), end) |

The catalog page has five tabs. **Overview**: usable picks per part and label; click a number for those picks.
**Runs**: every run in real time order with its note; click a pick for all its images, the scores per view,
`meta.json`, its `decisions.jsonl` row and which model bundles list it as train / calibration / test. **All picks**:
filter across runs. **Experiments**: the camera and calibration sweeps. **Models**: what each bundle was built from.

Station run names use the station clock, 2 h behind the laptop (`171443_collect` on the station = 19:14 EST). The
catalog orders by real time and shows both.

## What we built, in order

| EST | What |
|---|---|
| 12:00–13:00 | Baseline cycle offline and in dry run: `run.py`, `vh/`, UDP dashboard, fake station, tests. No motion. |
| 13:00–14:55 | Arm bring-up. Checkpoint in front of the webcam, jaws close along gripper y, webcam to 1080p, webcam moved to a tripod and re-calibrated from 18 fingertip positions, five capture views over the reject compartment. `AGENTS.md`. |
| 15:05–15:48 | `sort.py` collect mode live for the first time (white table, wrist 640×480): taped nut, upright taped short bolt, clean button screw, clean large socket screw. **E-stop 15:48**: an upright bolt touched the gripper body on descent. Upright grasp off by default since. |
| 16:00–17:35 | Capture recipe. Offline PatchCore → OpenVINO pipeline; camera sweeps; wrist to 1280×720, brightness 8, exposure 100; cardboard pad measured by touch (z 6.5 mm); look pose with the lens 190 mm over the part; lamp LED. Station deploys, training dashboard on :8770. |
| 17:34–19:05 | Bulk good collection from the laptop on the new recipe: long hex bolt 30, big socket 41, button 21, short hex bolt 11. Three baseline sort runs on the laptop. **E-stop 19:03**: repeated misses on the short hex bolt, cardboard torn. |
| 19:10–19:50 | Loop moved onto the station (`station_run.py`). Defect set: 28 picks (tape, marker, other). Top-crop experiments, per-type banks, `each_cardboard_v3`, margin 1.03. First station sort run: two escapes. Auto type switched from best-fitting bank to measured size. Thin long socket ×20. HF data repo + station cron. Explorer and quality monitor (Vedant). |
| 19:46–20:20 | `socket_thin_short` will not stay in the grip. Lower-grasp probe, retention probe, then a head-targeted grasp: 7 captures. |
| 20:21–20:27 | A second agent session's sort run never left WATCH (hand gate latched on a stale reference). |
| 20:28–21:00 | `hex_nut`: 21 captures across five runs, each with another ad-hoc fix. `each_cardboard_v4` trained. Two short sort runs. All loops stopped and verified at 21:00. |

## What we captured

Captured picks, current recipe (cardboard, 1280×720, LED), runs flagged ok / partial, excluded items removed:

| Part | good | tape | marker | other | Note |
|---|---:|---:|---:|---:|---|
| `hex_bolt_partial` (long hex bolt) | 30 | 6 | 6 | · | 3 more good picks in `172508` are excluded (bad top crop) |
| `socket_m16` (big socket screw) | 40 | 6 | · | 6 | 3 excluded in `181752` |
| `button_ss_long` | 21 | 4 | · | · | 10 looped attempts excluded in `183403` |
| `socket_thin_long` | 20 | · | · | · | no defect captures |
| `hex_nut` | 21 | · | · | · | no defect captures; ad-hoc scripts |
| `hex_bolt_short` | 11 | · | · | · | no defect captures; run ended in an E-stop |
| `socket_thin_short` | (7) | · | · | · | flagged review-first: grasp probes, 1 mm clearance |

Also on disk: 23 picks on the legacy recipe (before 17:07, 640×480, background not recorded; they include the only
taped-nut and upright-bolt captures), eight camera / calibration experiment folders, 35 dry runs.

Things the counts hide:

- Each cell is close to **one physical part picked many times**. Repeats are not independent samples.
- Defect captures exist for three of seven part types. "Other" (non-blue mark) exists for one.
- The defect runs `171443` and `171810` were used to choose margin 1.03 and are listed as test picks in
  `each_cardboard_v3`. They are development data now.
- Sort-run items have no ground-truth label in the data. The log gives it for two runs (9 items).
- One item folder (`182200_collect`) has 10 images and no metadata at all.

## Models

| Bundle | Built from | Crop | Where | Used live |
|---|---|---|---|---|
| `button_white_v1`, `button_xpu_v1/v2`, `any_white_v1` | 9–12 legacy picks | square-context-v1 | shared | no |
| `hexbolt_cardboard_v1` | 30 long hex bolt picks | square-context-v1 | laptop + shared | `180637`, `181214` |
| `any_cardboard_v1` / `v2` | pooled, 71 / 91 picks | square-context-v1 | shared / laptop + shared | `184840` (v2) |
| `each_cardboard_v3` (margin 1.15) and `bundle_m103` (1.03) | per type, 4 types, 113 picks incl. the tape + marker runs as test | part-top-v2 | shared (station-trained) | `173234` |
| `each_cardboard_v4` / `bundle_m103` | per type incl. thin sockets and nut, per the log | part-top-v2 | **station only** | `185614`, `185846` |

Measured elsewhere today and still standing: per-view inference p50 CPU 6.4–6.7 ms, NPU 7.7, GPU 8.5 for the small
ResNet18 bundles; the event's reference PatchCore service is a different model (GPU f32, 31.7 ms p50).

## What the live sort runs showed

| EST | Run | Bundle | Result |
|---|---|---|---|
| 18:06 | `180637_sort` (laptop) | hexbolt_cardboard_v1 | Taped / marked bolts went to GOOD: scores 21.6, 21.7 under a threshold of 26.8; blue rule missed under the LED |
| 18:12 | `181214_sort` (laptop) | same, tape rule retuned | 3/3 correct; both rejects by the colour rule, model below threshold |
| 18:48 | `184840_sort` (laptop) | any_cardboard_v2 | 4 correct, 1 false reject (clean blue-zinc socket read as tape on the webcam), 1 dropped |
| 19:32 | `173234_sort` (station) | each_cardboard_v3 m103, type by best bank | 13 items: two taped parts to GOOD (wrong bank; no bank), 1 false upright, 1 not seen, 1 dropped |
| 20:25 | `182455_sort` (station) | each_cardboard_v3 m103 | no pick at all: stuck in WATCH. Not in the data |
| 20:56 | `185614_sort`, `185846_sort` (station) | each_cardboard_v4 m103, type by size | 6 decisions, truth not recorded: 3 tape rejects, 2 good, 1 upright-read nut rejected without a pick |

Across all six: 16 rejects (13 tape rule, 2 anomaly score, 1 upright skip), 12 good, 2 dropped, 2 no pick. On the
station (v3 / v4 `bundle_m103`: part-top-v2 crop, margin 1.03) the top-view model also flagged all 7 parts the tape rule
rejected; on the laptop (earlier bundles: square crop, margin 1.1) it flagged none of 6. Seen → first motion over the
32 logged rows: median 1.3 s, range 0.39–2.75 s.

## Problems to think through

Detection:

1. The scored case is a defect type we have not seen, and almost every live reject so far came from a rule that only
   knows blue tape. The anomaly model's live contribution is 2 rejects.
2. Thresholds. Ranking is good (AUROC 0.99–1.0 on 24 good vs 8 taped) but a threshold from the calibration goods
   rejected 2/24 to 7/24 held-out goods. Calibration sets are 2–10 picks of one specimen. Margin 1.03 was picked on
   the defect examples. There is no untouched audit set.
3. Type selection decides which bank scores a part. Best-fitting bank let two defects through. Size-based typing was
   95/101 leave-one-out on four types; it now has to separate seven, and has not been checked since.
4. `--decide top`: only the top view can reject on anomaly. A defect on the underside or far side is covered by the
   tape rule alone. The webcam banks rejected good parts when they were allowed to decide (front 1/7, yaw+35 3/7).
5. `each_cardboard_v4` was trained and put live within minutes, on data that includes the review-first captures.
6. Blue zinc reads as tape on the webcam (threshold raised to 4%); a nut with a blue ring is in the kit.

Picking:

7. `socket_thin_short` slips out after the grab (finger position 32 → 26 on lift). Only a head-targeted grasp at 1 mm
   clearance held it, from a script that is not `sort.py`.
8. `hex_nut` needed a metal-mask centre, jaws across the flats, retries at +30°, a shake to release it (it sticks to
   the fingers) and the hand gate off. Still 11 "not seen" and 3 "could not grasp" in 35 attempts.
9. `hex_bolt_short`: misses push the part 15–25 mm and scrape the pad. Cause not proven. Collect mode now makes one
   attempt and stops; sort mode still has to do something with a missed part.
10. Upright detection from depth is unreliable (lying bolts read 42–48 mm; one part read 20 and 80 mm). Upright grasp
    is off, so a part read as upright is not picked. In a judged run it stays on the table.
11. Three parts dropped while turning to the first webcam view. 34 "part not seen from hover", some in loops.

The loop:

12. WATCH can hang: one reference frame decided "hand present" for 2180 of 2181 frames. A fix is written in `sort.py`
    (`settled_ref`), **uncommitted and never run on the arm**. The nut runs avoided it by switching the gate off.
13. The judge log. Scoring wants item number, decision, **confidence**, timestamp. `decisions.jsonl` has no
    confidence value in any of its 282 rows (one row has the key, set to null).
14. Latency (seen → first motion) was 366–433 ms at 15:20. In the runs from 17:25 on the median is about 1 s, and
    1.3 s in the sort runs. Which change added the time has not been measured.
15. Stopping and ownership failed three ways: SIGINT ignored in WATCH (two loops connected at once), a pid file that
    held the wrong pid, and a second agent session queuing for the arm while a script still ran.

Housekeeping that will bite if left:

16. The scripts behind the thin-short and nut captures (`exp/one_grasp_head.py`, `nut_retries.py`, `nut_center.py`,
    `nut_relaunch`) and `each_cardboard_v4` exist only on the station.
17. The station pushes data with Ali's full-access HF token in `/root`. The repo is public.
18. `pranav/local-work` has two work commits that are not in `ali/pipeline`: grasp recovery (`6d13386`, 15:25) and
    motion_probe obstacles (`05c44fd`, 15:40).

## State right now

- **Arm:** released at the watch pose (200, 310, 330), all station loops stopped and verified at 21:00. Gripper state
  was not logged at the end.
- **Machine config changed today and still in effect:** wrist camera 1280×720 (fragment mod; backup
  `config/backup-cam1280-170454.json`), `overview-cam` MJPEG 1920×1080 (backup in `sorter/config_backups/` on Ali's
  laptop). Wrist brightness 8 / exposure 100 are v4l2 settings that do not survive a camera restart; `sort.py`
  re-applies them at run start. Workcell obstacles were still disabled in the Viam config at 19:17.
- **Station:** root cron pushes finished runs to HF every 10 minutes. Shared snapshot `265220ba`: 45 runs, 8 models.
  All 45 runs are now on Ali's laptop too.
- **Repo:** `ali/pipeline` = `origin/ali/pipeline` at `7eecb4c`, 39 commits ahead of `main`; Vedant's branch is merged
  in. Uncommitted: the `sort.py` hand-gate change, the 20:12–21:00 log entries, and this recap with the catalog
  (`catalog.py`, `catalog.html`, `docs/RUN_CATALOG.md`, `docs/run_notes.json`, `docs/DAY1_RECAP.md`). 57 unit tests
  and the 6 pipeline tests pass on the working tree (laptop, 22:50). Whether the station's `sort.py` has the hand-gate
  change is not recorded.
- **Tomorrow's clock:** resume 9:30, code freeze about 14:00, demos and judging 15:30.

## Docs that disagree with the evidence

- `README.md` status line says the loop has "not yet run with live motion" (written 12:15).
- `AGENTS.md`, hard-won facts: says `config/checkpoint.json` is stale since the webcam moved. The file's own comment
  and the 14:55 log entry say it was re-measured then (lens (−101, −206, 347)).
- `THRESHOLD_FINDINGS.md` calls `174637_collect` "1 good pick". Its decision row is "could not grasp"; it has no
  webcam images. It also points to branch `ali/live-dashboard`, which no longer exists on origin.
- `PLAN.md` ("private HF data still needs a team org") and the `sync_data.py` docstring still call the HF repo
  private. It is public.
- `CONTEXT.md` station table describes the wrist camera as 640×480 and the webcam as it was before 14:26.
