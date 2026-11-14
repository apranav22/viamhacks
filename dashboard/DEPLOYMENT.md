# Active dashboard deployment

[pi/unknown · op Ali (git: Ali, github: unknown) · Alis-MacBook-Air.local · ali/live-dashboard · 2026-11-13 19:38]

Operator authorized getting the dashboard running. Dashboard only deployed; no motion/config deployment and no arm/gripper actuation.

- Intel release: `/opt/viam/sorter-ali/dashboard-releases/20261113_193740`
- Release pointer: `/opt/viam/sorter-ali/DASHBOARD_RELEASE`
- HTTP: `http://172.16.0.182:8775/`; UDP telemetry: 8776.
- Runtime: `/opt/viam/sorter-ali/.venv/bin/python3.12`.
- Options: `--host 0.0.0.0 --port 8775 --udp-port 8776 --preview-during-run --preview-fps 1 --run-preview-fps 1`.
- `dashboard.pid` and `dashboard.log` are in the Intel dashboard release.
- `vh` and credentials symlink to existing release `20261113_192017`; runs symlink to shared `/opt/viam/sorter-ali/runs`. No secrets uploaded.
- Existing teammate dashboard on station 8765/8766 was left untouched.
- Replaced laptop dashboard PID 97728 with `python3.11 -I -u dashboard/relay.py --station 172.16.0.182` (PID 17995 at deployment). Relay log: `/tmp/sorter-dashboard-relay.log`.
- `http://localhost:8765/` redirects to Intel. Laptop UDP 8766 forwards unchanged to Intel UDP 8776, preserving the existing station launcher's laptop telemetry destination.

Verified both Intel camera image endpoints (wrist and overview), browser live frame ages below one second, no browser errors, HTTP redirect, and UDP relay packet-count increase. No new sorting run started; active-motion latency remains unverified. Processes are detached, not reboot-persistent services. HTTP is unauthenticated on the trusted station LAN; do not expose publicly.

Rollback: verify the command line of each PID before stopping it. Stop the Intel dashboard using its release `dashboard.pid`, and stop the laptop relay. Restore the laptop server from the repository with the previous command `python -I dashboard/server.py` using the sorter virtualenv Python. This does not require changing or restarting any robot process. Do not stop the teammate dashboard on Intel port 8765.
