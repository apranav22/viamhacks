# Intel station deployment

[pi/unknown · op Ali · ali/pipeline]

## Verified target and isolation

`armfarm04b`, Ubuntu 24.04.4, Python 3.12.3:

- CPU: Intel Core Ultra X7 358H.
- GPU: Intel Arc B390 iGPU; OpenVINO executes on **GPU.0**, PyTorch tensors/features on **xpu:0**.
- NPU: Intel AI Boost exposed; this bundle has not been benchmarked on it.

Own directory: `/opt/viam/sorter-ali/`.
Runtime environment: `.venv/` (OpenVINO 2026.4.1 + Viam SDK 0.85.2; no torch).
Training environment: `.train-venv/` (torch 2.15.0+xpu, torchvision 0.29.2+xpu, anomalib 2.7.0 + OpenVINO).
Code/models/data: `releases/20261113_1647/`; `ACTIVE_RELEASE` records the directory.

No apt packages, GPU drivers, shared Viam config, reference model service or arm settings were changed. The preexisting
`ov-anomaly` service remains loaded with the event reference model on GPU FP32; it is NOT our new bank.
No arm/gripper commands were used for deployment, training, benchmark or camera connectivity tests.

## What ran where

- Original `models/button_white_v1/` bundle was fitted on the Mac, then copied and scored on Intel CPU/GPU.
- New `models/button_xpu_v2/` was fitted ON THE INTEL MACHINE: all five groups recorded `feature_device: xpu:0`,
  `coreset_device: cpu`, `export_device: cpu`; training exited 0.
- PatchCore is frozen feature extraction + memory-bank fitting, not gradient-training epochs. The heavy neural
  feature extraction can use XPU; bank selection and graph export deliberately stay on CPU.
- Live camera reads from the Intel runtime worked: wrist 640x480 (~8.7 ms RPC in one sample), webcam 1920x1080
  (~39.9 ms). This was read-only connectivity, not a live sorting run or calibrated live anomaly evaluation.
- The Mac dashboard can replay ACTUAL Intel GPU scores/maps from the verified report. It labels this saved-frame
  replay with `armfarm04b GPU`; it does not call the Mac's model runtime in remote-report mode.

## Measured inference (not assumed)

Original five-model ResNet18 bundle, 10 held-out view images, 10 repeats each; float32, after model warmup:

| Device | p50 (preprocess + infer) | p90 | Actual execution |
|---|---:|---:|---|
| CPU | 6.30 ms | 6.87 ms | CPU |
| GPU | 8.51 ms | 9.24 ms | GPU.0 |

GPU/CPU maximum score difference 0.0000182; 100% agreement with EACH OTHER on those threshold decisions.
That is not 100% ground-truth accuracy: the original wrist model still has a false reject on a clean held-out pick.
CPU is slightly faster for this tiny batch-1 model under the measured load. Do not assume GPU wins every model;
use measured device placement, and avoid overlapping training with a judged inference run.

Reports on station: `releases/20261113_1647/device_report.json`, `xpu_train_v2.log`, `xpu_train_v2.exit`.
Local report: `models/button_white_v1/intel_device_report.json` (models/runs remain gitignored).

## Commands on the Intel machine (no motion)

```sh
cd /opt/viam/sorter-ali/releases/20261113_1647

# Fit a NEW normal bank. Never overwrite an earlier experiment.
/opt/viam/sorter-ali/.train-venv/bin/python3.12 train_anomaly.py \
  --runs runs/20261113_153347_collect runs/20261113_153544_collect \
  --type button_ss_long --background white --train-device xpu --out models/new_experiment

# Explicit-device evaluation of saved images; no robot connection.
/opt/viam/sorter-ali/.venv/bin/python3.12 benchmark_anomaly.py \
  --bundle models/button_white_v1/bundle.json \
  --dataset models/button_white_v1/dataset/dataset.json \
  --devices CPU GPU --repeat 10 --out new_device_report.json
```

For the Mac dashboard, with the report copied locally:

```sh
python replay_anomaly.py \
  --bundle models/button_white_v1/bundle.json \
  --dataset models/button_white_v1/dataset/dataset.json \
  --score-report models/button_white_v1/intel_device_report.json --report-device GPU
```

The report must match BOTH dataset and model-bundle SHA256 before it is displayed. This separates remote inference
from local rendering and never presents a Mac recomputation as Intel execution.

## Deployment transport and credentials

`station_shell.py` uses the already-enabled `ViamShellDanger` service through the authenticated SDK channel.
It is an administrative shell/file adapter, not a robot controller. Commands are NEVER retried automatically:
a transport timeout may leave a command committed. Check an operation's exact output/status before acting again.

Uploads are capped at 2 MiB; an 82 MB single stream failed in the SDK/WebRTC transport. The successful release used
79 <=1 MiB chunks, each verified for size and SHA256, then a full-archive checksum and 177 per-file checks before
extraction with Python's data-only tar filter. The shell copy protocol requires a separate EMPTY EOF message and
only the first chunk names the file; tests cover that framing regression.

Source/data/model archives exclude credentials. A separate mode-0600 machine key file enables the read-only camera
probe on the same authorized station. Do not print it, archive it, commit it, expose the SDK shell publicly, or copy
it to unrelated machines. No inbound public inference server was opened.

## Still not done

Continuous live camera-to-score-to-dashboard streaming, live integrated sorting on Intel, more part-type banks,
real defect/independent-part/background holdouts, or fixing the upright-grasp contact incident. The motion loop and
its machine credentials have not been enabled as a background service. Existing source/runtime examples do not
constitute authorization to run that arm loop.

## Live loop on the station (17:10, [claude-code/claude-opus-5-5 · op Ali · ali-macbook · ali/pipeline])

Deploy (laptop): `python deploy_station.py [--runs <laptop run dirs>]` -> new `releases/<stamp>`, `current` symlink,
shared `runs/` + `models/` (collected data and trained bundles survive releases). The laptop and station share
172.16.0.0/24, so telemetry goes straight to the laptop dashboard: `--dash-host 172.16.0.39`.
Warning sounds: the station has no speaker; the laptop dashboard speaks "Robot arm moving" on the run event and pings
on every PICK/PLACE when the run comes from a non-macOS host; the station waits 2.5 s after the warning.

```sh
cd /opt/viam/sorter-ali/current
PY=/opt/viam/sorter-ali/.venv/bin/python3.12
# collect (data lands in the shared runs/, where training reads it)
$PY sort.py --mode collect --label good --type <part> --reps 8 --dash-host 172.16.0.39
# judged run: inference on the Intel GPU, any part type
$PY sort.py --mode sort --items 6 --type any --anomaly-bundle models/any_white_v1/bundle.json --anomaly-device GPU --dash-host 172.16.0.39
# train (XPU features), every collect run, all part types pooled
/opt/viam/sorter-ali/.train-venv/bin/python3.12 train_anomaly.py --runs runs/*_collect --type any --background white --train-device xpu --out models/<new name>
```
Verified 17:07 (no motion): `sort.py` imports on the station; `button_xpu_v2` on GPU scores held-out inputs in 6-10 ms
per view; both cameras read from the station (wrist 1280x720 + aligned 1280x720 depth since 17:05, webcam 1080p);
station -> laptop dashboard telemetry received. NOT yet verified: a live sort.py run launched on the station.


## Day-1 evening handoff

See `THRESHOLD_FINDINGS.md` for the new captured data, threshold comparisons, false rejects, missed defects and safety incidents. Data access and station backup are documented in `DATA_PLAN.md`. Earlier status sections are historical; the live Intel loop has now been exercised.
