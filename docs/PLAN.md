# Plan

## Decisions so far

| Decision | Why |
|---|---|
| An inspection move counts as the arm's "response" for latency | Team assumption; latency stops at the first move toward the item, before the model runs |
| Reject bin = hold area → two destinations: box, reject | Unsure items go to reject |
| Our script runs on the station | Laptop RPCs add 0.5–1.5 s per item |
| Picking is classical (camera → world pose → motion planner), no RL or demonstrations | See ARCHITECTURE |
| Survey pose = `home-pose` | Straight down, ≈50 × 68 cm view, 1.06 mm/px, verified |
| Pick every item; check it at a checkpoint in front of the fixed camera on the way to the bins | Tape can face the table |
| One item at a time; the judge may move it | Staff info; recovery L1/L2 built, L3 next |
| Grasp by shape class (upright, lying, thin screw, nut flat/edge, washer, unknown) from the hover look | Different fasteners need different grasps; depth tells an upright bolt from a nut |
| Live dashboard via fire-and-forget UDP, separate process | Measured 23–74 µs per event on the loop |

## Status / next (day 1 evening)

- **Built and exercised live:** `sort.py` collection and sorting on the Intel station, shared runs/models across releases, per-type OpenVINO anomaly banks, measured-size auto type, multi-view capture, dashboards and HF backup. Upright grasp remains unvalidated and off by default.
- **Read first:** `THRESHOLD_FINDINGS.md` for the new defect runs, threshold experiments, misses, false rejects and safety incidents; `AGENT_LOG.md` for chronological evidence; `DATA_PLAN.md` for data access.
- **Next:** curate the latest captures, freeze independent calibration/audit data, verify thin-socket coverage and size-based typing, rehearse safely. Teammate access to private HF data still needs a team org.
- The ownership table below is the original bring-up allocation, not a claim that these tasks remain undone.

## Who does what

| Person | Owns | Next |
|---|---|---|
| **A: Perception and model** | Data, training, thresholds, unseen defects | Export the `fastener-anomaly` dataset; canonical-crop code shared by training and runtime; capture good close-ups at the inspect height; train the top-view model; then the presentation-view model from arm-collected data |
| **B: Motion and grasping** | Obstacles, poses, picking, presenting, recovery | Re-enable the table obstacle (z ≈ −4); theta test; hover test; grasp each part type; teach box / reject / presentation poses |
| **C: On-device and diagnostics** | Viam services, device placement, presentation camera | `ov-diag` → `list_devices`; `ov-anomaly` (GPU f32) with `fastener-patchcore`; benchmark CPU/GPU/NPU; test `overview-cam` focus and resolution at 20–40 cm |
| **D: Integration, decisions, story** | The loop, the judge log, dashboard, pitch | Judge log with ms timestamps; wire SURVEY → INSPECT → PICK → PRESENT → DECIDE → PLACE with motion dry-run; NOTES.md; draft the design explanation |

**Interfaces:**
- **A → C:** model packages and thresholds.
- **C → D:** service names and returned fields.
- **B → D:** `locate()`, `inspect(obj)`, `pick(obj)`, `present()`, `place(dest)`, each failing with clear errors.

## Timeline

- **13:00:** first scores from `fastener-patchcore` on our camera; table obstacle on; hover test done; presentation camera tested; open questions answered.
- **18:00:** own top-view model; fixed-position pick → present → place on real parts; diagnostics numbers.
- **21:00:** presentation model; recovery; the loop running on the station; ≥5 five-minute rehearsals with a teammate playing judge (moves items, adds a new defect).
- **Day 2:** hardening and rehearsals until a **~14:00 code freeze**, then the design explanation and numbers for 15:30.

## Open questions for staff

1. May we move the `overview-cam` stand to aim at our checkpoint?
1. Are washers in the judge set? (not graspable top-down with the claw)
1. How is recovery scored?
2. How do items arrive, and what counts as "enters view"?
3. Is the log read from the station; is JSON lines fine; which timestamp do they use for latency?
4. Should the obstacles be enabled? The fragment's table is ~19 mm too low.

## Rules while sharing the machine

- **One driver at a time.** Say "I have the arm"; someone at the E-stop.
- **Config changes through C**, with a backup first.
- **AI agents and the Viam MCP server can move the arm.** Treat them like a person driving.
