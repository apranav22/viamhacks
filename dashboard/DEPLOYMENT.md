[codex/unknown · op Ali (git: Ali; github: unknown) · Mac.mynetworksettings.com · ali/judges-presentation · 2026-11-14]

# Intel web interfaces

Only two project web interfaces are now served on Intel:

| Interface | URL | Managed service |
|---|---|---|
| Dashboard: Live / History / Models | http://172.16.0.182:8765/ | `viamhacks-dashboard.service` |
| New judges presentation | http://172.16.0.182:8899/ | `viamhacks-presentation.service` |

Both services are enabled for reboot and run independently of `viam-agent.service`. No Viam restart is required for web updates. The previous 8770, 8771 and 8775 web interfaces were stopped; their ports were verified closed. The temporary teammate live/site tree and explorer/isolated dashboard trees were moved into the archive below. Old robot releases and CLI training tools were preserved.

## Release and data

- Web release: `/opt/viam/sorter-ali/web-releases/20261114_111617`.
- Dashboard working directory: `/opt/viam/sorter-ali/web-releases/20261114_111617/app`.
- Presentation files: `/opt/viam/sorter-ali/web-releases/20261114_111617/presentation` (fresh local TypeScript/Vite build).
- Pointers: `/opt/viam/sorter-ali/WEB_RELEASE`, `DASHBOARD_RELEASE`, `PRESENTATION_RELEASE`.
- Shared runs and models are symlinked into the dashboard. Models consumes imported `runs/_analysis/*.json`.
- 348 source-image hashes verified across the two imported model replays. One legacy v4 row has no hash and remains unverified; no hash was invented. Candidate counts remain 22 detected defects, 5 misses, 2 good rejects, 32 good passes, 1 unknown.
- Frozen replay preprocessing is copied from `releases/20261113_194153/vh/anomaly.py`, SHA256 `0b639397d582a6e0d8589e44ae5b735ad4d312364c6565a298f8cc4ef376dbdc`. Another session changed the live crop implementation during staging; using the frozen copy preserves honest reconstruction of these old evaluations without changing the robot runtime.
- Source hashes and preprocessing provenance: `/opt/viam/sorter-ali/web-releases/20261114_111617/deployment.json`.

## Live telemetry

Dashboard listens on UDP **8776** on Intel. The other operator session had moved the current collection to `--dash-host 127.0.0.1 --dash-port 8776`; the web service was aligned with that route without modifying its controller process. No laptop relay is needed. A non-run diagnostic packet verified the listener. At final verification no collection process remained, so this cutover did not exercise a new physical run.

For subsequent station runs, use `--dash-host 127.0.0.1 --dash-port 8776`. Run telemetry is recorded under shared `runs/<run>/dash`; idle preview is disabled to avoid extra camera/RPC work. Live images arrive from the running controller. Idle is not a claim that the arm is home; physical state was not queried.

## Archive and rollback

Archive: `/opt/viam/sorter-ali/web-archive/20261114_111617`.

`rollback.json` and `rollback-initial.json` retain old process commands, paths, pointers and cutover records. Archived UI trees:

- `legacy-live-and-site`
- `legacy-explorer`
- `legacy-isolated-dashboard`

`/opt/viam/sorter-ali/web-releases/20261114_111617/cutover.json` records the final service configuration. To roll back, first stop only the two web services, restore archived directories to their recorded original paths, then relaunch the recorded old web commands. Do not restart Viam, stop robot controllers, restore stale measured poses, or activate another model as part of a web rollback. The old release directories remain for provenance.

## Verification and scope

- Both HTTP services and Models' complete 62-pick benchmark API passed.
- Verified crop reconstruction on Intel.
- Headless browser loaded both LAN URLs, rendered model images/crops, advanced the presentation, and reported no JavaScript errors.
- Old web ports 8770/8771/8775 verified closed.
- New services enabled/active; Viam service remained active.
- Controller PID 834784 was identical before/after the successful web cutover. It subsequently ended outside this task; no arm/gripper, camera settings, machine config, robot release or model activation was changed by this deployment.
- A concurrent replacement on old port 8775 was detected and retired by command/cwd identity. PID-only assumptions were not used for final verification.

No runs, models, environments, training jobs, measured constants, or backup cron were deleted.
