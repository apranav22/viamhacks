# Plan

## Decisions so far

| Decision | Why |
|---|---|
| An inspection move counts as the arm's "response" for latency | Team assumption; latency stops at the first move toward the item, before the model runs |
| Reject bin = hold area → two destinations: box, reject | Unsure items go to reject |
| Our script runs on the station | Laptop RPCs add 0.5–1.5 s per item |
| Picking is classical (camera → world pose → motion planner), no RL or demonstrations | See ARCHITECTURE |
| Survey pose = `home-pose` | Straight down, ≈50 × 68 cm view, 1.06 mm/px, verified |
| Pick every item; show its underside to a fixed camera | Tape can face the table (pending the camera test) |

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

1. May we move the `overview-cam` stand and put a white card behind a presentation spot?
2. How do items arrive, and what counts as "enters view"?
3. Is the log read from the station; is JSON lines fine; which timestamp do they use for latency?
4. Should the obstacles be enabled? The fragment's table is ~19 mm too low.

## Rules while sharing the machine

- **One driver at a time.** Say "I have the arm"; someone at the E-stop.
- **Config changes through C**, with a backup first.
- **AI agents and the Viam MCP server can move the arm.** Treat them like a person driving.
