# Claude as supervisor: quality monitoring handoff

[codex/unknown · op Vedant Desai (git: unknown, github: unknown) · local workstation · vedant/dashboard-progress · 2026-11-14 UTC]

Read and follow `AGENTS.md` before acting. Ask any agent receiving this handoff to follow it too.
Vedant requests implementation of the items below, visible on the actual station dashboards. This note is a
handoff, not evidence that the implementation is complete. No motion, camera changes, threshold changes, model
activation, or cloud upload is authorized by this note. Existing arm ownership rules still apply.

## Claude's role: Vedant's clarification

Claude is the teacher in the operational sense: it supervises the whole project, watches training/evaluation,
uses known defect/nondefect labels to recognize mistakes, diagnoses causes and directs the next improvement.
There need not be a distillation loss. Claude may also propose labels by inspecting images, with label provenance
and uncertainty retained. Use known labels when available; distinguish visual proposals from verified labels.
Defect labels can support a separate supervised student/head; do not insert defects into PatchCore's normal bank.
Hold out entire defect families and independent physical parts to measure OOD behavior after development.

## Available monitoring tool and consumer contract

`python monitor_quality.py --root /opt/viam/sorter-ali --watch` reads saved bundle test results and registered jobs,
refreshes `quality/latest.json` every 15 seconds and prints changed evidence to stdout. It computes anomaly-only
whole-pick TP/TN/FP/FN, excluding unknown labels, missing views, invalid scores and train/calibration overlap.
It uses recorded dataset labels; independent human verification is not established. No GPU or robot connection.
`train_dashboard.py` adds `/api/quality` and `/supervision` with clickable counts and links to images.
These source changes need deployment before those routes exist on the station.

The supervisor Claude instance runs on **another machine**, per Vedant; do not confuse a station Claude process
with that supervisor. Fetch and integrate `origin/vedant/dashboard-progress` in your own checkout, following
`AGENTS.md`; do not push to someone else's branch. Read this handoff immediately after pulling.

To the active Claude orchestrator: read/pull this branch in your own checkout. Start the monitor in an isolated
checkout; retain and poll its background output using your supported job mechanism. After each candidate job,
and periodically while jobs run, consume the fresh report and inspect FN/FP images. Write an identity-stamped
supervisor record with model/data fingerprints, metrics, absent labels, diagnosis, one proposed intervention and
the next evaluation. Add a separate consumer heartbeat/acknowledgment with your identity and last processed
report hash. Show stale acknowledgment as **supervisor not observing**. Do not infer consumption from file existence.
No automatic activation, frozen-test tuning or hardware commands. Report "not measurable" when labels are absent.
Codex has NOT started or verified this consuming Claude loop. It is a pending handoff, not an active supervisor.

## The gap

`sort.py` catches operational failures and rejects missing/invalid inference views, but a visually defective part
with all scores below threshold can be accepted without knowing it was a false negative. Saved decisions and
scores are not ground truth. A running Claude process, dashboard refresh, or ten-minute data-sync cron is not proof
that any agent continuously checks prediction quality. Do not represent any of those as an accuracy monitor.

## Requested implementation

1. Persist an append-only review/audit record per `run/item`, separate from original images, collection metadata,
   decisions and model bundles. Include actual label (`good`, `defective`, `unknown`, `unusable`), defect type,
   physical-part ID if known, reviewer/source, timestamp, evidence views and optional explanation. Corrections must
   retain history. Never infer a ground-truth label from the detector's decision or anomaly score.
2. A stronger vision model/Claude can inspect saved images and propose teacher labels and defect locations. Record
   model/version, prompt version, confidence/abstention and evidence. Keep proposals separate from human-confirmed
   labels. Occluded surfaces and uncertain imagery must be unknown; teacher agreement is not true accuracy.
   Do not silently send station images to a cloud API: get Vedant's destination/model/data approval first.
3. Continuously join new completed picks with reviewed labels, decisions and model identity. Persist heartbeat,
   last processed pick/time, failures and a machine-readable quality summary for Claude/orchestrator. Explicitly
   show idle, disconnected, stalled, unknown and active states. Watching files must not command hardware or
   compete with judged sorting for accelerator resources. Clarify which agent actually consumes the summary;
   do not claim automatic notification merely because a JSON file exists.
4. Display per-pick TP/TN/FP/FN with **defective = positive**: defective/reject TP; good/accept TN;
   good/reject FP; defective/accept FN. Show accuracy, precision, recall, specificity and denominators;
   undefined metrics must be N/A. Unreviewed predictions cannot contribute to verified accuracy. Separate
   teacher-agreement metrics, operator collection-label metrics and human-confirmed evaluation metrics.
   Keep dropped/skipped/incomplete/unlabeled picks outside binary confusion counts, visible in separate counts.
   Distinguish explicit defect detection from rejection solely for missing models/views or invalid inference.
5. Make each confusion-matrix cell clickable to inspect those exact picks in the explorer. Miss queue must show
   all views, available heatmaps, score/threshold ratios, decision reason, model fingerprint, label source and
   review controls. Classify suspected causes as invisible/occluded defect, bad crop/quality/domain shift,
   low anomaly sensitivity, or threshold/fusion; present causes as hypotheses until verified.
6. Training dashboard: show current process/job, model, data snapshot/splits, device, start time, elapsed time,
   actual stage, completed/total groups if available, logs, exit/failure state, test counts and recent changes.
   Do not invent percentages, epochs or loss curves for PatchCore. Show frozen feature extraction -> coreset ->
   export -> normal calibration -> held-out evaluation -> device benchmark, with unknown progress if uninstrumented.
7. Project dashboard: add an architecture view (optional animation, with pause/reduced-motion support) showing
   wrist/webcam -> localization/grasp -> multi-view capture -> shared crop preprocessing -> PatchCore/OpenVINO ->
   per-view scores -> conservative fusion -> accept/reject, with telemetry/storage to dashboards. Show the separate
   normal-only fit/calibration lane and teacher proposal -> human review -> failure queue -> candidate improvement
   -> frozen evaluation lane. Differentiate implemented components from planned ones and live state from animation.

## Teacher/student and learning from misses

Current `train_anomaly.py` freezes ResNet-18, uses `torch.no_grad()`, builds a PatchCore memory bank and calibrates
thresholds from normal picks. There is no gradient loss or teacher/student optimizer in this implementation.
**Never insert defective examples into the normal bank** or reuse reviewed test errors to tune thresholds while
still calling that same test set held out.

Human-confirmed misses can drive preprocessing/coverage experiments and a separate development set. If implementing
a defect-aware student/head, use explicitly approved teacher/human training labels, a specified supervised objective
(e.g. binary classification; localization only when suitable annotations exist), and an independent frozen test set.
Compare candidate and current models at the whole-pick level before activation. Do not promise that distilling an
imperfect teacher resolves unseen defects. Keep at least one defect family and independent physical parts untouched
for final evaluation; repeated views of the same fastener are not independent physical objects.

## Deployment and coordination

Code branches do **not** automatically share updates. This note is pushed on `vedant/dashboard-progress`; its shared
station copy is intended to be readable regardless of checkout. Receiving agents must explicitly read it and pull,
cherry-pick or integrate reviewed changes. Do not switch teammates' branches or restart their sessions.

Existing explorer: http://172.16.0.182:8771/explore (our isolated deployment; actual shared station runs/models).
Existing training: http://172.16.0.182:8770/. Existing project link: http://172.16.0.182:8899/#progress (recheck service).
The explorer is deployed from commit 896d886. Later architecture/review features were requested but have not yet
been implemented. Preserve other dashboards, immutable release directories, collection and running jobs.

Acceptance: a reviewed defective pick predicted good appears as FN with its actual images; a reviewed good reject
appears as FP; unknown/dropped/incomplete picks stay separate; teacher proposals never count as confirmed truth;
new completed labeled picks update the monitor without manual replay; model/data versions and heartbeat are visible;
training stages reflect evidence, and robot/model activation stays unchanged.

Done: source/runtime inspection and this handoff; explorer deployed previously. Not done: review/quality loop,
training-stage instrumentation, architecture animation, or verified OOD accuracy improvement at the first handoff.
Subsequent update: `monitor_quality.py`, `/api/quality` and `/supervision` are implemented and tested in source,
including per-pick confusion counts and log-derived job stages. They are not yet deployed on the station.
Human review storage, live sorting ground-truth joins, consumer acknowledgment, architecture animation and
the running remote Claude supervision loop remain pending. Do not present source delivery as an active loop.
Robot: no motion/config/gripper changes. Next: implement review storage and the verified per-pick confusion matrix.
