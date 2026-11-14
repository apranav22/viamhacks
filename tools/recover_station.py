"""Recover station-only source and model artifacts without changing the station.

python -m tools.recover_station [--models]

Source snapshots and a SHA256 inventory go to archive/station/. Model descriptors
are tracked there; weights go to the ignored models/ directory. Existing local
files are never overwritten. Only explicitly allowed source/config/model files
are read; credentials, raw images, logs, and process controls are excluded.
"""
import argparse
import asyncio
import hashlib
import json
import os
import shlex
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from station import connect
from station_shell import execute
from tools.identity import identity_line
from viam.gen.service.shell.v1.shell_grpc import ShellServiceStub
from viam.proto.service.shell import CopyFilesFromMachineRequest, CopyFilesFromMachineRequestMetadata

ROOT = Path(__file__).resolve().parents[1]
BASE = "/opt/viam/sorter-ali"
CONFIGS = ("poses.json", "checkpoint.json", "part_sizes.json", "obstacles.json", "overview_calib.json")


async def remote(machine, code):
    rc, result = await execute(machine, "python3 -c " + shlex.quote(code), 60)
    if rc:
        raise RuntimeError("Station read failed; no remote writes were attempted")
    return json.loads(result)


def destination(entry, archive):
    rel = Path(entry["relative"])
    if entry["category"] not in {"experiments", "release", "station", "config", "models"} or rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Invalid station inventory path")
    return archive / entry["category"] / rel


def matches(path, entry):
    return path.is_file() and path.stat().st_size == entry["size"] and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]


def verify_snapshot(archive):
    """Verify recovered bytes and assemble complete copies of conflicting bundles."""
    archive = Path(archive).resolve()
    inventory = json.loads((archive / "inventory.json").read_text())
    verified = []
    conflicts = set()
    for entry in inventory["files"]:
        candidates = [destination(entry, archive)]
        if entry["category"] == "models":
            candidates += [ROOT / "models" / entry["relative"], ROOT / "models" / "_station" / archive.name / entry["relative"]]
        source = next((p for p in candidates if matches(p, entry)), None)
        if source is None:
            raise RuntimeError(f"Missing or mismatched recovered file: {entry['category']}/{entry['relative']}")
        if entry["category"] == "models":
            local = ROOT / "models" / entry["relative"]
            if local.exists() and not matches(local, entry):
                conflicts.add(Path(entry["relative"]).parts[0])
        verified.append({"category": entry["category"], "relative": entry["relative"], "local": str(source.relative_to(ROOT)), "sha256": entry["sha256"], "size": entry["size"]})
    # A conflicting bundle must be self-contained, including metadata and matching XML/BIN pairs.
    for entry, result in zip(inventory["files"], verified):
        if entry["category"] != "models" or Path(entry["relative"]).parts[0] not in conflicts:
            continue
        dest = ROOT / "models" / "_station" / archive.name / entry["relative"]
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.link(ROOT / result["local"], dest)
        if not matches(dest, entry):
            raise RuntimeError(f"Conflicting artifact not preserved: {dest}")
    report = {"identity": inventory["identity"], "release": inventory["release"], "verified_files": len(verified),
              "bytes": sum(e["size"] for e in verified), "conflicting_bundles": sorted(conflicts), "files": verified}
    (archive / "recovery.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def pack_snapshot(archive):
    """Keep historical source/data descriptors out of the maintained source tree."""
    archive = Path(archive).resolve()
    report = verify_snapshot(archive)
    packed = archive / "evidence.tar.gz"
    if packed.exists():
        raise FileExistsError(packed)
    with tarfile.open(packed, "w:gz") as tar:
        for category in ("experiments", "release", "station", "config", "models"):
            if (archive / category).exists():
                tar.add(archive / category, arcname=category)
    # Verify every archived file before removing the loose duplicate sources.
    with tarfile.open(packed, "r:gz") as tar:
        for entry in report["files"]:
            member = f"{entry['category']}/{entry['relative']}"
            if not (archive / member).exists():
                continue  # XML/BIN artifacts are retained in ignored models/, not git.
            if hashlib.sha256(tar.extractfile(member).read()).hexdigest() != entry["sha256"]:
                raise RuntimeError(f"Archive verification failed: {member}")
    for category in ("experiments", "release", "station", "config", "models"):
        if (archive / category).exists():
            shutil.rmtree(archive / category)
    report["evidence_archive"] = packed.name
    report["evidence_sha256"] = hashlib.sha256(packed.read_bytes()).hexdigest()
    for entry in report["files"]:
        member = f"{entry['category']}/{entry['relative']}"
        if entry["local"].startswith(str(archive.relative_to(ROOT)) + "/"):
            entry["local"] = f"{packed.relative_to(ROOT)}:{member}"
    (archive / "recovery.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified {report['verified_files']} files; packed historical evidence into {packed.relative_to(ROOT)}")


async def read_file(machine, entry):
    """Download one allowlisted file through the existing shell file-transfer API."""
    data = bytearray()
    stub = ShellServiceStub(machine._channel)
    async with stub.CopyFilesFromMachine.open(timeout=180) as stream:
        await stream.send_message(CopyFilesFromMachineRequest(metadata=CopyFilesFromMachineRequestMetadata(
            name="ViamShellDanger", paths=[entry["path"]], allow_recursion=False, preserve=False)))
        async for response in stream:
            if not response.HasField("file_data"):
                continue
            packet = response.file_data
            if packet.is_dir:
                raise ValueError("Expected one file, received directory")
            data.extend(packet.data)
            if len(data) > entry["size"]:
                raise ValueError("Station file grew during recovery")
            if packet.eof:
                await stream.send_message(CopyFilesFromMachineRequest(ack_last_file=True))
                await stream.end()
                break
        else:
            raise RuntimeError("Station download ended without EOF")
    if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise RuntimeError(f"Station file changed during recovery: {entry['path']}")
    return data


async def main(include_models=False, resume=None, source_only=False):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = Path(resume).resolve() if resume else ROOT / "archive" / "station" / stamp
    archive.mkdir(parents=True, exist_ok=bool(resume))
    async with await asyncio.wait_for(connect(), 30) as machine:
        inventory = json.loads((archive / "inventory.json").read_text()) if resume else await remote(machine, f'''
import hashlib,json
from pathlib import Path
b=Path({BASE!r}); r=(b/'current').resolve(); files=[]
def add(p, category, relative):
 if p.is_file() and not p.is_symlink():
  files.append(dict(path=str(p),category=category,relative=str(relative),size=p.stat().st_size,
                    sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
for folder,category in [(b/'exp','experiments'),(r,'release'),(b,'station')]:
 for pattern in ('*.py','*.sh'):
  for p in sorted(folder.glob(pattern)): add(p,category,p.name)
for dirname in ('vh','dashboard','tools','config'):
 for p in sorted((r/dirname).rglob('*')):
  if p.suffix in ('.py','.sh','.js','.html','.css') and '__pycache__' not in p.parts:
   add(p,'release',p.relative_to(r))
for name in {CONFIGS!r}: add(r/'config'/name,'config',name)
if not {source_only!r}:
 for p in sorted((b/'models').rglob('*')):
  if p.suffix in ('.json','.xml','.bin') and p.is_file(): add(p,'models',p.relative_to(b/'models'))
print(json.dumps(dict(release=str(r),files=files)))
''')
        inventory.setdefault("recovered_at", stamp)
        inventory.setdefault("identity", identity_line())
        (archive / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
        print(f"Inventory: {len(inventory['files'])} files from {inventory['release']}", flush=True)
        # Complete source/metadata before downloading large model weights.
        entries = sorted(inventory["files"], key=lambda e: e["relative"].endswith((".xml", ".bin")))
        conflicts = []
        for entry in entries:
            is_model = entry["category"] == "models"
            if is_model and entry["relative"].endswith((".xml", ".bin")) and not include_models:
                continue
            dest = destination(entry, archive)
            # Keep model metadata in git; model binaries remain outside git.
            if is_model and entry["relative"].endswith((".xml", ".bin")):
                dest = ROOT / "models" / entry["relative"]
            if is_model:
                local = ROOT / "models" / entry["relative"]
                if local.exists() and hashlib.sha256(local.read_bytes()).hexdigest() == entry["sha256"]:
                    if dest != local:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(local.read_bytes())
                    continue
            if dest.exists():
                if hashlib.sha256(dest.read_bytes()).hexdigest() == entry["sha256"]:
                    continue
                if not is_model:
                    raise FileExistsError(f"Refusing to replace {dest}")
                # Same model name with different bytes: retain both versions.
                conflicts.append(entry["relative"])
                dest = ROOT / "models" / "_station" / archive.name / entry["relative"]
                if dest.exists():
                    if hashlib.sha256(dest.read_bytes()).hexdigest() == entry["sha256"]:
                        continue
                    raise FileExistsError(f"Refusing to replace {dest}")
            data = await read_file(machine, entry)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            # Restore missing model metadata to the local artifact tree as well.
            if is_model and dest.is_relative_to(archive):
                local = ROOT / "models" / entry["relative"]
                if not local.exists():
                    local.parent.mkdir(parents=True, exist_ok=True)
                    local.write_bytes(data)
            print(f"Recovered {dest.relative_to(ROOT)} ({len(data)} bytes)", flush=True)
        (archive / "conflicts.json").write_text(json.dumps(conflicts, indent=2) + "\n")
    print(f"Recovered snapshot: {archive.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", action="store_true", help="also download missing OpenVINO XML/BIN artifacts into ignored models/")
    parser.add_argument("--resume", type=Path, help="resume a previously inventoried snapshot")
    parser.add_argument("--source-only", action="store_true", help="recover source/config only, including deployed packages and dashboard assets")
    parser.add_argument("--pack", type=Path, help="verify and pack a completed local snapshot; no station connection")
    args = parser.parse_args()
    if args.pack:
        pack_snapshot(args.pack)
    else:
        asyncio.run(main(args.models, args.resume, args.source_only))
