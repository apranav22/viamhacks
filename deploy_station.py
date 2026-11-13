"""Deploy the sort loop to the Intel station (armfarm04b) and sync collected data. Moves nothing on the robot.

    python deploy_station.py                       # code + config -> new release, made active
    python deploy_station.py --runs 20261113_153544_collect 20261113_154405_collect   # also push laptop runs

Layout on the station (/opt/viam/sorter-ali):
    releases/<stamp>/   code + config, immutable once deployed
    current -> releases/<stamp>
    runs/               shared: every collect/sort run, from any release (training reads these)
    models/             shared: every trained bundle
    .venv/              runtime (OpenVINO, Viam SDK)      .train-venv/  training (torch XPU, anomalib)

Transfer goes through the ViamShellDanger shell service (station_shell.py): uploads are chunked (<=1.5 MB),
each chunk SHA256-checked on the station before the archive is assembled and extracted.
The release gets the station's existing api-key.json copied from the previous release (never re-uploaded).
"""

import argparse
import asyncio
import hashlib
import io
import json
import shlex
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from station import connect                       # noqa: E402
from station_shell import execute, upload         # noqa: E402

BASE = "/opt/viam/sorter-ali"
CHUNK = 1_500_000
CODE = ["sort.py", "pipeline.py", "screws.py", "tracking.py", "overview.py", "station.py", "train_anomaly.py",
        "replay_anomaly.py", "benchmark_anomaly.py", "requirements.txt", "requirements-anomaly.txt"]
DIRS = ["vh", "config"]
SKIP = ("__pycache__", ".pyc", "backup-")


def build_archive(runs):
    buf = io.BytesIO()
    files = {}
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        def add(path: Path, arc: str):
            if any(s in str(path) for s in SKIP):
                return
            data = path.read_bytes()
            files[arc] = hashlib.sha256(data).hexdigest()
            ti = tarfile.TarInfo(arc); ti.size = len(data); ti.mtime = int(path.stat().st_mtime); ti.mode = 0o644
            tar.addfile(ti, io.BytesIO(data))
        for f in CODE:
            if (ROOT / f).exists():
                add(ROOT / f, f)
        for d in DIRS:
            for p in sorted((ROOT / d).rglob("*")):
                if p.is_file():
                    add(p, str(p.relative_to(ROOT)))
        for r in runs:
            for p in sorted((ROOT / "runs" / r).rglob("*")):
                if p.is_file() and "/dash/" not in str(p):
                    add(p, "shared_runs/" + str(p.relative_to(ROOT / "runs")))
        manifest = json.dumps({"files": files, "built": time.strftime("%Y-%m-%d %H:%M:%S")}).encode()
        ti = tarfile.TarInfo("DEPLOYMENT_MANIFEST.json"); ti.size = len(manifest)
        tar.addfile(ti, io.BytesIO(manifest))
    return buf.getvalue(), files


REMOTE_ASSEMBLE = r'''
import hashlib, json, os, shutil, sys, tarfile
from pathlib import Path
base = Path("{base}"); stage = base / "incoming" / "{stamp}"
man = json.loads((stage / "chunks.json").read_text())
blob = b""
for c in man["chunks"]:
    d = (stage / c["name"]).read_bytes()
    if hashlib.sha256(d).hexdigest() != c["sha256"]: sys.exit("chunk mismatch " + c["name"])
    blob += d
if hashlib.sha256(blob).hexdigest() != man["sha256"]: sys.exit("archive mismatch")
rel = base / "releases" / "{stamp}"; rel.mkdir(parents=True)
import io
with tarfile.open(fileobj=io.BytesIO(blob)) as t: t.extractall(rel, filter="data")
files = json.loads((rel / "DEPLOYMENT_MANIFEST.json").read_text())["files"]
bad = [n for n, h in files.items() if hashlib.sha256((rel / n).read_bytes()).hexdigest() != h]
if bad: sys.exit("file mismatch " + ",".join(bad[:5]))
for shared in ("runs", "models"):
    (base / shared).mkdir(exist_ok=True)
prev = Path((base / "ACTIVE_RELEASE").read_text().strip()) if (base / "ACTIVE_RELEASE").exists() else None
if prev and prev.exists():
    for shared in ("runs", "models"):            # one-time: adopt data/models that lived inside the old release
        src = prev / shared
        if src.is_dir() and not src.is_symlink():
            for item in src.iterdir():
                if not (base / shared / item.name).exists(): shutil.copytree(item, base / shared / item.name)
    if (prev / "api-key.json").exists():
        shutil.copy2(prev / "api-key.json", rel / "api-key.json"); os.chmod(rel / "api-key.json", 0o600)
moved = 0
if (rel / "shared_runs").exists():
    for item in (rel / "shared_runs").iterdir():
        dst = base / "runs" / item.name
        if not dst.exists(): shutil.move(str(item), dst); moved += 1
    shutil.rmtree(rel / "shared_runs")
for shared in ("runs", "models"):
    (rel / shared).symlink_to(base / shared)
tmp = base / "current.tmp"
if tmp.exists() or tmp.is_symlink(): tmp.unlink()
tmp.symlink_to(rel); tmp.replace(base / "current")
(base / "ACTIVE_RELEASE").write_text(str(rel) + "\n")
shutil.rmtree(stage)
print(json.dumps({{"release": str(rel), "files": len(files), "runs_added": moved,
                  "key": (rel / "api-key.json").exists(), "runs_total": len(list((base / "runs").iterdir())),
                  "models": sorted(p.name for p in (base / "models").iterdir())}}))
'''


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="*", default=[], help="laptop runs/<name> folders to copy into the shared runs/")
    a = ap.parse_args()
    blob, files = build_archive(a.runs)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    chunks = [blob[i:i + CHUNK] for i in range(0, len(blob), CHUNK)]
    print(f"archive {len(blob) / 1e6:.1f} MB, {len(files)} files, {len(chunks)} chunks -> release {stamp}", flush=True)
    async with await connect() as m:
        stage = f"{BASE}/incoming/{stamp}"
        rc, out = await execute(m, f"mkdir -p {stage}")
        if rc:
            raise SystemExit(out)
        man = {"sha256": hashlib.sha256(blob).hexdigest(), "chunks": []}
        with tempfile.TemporaryDirectory() as td:
            for i, c in enumerate(chunks):
                p = Path(td) / f"chunk_{i:04d}"
                p.write_bytes(c)
                await upload(m, p, f"{stage}/{p.name}")
                man["chunks"].append({"name": p.name, "sha256": hashlib.sha256(c).hexdigest()})
                print(f"  chunk {i + 1}/{len(chunks)}", flush=True)
            mp = Path(td) / "chunks.json"; mp.write_text(json.dumps(man))
            await upload(m, mp, f"{stage}/chunks.json")
            sp = Path(td) / "assemble.py"; sp.write_text(REMOTE_ASSEMBLE.format(base=BASE, stamp=stamp))
            await upload(m, sp, f"{stage}/assemble.py")
        rc, out = await execute(m, f"{BASE}/.venv/bin/python3.12 {stage}/assemble.py", timeout=180)
        print(out.strip())
        if rc:
            raise SystemExit(f"assemble failed (rc {rc})")


if __name__ == "__main__":
    asyncio.run(main())
