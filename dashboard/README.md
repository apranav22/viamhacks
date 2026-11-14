# Run dashboard

[pi/unknown · op Ali (git: Ali, github: unknown) · Alis-MacBook-Air.local · ali/live-dashboard]

The server displays telemetry; it does not control motion. Camera tabs stay selected across run events. Inspection evidence remains in the strip and per-item progress records observed milestones. A decision or completed release sequence is not physical placement confirmation.

## Intel station

`deploy_station.py` now includes `dashboard/` in release archives. Deploy only a reviewed release: the deployment script also includes the current working copies of motion code and config. Do not deploy a dirty shared tree just to update this UI.

After approved deployment, run from the station release directory using its runtime:

```
cd /opt/viam/sorter-ali/current
/opt/viam/sorter-ali/.venv/bin/python3.12 -I dashboard/server.py --preview-during-run --run-preview-fps 1 --udp-host 127.0.0.1
```

Serve HTTP on loopback and use an approved SSH/Viam port forward for port 8765; open the forwarded `http://localhost:8765/` on the laptop. Alternatively `--host 0.0.0.0` exposes the unauthenticated dashboard to the trusted station network; do not expose it publicly.

For a separately authorized station sorting run, route telemetry with `--dash-host 127.0.0.1`. The existing `station_run.py` launcher currently forces the laptop address, so it must be adapted before using that launcher with a station-local dashboard. Starting this dashboard does not start a sorting run.

Run preview is opt-in, camera-only, defaults to 1 FPS per camera and is capped at 2 FPS. It skips detection, geometry and arm polling during active runs. It adds camera RPC load and needs station latency validation before judged runs. Without the flag, preview still pauses during runs; saved frames are explicitly timestamped and marked stale/snapshot rather than presented as continuous video.

## Offline checks (no robot)

```
python3 -m unittest discover -s tests -p test_dashboard_preview.py
node --test tests/test_dashboard_ui.cjs
python3 -I dashboard/server.py --no-preview --port 8875 --udp-host 127.0.0.1 --udp-port 8876 --record ''
```

Frontend HTML is read per request: reload the browser for UI changes. Backend options require a separately coordinated server restart. An isolated Intel deployment and laptop relay are now running; see `DEPLOYMENT.md` for actual ports, verification, and rollback. The instructions above describe a future consolidated deployment, not the isolated instance.
