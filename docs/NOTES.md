# Notes: findings and failures

One line per surprise, newest last. This is raw material for "what failed, what we'd change" in the design explanation.

## Day 1

- **Teleop: both arms "drooped" on start.**
  - `leader_hold: manual` makes the SO-101 leader limp; unheld, it fell, and the follower copied the fall ×2.5.
  - It stopped on a self-collision (arm base vs claws).
  - Fix: hold the leader the whole time, `stop` before letting go.
- **Teleop config pointed at `vacuum-gripper`** (disabled); the station's gripper is `gripper`.
- **The leader logged a servo voltage error and serial timeouts once:** power or cable?
- **The arm is an xArm850, not the xArm6 from the slides.**
- **Table/wall/ceiling obstacles are disabled by our fragment mods, and the table box sits ~19 mm too low** (real surface z ≈ −4 mm).
- **Pixel → world verified:** 31 table points at an angle map to z = −4 ± 5 mm.
- **Home looks straight down from ~64 cm:** ≈50 × 68 cm at 1.06 mm/px. Good for finding parts, too coarse for tape.
- **First segmentation from home:** zinc parts found; stainless parts partly missed; touching parts merge; the gripper finger is always in the bottom-right corner.
- **Laptop → station:** RPCs 85–230 ms, a color+depth frame 1.1–1.3 s, color-only 15–85 ms. Run on the station.
- **Depth at 17 cm is at the D435's limit** (67% valid). A bolt still reads ~12 mm above the table.
- **The machine API key lists the org's datasets but can't download images;** use `viam dataset export` from a logged-in account.
- **Tape can face the table** → pick everything and present the underside to a fixed camera.
- **`overview-cam` is too far and has a busy background for that as placed** → move it closer to a presentation spot (asking staff).
- **From last night's prep (MacBook, offline):**
  - PatchCore coreset 0.01 matches 0.1 in accuracy at a third of the latency.
  - GPU/NPU f16 shifts scores by up to 0.1, so calibrate on the deploy device.
  - OpenVINO's CPU cache ignores the precision hint.
  - A 1B VLM answers from the prompt, not the image; a 4B VLM gets 5/8 and is slow. The VLM explains, it doesn't detect.
