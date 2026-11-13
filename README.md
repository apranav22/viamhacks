# viamhacks: Track 3, "Spot it, sort it"

Viam × Intel "Edge of Intelligence" hackathon, Nov 13–14 2026. Team of 4.

Cameras and an anomaly model find defective fasteners (the known defect: blue tape), the system decides, and a UFactory arm sorts each item into the **box** (good) or the **reject bin** (defective or unsure). Every model runs through OpenVINO on the station's Intel hardware.

| Doc | What's in it |
|---|---|
| [`docs/CONTEXT.md`](docs/CONTEXT.md) | The event, how we're scored, the station as measured, what Viam gives us |
| [`docs/PLAN.md`](docs/PLAN.md) | Decisions so far, who does what, timeline, open questions, rules for the shared machine |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | The pipeline: locate → inspect → pick → present → decide → place, and why |
| [`docs/NOTES.md`](docs/NOTES.md) | Running log of findings and failures (feeds the design explanation, 20% of the score) |

**Status (day 1, ~noon):** teleop works; arms at home. Pixel → world mapping verified on the live station; first part segmentation from the survey pose works. OpenVINO services not configured yet. No arm motion from our code yet.

**Existing code:** a starter pipeline (training, OpenVINO detector, decider, Viam robot wrapper, sorter loop, dashboard, preflight `doctor.py`) lives in Ali's `sorter` repo, tested offline and read-only against the station. To be merged here.
