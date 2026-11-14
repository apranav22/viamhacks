# Ops console + Stream Deck

The Stream Deck (model 20GBD9901, 15 keys) is plugged into the **venue laptop** (`alterschloss`). The ops console
runs on the **home PC** (`sticker`), which reaches the station through Viam. The laptop calls the console over
Tailscale at `http://100.104.1.88:8790`. Only tailnet devices can reach it. The console never binds 0.0.0.0.

The physical E-stop is the safety stop. The STOP key goes laptop → Tailscale → PC → Viam cloud → station and takes
about 3–6 s (`station_run.py stop`: SIGTERM, then SIGKILL after 5 s). It ends sort.py. It does not brake the arm mid-move.

## Run the console (home PC)

```bash
cd C:\Users\aayus\Projects\viamhacks-run\repo-ops
..\.venv\Scripts\python.exe ops\console.py --host 127.0.0.1 --host 100.104.1.88
```

Needs `api-key.json` next to `station.py` (gitignored). The page is at `http://100.104.1.88:8790/` from the laptop. It
shows RUNNING / NOT RUNNING, the station log, the newest run's decisions (judge log), both camera snapshots, health
and the device bench. Every press is logged to `logs/ops_console.log`. Start and stop also append `ARM: taken` /
`ARM: released` to `docs/AGENT_LOG.md`.

## Import the profile (laptop)

1. Install the Stream Deck app from elgato.com. Plug the deck in directly, not through a hub.
2. Copy `ops/streamdeck/Viam Ops.streamDeckProfile` to the laptop (`git pull` on this branch) and double-click it,
   or use Preferences → Profiles → Import.
3. Check one GET key (e.g. STOP): Website action, **"Access in background" / GET request in background** ticked.
   Open-in-browser keys (STATUS, SNAP, CONSOLE, BOARD, DASH, DECISIONS) have it unticked. If the import lands on the
   wrong device or comes in empty, rebuild by hand with the table below. Each key is a Website action with the URL shown.
4. Verify from the laptop without moving anything: press OPS CONSOLE, then STATUS, WEBCAM SNAP and WRIST SNAP.
   If the page does not load, check that the laptop shows `sticker` in Tailscale and that Windows Firewall on the PC
   allows python on port 8790 for the Tailscale network.

Regenerate after changing the URL or the layout:
`..\.venv\Scripts\python.exe ops\make_profile.py --console http://100.104.1.88:8790 --model 20GBD9901`

## Layout (5 × 3, see `streamdeck/preview.png`)

| | col 0 | col 1 | col 2 | col 3 | col 4 |
|---|---|---|---|---|---|
| row 0 | **STOP** (GET `/api/stop`) | ARM JUDGED CPU (GET `/api/arm?preset=judged`) | **CONFIRM START** (GET `/api/confirm`) | ARM JUDGED NPU (GET `/api/arm?preset=judged_npu`) | OPS CONSOLE (open `/`) |
| row 1 | ARM COLLECT m16 (GET `…preset=collect_socket_m16`) | ARM COLLECT hexbolt (GET `…preset=collect_hex_bolt_short`) | STATUS (open `/api/status`) | WEBCAM SNAP (open `/api/snapshot?cam=overview-cam`) | WRIST SNAP (open `/api/snapshot?cam=cam`) |
| row 2 | PREV SLIDE (hotkey ←) | NEXT SLIDE (hotkey →) | LIVE BOARD (open claude.ai artifact) | STATION DASH (open `http://172.16.0.182:8775`, venue LAN only) | DECISIONS (open `/api/decisions`) |

The slide keys send arrow keys to the focused window. Click the deck window once first. The deck runs on the laptop:
`cd presentation && npm run preview` → `http://127.0.0.1:5199`.

## Starting a run (two steps)

1. Press an **ARM** key. The console arms that preset for 5 s and the console page shows
   "ARMED … Person at the E-stop?".
2. Look at the E-stop. Someone's hand is on it. Press **CONFIRM START** within 5 s.
3. Before launching, the console checks (read-only) that no sort.py runs on the station and that the deployed
   `sort.py` knows every flag of the preset. Otherwise it refuses and the key shows the alert triangle.
4. It runs `station_run.py start -- <preset args> --dash-host 127.0.0.1` (telemetry to the station dashboard :8775).
   sort.py then checks teleop off and joints steady before it moves.

A late CONFIRM, a CONFIRM without ARM, or a second start while something runs → HTTP 409 (alert triangle), nothing starts.
STOP is always one press and also cancels a pending ARM.

## Presets (`ops/presets.json`)

| Preset | sort.py args (all also get `--dash-host 127.0.0.1`) |
|---|---|
| `judged` | `--mode sort --items 6 --background cardboard --type auto --anomaly-bundle models/each_cardboard_v4/bundle_m103.json --anomaly-device CPU --decide top --views coverage --watch-timeout 300` |
| `judged_npu` | same with `--anomaly-device NPU` |
| `judged_typeclf` | `judged` + `--type-clf models/type_clf_v1/type_clf.json`. **Refused today**: the deployed release (20261114_113843) has no `--type-clf`. Page only, no key. |
| `collect_socket_m16` / `collect_hex_bolt_short` | `--mode collect --background cardboard --label good --type <t> --reps 10 --views coverage --watch-timeout 300` |

Bundle `models/each_cardboard_v4/bundle_m103.json` is `dashboard/runner.py`'s default. Change presets only together
with the person running the arm.

## Fallback without the Stream Deck app

`ops/streamdeck/*.cmd` (stop, confirm, arm_*) each call one GET with `curl.exe`. Use them with the Stream Deck
"Open" action, or double-click them. The console page has the same buttons. Its CONFIRM needs the "Person at the
E-stop" box ticked.

## Stream Deck + on Pranav's Mac (8 keys, 4 dials)

Console runs on the same Mac: `python ops/console.py` (127.0.0.1:8790). Install the profile with
`python ops/make_profile_plus.py` (writes into the Stream Deck app's ProfilesV3 and restarts the app; pick "Viam Demo").

| | col 0 | col 1 | col 2 | col 3 |
|---|---|---|---|---|
| row 0 | **STOP** (`/api/stop_now`) | **DEMO 6 items** (`/api/go?preset=demo`) | **CONTINUOUS** (`…preset=continuous`) | **ONE OBJECT** (`…preset=one_object`) |
| row 1 | **COLLECT DEMO** (`…preset=collect_demo`) | OPS CONSOLE | **MULTI PART** (`…preset=multi`) | STATION DASH (LAN) |

Dial 0 turn: previous / next slide. `/api/go` starts at once on the console's open connection: no ARM/CONFIRM, no flag
preflight, no AGENT_LOG entry (operator's choice for the demo; the physical E-stop is the safety stop). Its only guard:
refused (409) while any sort.py runs on the station. `demo` = `demo.py start` settings (6 items); `continuous` = same, 999 items and a 1 h
wait for the next part (runs until STOP); `one_object` = same, 1 item; `multi` = same settings through `ops/multi/sort.py`
(several parts on the pad, one at a time; upload it to the station's `incoming/multi/sort.py`), ends 60 s after the pad empties; `collect_demo` = 3 picks,
sort.py's default label `unlabeled` / type `unknown`, so demo captures stay out of training.
