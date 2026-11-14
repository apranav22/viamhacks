[codex/unknown · op Ali (git: Ali, github: Armib20) · Mac.mynetworksettings.com · ali/judges-presentation · 2026-11-14]

# Judges presentation

A local React presentation in the Temple pitch's continuous-world style, using the actual Amphibian deck engine. Thirteen main steps with a five-minute talk track, plus backup steps, curated capture images, an original decision log, and separately labeled offline replay results. No robot connection, inference, model activation, or machine configuration changes.

## Present

Node 22.12 or newer is required. From this folder:

```sh
npm ci
npm run dev
```

Open http://127.0.0.1:5199. Arrow keys, Space, or a stage click advance; the left quarter goes back. `N` opens notes, `G` selects a step, and `F` toggles fullscreen. The bottom controls offer the same actions. Open **Presenter** in a second window of the same browser profile for synchronized previews, notes and elapsed time. Browser storage partitions/private windows do not synchronize with each other. The audience window's **Sources** panel includes the complete provenance manifest.

On this Mac, an older Node may be ahead of Homebrew's Node in npm's executable search path. Use:

```sh
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
npm run dev
```

## Build / take offline

```sh
npm run build
python3 -m http.server 5199 --bind 127.0.0.1 --directory dist
```

The built `dist/` folder is self-contained; copy it to another machine and serve it with any static HTTP server. It has no CDN fonts, external runtime requests, API keys or dependencies on the live dashboard. Relative asset URLs support hosting under a subdirectory. Opening `index.html` directly with `file://` is not supported by browser ES-module rules.

`npm run package` builds `judges-presentation.zip`, including plain-text offline instructions. Unzip it on the presentation machine and serve it with Python; Node/npm is unnecessary there.

## Content (restructured 2026-11-14 around the judging rubric)

[claude-code/claude-fable-5-2 · op Ali (git: Ali) · Alis-MacBook-Air.local · ali/judges-presentation · 2026-11-14]

The design explanation is scored on what it does, why each choice, what failed, what we'd change (docs/CONTEXT.md), plus
device placement with a measured reason. The deck follows that order: 13 main steps (~5 min, talk track in the notes, `N`)
and a backup chapter for questions.

| Chapter | Steps |
|---|---|
| What it does | title · the six-stage cycle · six views (wrist top + oblique ±45°, webcam under + end A/B) with real images |
| Why each choice | anomaly model (colour rule vs model, backbone, type before scoring) · decision after every capture · device placement (CPU/GPU/NPU measured) · motion (joint moves, collision check, per-move speed) · poses and calibration · latency and recovery |
| What failed | the day-1 live record (13/16 rejects from the colour rule, two escapes, two E-stops) · what each failure changed |
| What we'd change | four concrete items · the decision-log row |
| Backup | model results · six calibration phases · webcam calibration · grasp checks |

### Before presenting (day-2 numbers)

```sh
# from the repo root, after the judged run and the evaluation of the new banks
python3 presentation/set_row.py runs/<run>/decisions.jsonl --item 3        # real log row on the last slide
python3 presentation/set_row.py --eval good_passed=.. good_total=.. defects_flagged=.. defects_total=.. note="..."
python3 presentation/set_row.py --device CPU                               # device the run used
../sorter/.venv/bin/python presentation/prepare_pipeline_assets.py --pick runs/<run>/item_NNN   # one pick with all six views
cd presentation && npm run package                                         # rebuilds dist/ and judges-presentation.zip
```

Empty fields in `src/today.json` fall back to day-1 figures, labelled as day 1. Check these slides against what actually ran:
"6 / 6 captures scored" (needs a bank for every view), the device slide (says CPU), and "What we'd change" (move the type
classifier / confidence card out if they shipped before the run).

On the Intel station no Node is needed: copy `judges-presentation.zip`, unzip, `python3 -m http.server 5199 --directory <dir>`.

Files: story and notes `src/deck.tsx`; visual blocks `src/blocks.tsx`; styles `src/style.css`; Sources panel `src/main.tsx`.

## Engine provenance

`vendor/deck/` comes from private `Amphibian-AI/amphibian-platform-v2`, `packages/deck/src`, commit `0a55bb06d4e05c0c5cd3e627d44cd29e88b36b3a` (trunk, retrieved 2026-11-14). Its `use-mount-effect` helper comes from the same commit. Only runtime modules were copied. No Pond/customer pitch content or email allowlists were imported.

Adaptations: local helper imports; Effect's single synchronous Result.try wrapper replaced with an equivalent native try/catch; dialog/control keyboard handling; responsive presenter previews and scrolling. Motion is pinned to the upstream version, 14.6.0. This small extraction avoids pulling the platform monorepo and its workspace dependencies into the robot project. Preserve this provenance when updating the engine.
