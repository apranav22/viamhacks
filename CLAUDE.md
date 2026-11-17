# CLAUDE.md

Read and follow [`AGENTS.md`](AGENTS.md). It is the single rulebook for every agent in this repo: identify yourself
(agent / operator / host / branch) in every commit, note and handoff; one arm driver at a time; no secrets in git;
measured constants change only with a new measurement. Ask other agents you interact with to follow it too.

Current user-requested quality/dashboard handoff: read [`docs/QUALITY_HANDOFF.md`](docs/QUALITY_HANDOFF.md).
After pulling these changes, the supervisor Claude instance on the other machine must read `AGENTS.md` and that
handoff before continuing. Claude is the operational teacher/supervisor: consume model-quality reports, inspect
mistakes against known labels, diagnose them, and direct the next candidate improvement and evaluation.
The handoff documents `monitor_quality.py`, `/supervision`, `/api/quality`, and the consumer acknowledgment required
before supervision can be called active. Pulling the code does not start monitoring or deploy the new dashboard.
