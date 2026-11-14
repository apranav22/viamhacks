# viamhacks: Track 3, "Spot it, sort it"

Viam × Intel "Edge of Intelligence" hackathon, Nov 13–14 2026. A judge places **one fastener at a time**; we look, pick it, check it from every side, and drop it in the **box** (good) or the **reject bin** (defective / unsure). Models run through OpenVINO on the station.

| Doc | What's in it |
|---|---|
| [`docs/CONTEXT.md`](docs/CONTEXT.md) | Event, scoring, the station as measured, what Viam gives us |
| [`docs/PLAN.md`](docs/PLAN.md) | Decisions, who does what, next steps, open questions |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | The cycle, grasp recipes, recovery levels, dashboard, code map |
| [`docs/NOTES.md`](docs/NOTES.md) | Findings and failures (feeds the design explanation) |
| `site/` | Visual overview: `python3 site/build.py && python3 -m http.server 8899 -d site` |

## Run it

```bash
pip install -r requirements.txt                 # numpy, scipy, pillow, viam-sdk (+ optional opencv-python-headless)
# api-key.json: {"address": ..., "api_key": ..., "api_key_id": ...}   (gitignored)

python dashboard/server.py                      # http://localhost:8765 (add --host 0.0.0.0 on the station)
python tests/test_pipeline.py                   # offline, ~3 s
python run.py pick --fake site/img/home_color.jpg --cycles 3   # whole cycle offline, no robot
python run.py watch                             # live cameras, never moves
python run.py pick                              # live cameras, DRY RUN: every move only logged
python run.py pick --live --step                # real motion, Enter before each move (bring-up)
```

**Status (day 1, ~12:15):** baseline cycle (watch → hover → look → pick → home) built and tested offline and in dry run; **not yet run with live motion**. Defect detection is next.


## Day-1 evening handoff

See `docs/THRESHOLD_FINDINGS.md` for the new captured data, threshold comparisons, false rejects, missed defects and safety incidents. Data access and station backup are documented in `docs/DATA_PLAN.md`. Earlier status sections are historical; the live Intel loop has now been exercised.
