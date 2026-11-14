# AGENTS.md: rules for every AI agent (and human) in this repo

This repo drives a **real robot arm shared by a team of four and several AI agents** (Viam × Intel hackathon, Track 3).
Read this before you change code, config, or the machine. If you are an AI agent: follow it, and whenever you hand off to,
review, or build on another agent's work, **point that agent to this file and ask it to follow the same rules**.

Tool-specific files (`CLAUDE.md`, etc.) only point here. This file is the single source of rules.

## 1. Identify yourself, every time

Every commit, note, log entry, PR/PR comment, and handoff written by an agent carries an identity block. The identity
comes from **where you actually run**: the tool and model you are, and the human account that launched you (git
`user.name`, GitHub login). Never borrow another operator's identity. If you don't know a field, write `unknown`.

```
agent:    <tool>/<model-id>        e.g. claude-code/claude-opus-5-5, codex/<model>, cursor/<model>
operator: <human> (git: <user.name>, github: <login or unknown>)
host:     <machine the agent runs on>   e.g. ali-macbook, station armfarm04b
branch:   <branch you are on>
```

**Commits** carry it as trailers (humans committing by hand don't need them):

```
git commit -m "Short summary" \
  --trailer "Agent: claude-code/claude-opus-5-5" \
  --trailer "Operator: Ali (git: Ali)" \
  --trailer "Host: ali-macbook"
```

**Notes and logs** (`docs/AGENT_LOG.md`, `docs/NOTES.md`, PR text) start with the one-line form:
`[claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline · 14:40]`.

If you find work with no identity block, treat its origin as unverified: ask your operator, and leave a note (PR comment
or `docs/AGENT_LOG.md`) asking that agent to adopt this template.

## 2. The robot is shared: one driver at a time

- **Default is read-only / dry run.** Reading cameras, joints, gripper state, teleop status: fine any time (keep it
  light; the dashboard preview may already be polling). **Any motion, gripper command, or `DoCommand` that actuates needs
  your operator's go-ahead in the current session.**
- **Before moving:** teleop `{"command":"status"}` shows `running: false`; arm joints unchanged over ~1 s (nobody else
  driving); your operator confirms a human is at the E-stop. Then append `ARM: taken by <identity>` to
  `docs/AGENT_LOG.md`, and `ARM: released` when done (arm at home, gripper open).
- **Planned moves** (`motion.move`) pass the obstacles: table, walls, ceiling, **webcam tripod, lamp, cardboard box**.
- **Never** change arm speed/acceleration, collision sensitivity, or safety settings.
- On any error during motion: `arm.stop()`, report, don't retry blindly.

## 3. Machine config (Viam app)

Only with operator go-ahead. Back up the **whole** part config first (`config/backup-<HHMMSS>.json`, gitignored),
change only the attributes you need, record before → after in `docs/AGENT_LOG.md`, and say how to revert.

## 4. Secrets

Never commit or paste: `api-key.json`, `.env`, the machine's `viam.json`, part secrets, API keys. Run
`git diff --cached` before every commit. Both files are gitignored; keep it that way.

## 5. Git

- Work on your own branch `<operator>/<topic>`. Never push to someone else's branch, never force-push shared branches,
  never rewrite history others have pulled. `main` changes by team agreement / PR.
- `git fetch` before starting; read what teammates pushed since your last session before duplicating it.
- Don't commit `runs/`, `logs/`, or raw images, except curated figures under `site/img/`.

## 6. Measured constants: change only with a new measurement

Source of truth: `config/poses.json` (grasp, table, scan pose) and `config/checkpoint.json` (webcam, capture views).
Every value there came from a measurement on the arm. Change one only with a new measurement, and write the date, the
method, and your identity into its `_comment` field. **Never tune by guessing.**

Hard-won facts (each cost us an hour; don't relearn them):

| Fact | Value |
|---|---|
| Fingers close along the gripper's **y** axis | `jaw_offset_deg` **0** (90 grips a screw end to end) |
| Closed fingertips past the gripper TCP | **20.5 mm** (open ≈ 13 mm; tips drop up to ~25 mm as the jaws close) |
| Table top | z **−1.3 mm**; a depth scan's median swings ±3 mm and once read +3.6 |
| `gripper.grab()` returns before the jaws settle | read `pos` again after it stops changing; ~0–15 = closed on nothing |
| `anomaly` vision service, anomalib 0.1.5 | `capture_all_from_camera` crashes viam-server; use separate calls |
| `overview-cam` (the webcam) | no depth; MJPEG 1920×1080 since 14:26 (backup `config_backups/before_cam1080_142629.json` on Ali's laptop) |
| Webcam position | **moved ~14:30** to a tripod, lens ≈ (−125, −230, ~300) mm from wrist depth; `config/checkpoint.json` lens + capture views are **stale** until re-measured |
| Laptop → station latency | RPC 85–230 ms, color+depth frame 0.3–1.3 s. Judged runs execute on the station |

## 7. How to work with the humans and the other agents

- **Change one variable at a time** on the arm and say which. Don't swap in your own fork of the pick pipeline while
  someone is debugging the shared one; run theirs unchanged first.
- Report outcomes as they are: failed runs, skipped steps, untested code ("dry run only") are stated plainly.
- Prefer extending the existing code (`pipeline.py`, `motion_probe.py`, `vh/`, `dashboard/`) over parallel rewrites.
  Check `docs/AGENT_LOG.md` for who is doing what.

## 8. Handoff template (end of a session, or when passing work on)

```
[identity one-liner]
Done:      what changed (files, commits), what was verified and how
Not done:  what's untested / half-built
Robot:     arm state (home? gripper?), any config changed + how to revert
Next:      the single most useful next step
```

## 9. Map

| Path | What |
|---|---|
| `docs/CONTEXT.md` · `PLAN.md` · `ARCHITECTURE.md` · `NOTES.md` | event + scoring, decisions, design, findings |
| `docs/DATA_PLAN.md` | part classes, data splits, holdout defects |
| `sync_data.py` | share runs/ and models/ with the team (public HF dataset; read access needs no login): `status` · `pull` · `push` (DATA_PLAN.md, end) |
| `docs/AGENT_LOG.md` | who is doing what, arm taken/released, config changes |
| `docs/DAY1_RECAP.md` · `RUN_CATALOG.md` | day-1 recap; every run with part, label, counts, flag and note |
| `catalog.py` | rebuilds the catalog: `python3 catalog.py` then `open runs/index.html` (all images + metadata per pick); notes in `docs/run_notes.json` |
| `pipeline.py`, `motion_probe.py`, `overview.py` (Pranav) | scan, grasp, motion primitives, present views |
| `vh/`, `run.py` (Ali) | perception, geometry, telemetry; baseline cycle |
| `dashboard/server.py` | live dashboard (UDP telemetry, idle camera preview) on :8765 |
| `config/` | measured poses, checkpoint, Viam config tooling |
| `site/` | visual overview (`python3 site/build.py`) |


## Offline calibration handoff

`compare_anomaly.py`: `score` → `specimens` (human-reviewed identity/role template) → `report`.
Read `docs/ANOMALY_CALIBRATION.md` first. No live activation. Never invent physical specimen identities or call
repeated grasps independent samples. The good-reject budget is explicit; insufficient calibration stays uncertain.

## Day-1 evening handoff

See `docs/THRESHOLD_FINDINGS.md` for the new captured data, threshold comparisons, false rejects, missed defects and safety incidents. Data access and station backup are documented in `docs/DATA_PLAN.md`. Earlier status sections are historical; the live Intel loop has now been exercised.
