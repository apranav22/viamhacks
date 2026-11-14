[codex/unknown · op Ali (git: Ali, github: Armib20) · Mac.mynetworksettings.com · ali/judges-presentation · 2026-11-14]

# Judges presentation

A local React presentation in the Temple pitch's continuous-world style, using the actual Amphibian deck engine. Fourteen steps with a five-minute talk track, curated capture images, an original decision log, and separately labeled offline replay results. No robot connection, inference, model activation, or machine configuration changes.

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

## Evidence and edits

- Story and five-minute speaker notes: `src/deck.tsx`.
- Custom visuals: `src/blocks.tsx`; controls and source panel: `src/main.tsx`.
- Main subject: `runs/20261113_173234_sort/item_002`. Original reject reason is **tape**, even though its anomaly score also crossed threshold. A release timestamp does not independently verify the destination. The original row has no calibrated confidence field.
- Candidate examples: marker `20261113_171810_collect/item_004` and missed tape `20261113_173029_collect/item_001`. Both were originally **COLLECT**, with no anomaly model loaded; the deck explicitly labels later CPU replay results.
- Metrics: top-view candidate replay, automatic size routing, test picks only. Good: 32 clear, 2 flagged. Defects: 22 flagged, 5 clear misses, 1 unknown. The unknown is not counted as a successful anomaly detection. Known-type oracle metrics appear only in notes.
- Timing: 10.18 ms median / 13.02 ms p95 over 169 successful saved CPU calls; not an end-to-end or matched device benchmark. The main recorded item's first-motion latency is 2,672 ms.
- Training: 75 train, 34 calibration, 34 good test picks / six types. Repeated physical specimens mean these are development results, not independent-specimen accuracy or judge-set results. Candidate has not been activated.
- Event references supplied by Ali: Viam Overview p6 and reference sheet pp9–10. Both inform the story; their different rubric emphasis is noted in Sources.

Curated images live in `../site/img/judges-*.jpg`, as required by the repository's image policy. `src/evidence.json` pins their source hashes, transformations, original records and replay identity; `public/evidence.json` is the downloadable copy. `prepare_assets.py` can reproduce them from local runs using the existing `vh.anomaly.model_crop` routine:

```sh
../sorter/.venv/bin/python presentation/prepare_assets.py
```

Run that command from the repository root. It requires the source runs, analysis JSON and the two PDFs at their supplied Downloads paths. Rendering the already-prepared deck needs none of those inputs.

## Engine provenance

`vendor/deck/` comes from private `Amphibian-AI/amphibian-platform-v2`, `packages/deck/src`, commit `0a55bb06d4e05c0c5cd3e627d44cd29e88b36b3a` (trunk, retrieved 2026-11-14). Its `use-mount-effect` helper comes from the same commit. Only runtime modules were copied. No Pond/customer pitch content or email allowlists were imported.

Adaptations: local helper imports; Effect's single synchronous Result.try wrapper replaced with an equivalent native try/catch; dialog/control keyboard handling; responsive presenter previews and scrolling. Motion is pinned to the upstream version, 14.6.0. This small extraction avoids pulling the platform monorepo and its workspace dependencies into the robot project. Preserve this provenance when updating the engine.
