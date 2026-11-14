"""Share collected runs (and trained model bundles) with the team through the configured Hugging Face dataset repo.

    python sync_data.py init <org-or-user>/<name>   # once: create the private repo, write config/data_repo.json
    python sync_data.py status                     # local vs shared, per run
    python sync_data.py push                       # every finished *_collect / *_sort run not yet shared
    python sync_data.py push 20261113_183403_collect --models any_cardboard_v2
    python sync_data.py pull                       # every shared run you don't have
    python sync_data.py pull '20261113_18*' --models any_cardboard_v2 --revision <commit>

Layout in the repo: runs/<run>/... exactly as on disk (item_NNN/meta.json + images, decisions.jsonl, exclude.json),
models/<name>/..., and index.json (per run: host, item/label/type counts, content fingerprint).

Safety:
- A run whose newest file is younger than --min-age seconds (default 120) is still being written: skipped.
- Unchanged runs (same fingerprint as index.json) are skipped, so pushing is cheap and idempotent.
- A run name that exists in the repo with different content from ANOTHER host is a name collision: refused.
- pull never overwrites a local run whose content differs from the shared copy (push it first, or --force).
- Uploads only add/replace files; nothing is ever deleted in the repo.
- dash/ (laptop dashboard cache) is not uploaded unless --with-dash.

Auth: standard Hugging Face token (`hf auth login`, or HF_TOKEN). Every push prints the commit: train from a pinned
snapshot with `pull --revision <commit>` to know exactly which data a model saw. Moves nothing on the robot.
"""

import argparse
import fnmatch
import hashlib
import json
import os
import socket
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "data_repo.json"
RUN_KINDS = ("_collect", "_sort")
SKIP_PARTS = {"__pycache__", ".DS_Store"}


# ---------- local content ----------

def run_files(run_dir: Path, with_dash=False):
    """Files of one run (relative paths, sorted), without caches."""
    out = []
    for p in sorted(run_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(run_dir)
        if SKIP_PARTS & set(rel.parts) or (not with_dash and rel.parts[0] == "dash"):
            continue
        out.append(rel.as_posix())
    return out


def fingerprint(run_dir: Path, files):
    """sha256 over (path, sha256(content)) of every file: equal iff the shared content is equal."""
    h = hashlib.sha256()
    for rel in files:
        h.update(rel.encode() + b"\0" + hashlib.sha256((run_dir / rel).read_bytes()).digest())
    return h.hexdigest()


def newest_mtime(run_dir: Path):
    return max((p.stat().st_mtime for p in run_dir.rglob("*") if p.is_file()), default=run_dir.stat().st_mtime)


def summarize(run_dir: Path, files, with_dash=False):
    """Index entry: counts that let a teammate pick runs without downloading them."""
    labels, types, backgrounds = Counter(), Counter(), Counter()
    rows = {}
    try:  # decisions.jsonl: one row per pick; the only labels in runs older than meta.json (15:31)
        for line in (run_dir / "decisions.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                rows[f"item_{int(r['item']):03d}"] = r
    except (OSError, ValueError, KeyError, TypeError):
        pass
    item_dirs = sorted({rel.split("/")[0] for rel in files if rel.startswith("item_") and "/" in rel})
    items, legacy = len(item_dirs), 0
    for it in item_dirs:
        try:
            m = json.loads((run_dir / it / "meta.json").read_text())
        except (OSError, ValueError):
            m, legacy = rows.get(it, {}), legacy + 1
        labels[str(m.get("label"))] += 1
        types[str(m.get("type"))] += 1
        backgrounds[str(m.get("background"))] += 1
    excl = run_dir / "exclude.json"
    try:
        excluded = len(json.loads(excl.read_text())) if excl.exists() else 0
    except (OSError, ValueError):
        excluded = 0
    return {
        "host": socket.gethostname().split(".")[0],
        "items": items, "excluded": excluded, "without_meta": legacy,
        "labels": dict(labels), "types": dict(types), "backgrounds": dict(backgrounds),
        "files": len(files), "bytes": sum((run_dir / f).stat().st_size for f in files),
        "fingerprint": fingerprint(run_dir, files),
        "with_dash": with_dash,
        "pushed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def is_data_run(run_dir: Path):
    return (run_dir.is_dir() and run_dir.name.endswith(RUN_KINDS) and (run_dir / "decisions.jsonl").exists()
            and any(p.is_dir() and any(p.iterdir()) for p in run_dir.glob("item_*")))


def local_runs(runs_root: Path, names=None):
    """Explicit names/globs (any run dir), else every *_collect / *_sort run that has picks."""
    if not runs_root.is_dir():
        return []
    dirs = sorted(p for p in runs_root.iterdir() if p.is_dir())
    if names:
        return [d for d in dirs if any(fnmatch.fnmatch(d.name, n) for n in names)]
    return [d for d in dirs if is_data_run(d)]


# ---------- planning (pure, tested offline) ----------

def plan_push(candidates, remote_index, now, min_age=120, force=False, with_dash=False):
    """-> (to_push: [(name, dir, entry)], skipped: [(name, reason)])."""
    to_push, skipped = [], []
    for d in candidates:
        age = now - newest_mtime(d)
        if age < min_age and not force:
            skipped.append((d.name, f"still being written ({age:.0f} s old < {min_age} s)"))
            continue
        files = run_files(d, with_dash)
        if not files:
            skipped.append((d.name, "no files"))
            continue
        entry = summarize(d, files, with_dash)
        old = remote_index.get(d.name)
        if old and old.get("fingerprint") == entry["fingerprint"]:
            skipped.append((d.name, "already shared, unchanged"))
            continue
        if old and old.get("host") != entry["host"] and not force:
            skipped.append((d.name, f"NAME COLLISION: shared copy came from {old.get('host')} with different "
                                    f"content; rename one, or --force to overwrite"))
            continue
        to_push.append((d.name, d, entry))
    return to_push, skipped


def plan_pull(patterns, remote_index, runs_root: Path, force=False):
    """-> (to_pull: [name], skipped: [(name, reason)])."""
    names = sorted(remote_index)
    if patterns:
        names = [n for n in names if any(fnmatch.fnmatch(n, p) for p in patterns)]
    to_pull, skipped = [], []
    for n in names:
        local = runs_root / n
        entry = remote_index[n]
        if local.exists():
            files = run_files(local, entry.get("with_dash", False))
            if files and fingerprint(local, files) == entry.get("fingerprint"):
                skipped.append((n, "up to date"))
                continue
            if files and not force:
                skipped.append((n, "local copy differs from the shared one: push it, or --force to overwrite"))
                continue
        to_pull.append(n)
    return to_pull, skipped


# ---------- the hub ----------

class Hub:
    """Thin wrapper over huggingface_hub; tests substitute a fake with the same methods."""

    def __init__(self, repo_id):
        from huggingface_hub import HfApi
        self.repo_id, self.api = repo_id, HfApi()

    def create(self):
        return self.api.create_repo(self.repo_id, repo_type="dataset", private=True, exist_ok=True)

    def read_index(self, revision=None):
        from huggingface_hub import hf_hub_download
        from huggingface_hub.utils import EntryNotFoundError, RepositoryNotFoundError
        try:
            p = hf_hub_download(self.repo_id, "index.json", repo_type="dataset", revision=revision)
        except EntryNotFoundError:
            return {"runs": {}, "models": {}}
        except RepositoryNotFoundError:
            sys.exit(f"repo {self.repo_id} not found, or no access: `hf auth login` with an account in the team org")
        return json.loads(Path(p).read_text())

    def commit(self, files, index, message):
        """files: [(path_in_repo, local_path)]. One commit with every file + the new index.json."""
        from huggingface_hub import CommitOperationAdd
        ops = [CommitOperationAdd(path_in_repo=r, path_or_fileobj=str(l)) for r, l in files]
        ops.append(CommitOperationAdd(path_in_repo="index.json",
                                      path_or_fileobj=json.dumps(index, indent=1, sort_keys=True).encode()))
        info = self.api.create_commit(self.repo_id, ops, commit_message=message, repo_type="dataset")
        return getattr(info, "oid", None) or str(info)

    def download(self, patterns, local_dir, revision=None):
        from huggingface_hub import snapshot_download
        snapshot_download(self.repo_id, repo_type="dataset", allow_patterns=patterns, local_dir=local_dir,
                          revision=revision)


def repo_id_from_config():
    rid = os.environ.get("VH_DATA_REPO")
    if not rid and CONFIG.exists():
        rid = json.loads(CONFIG.read_text()).get("repo_id")
    if not rid:
        sys.exit("no data repo configured: python sync_data.py init <org-or-user>/<name>")
    return rid


# ---------- commands ----------

def cmd_push(args, hub, root=ROOT):
    index = hub.read_index()
    index.setdefault("runs", {}); index.setdefault("models", {})
    plan, skipped = plan_push(local_runs(root / "runs", args.runs), index["runs"], time.time(),
                              args.min_age, args.force, args.with_dash)
    mplan, mskipped = [], []
    if args.models:
        mdirs = [d for d in local_runs(root / "models", args.models)]
        missing = set(args.models) - {d.name for d in mdirs} - {n for n in args.models if any(c in n for c in "*?[")}
        mskipped += [(m, "not found locally") for m in sorted(missing)]
        mplan, ms = plan_push(mdirs, index["models"], time.time(), args.min_age, args.force, with_dash=True)
        mskipped += ms
    for n, why in skipped + mskipped:
        print(f"skip  {n}: {why}")
    if not plan and not mplan:
        print("nothing to push")
        return None
    files = []
    for kind, items in (("runs", plan), ("models", mplan)):
        for name, d, entry in items:
            files += [(f"{kind}/{name}/{rel}", d / rel) for rel in run_files(d, entry["with_dash"])]
            index[kind][name] = entry
            print(f"push  {kind}/{name}: {entry['files']} files, {entry['bytes'] / 1e6:.1f} MB"
                  + (f", {entry['items']} items {entry['labels']}" if kind == "runs" else ""))
    if args.dry_run:
        print(f"dry run: would commit {len(files)} files to {hub.repo_id}")
        return None
    host = socket.gethostname().split(".")[0]
    names = [n for n, _, _ in plan] + [f"models/{n}" for n, _, _ in mplan]
    oid = hub.commit(files, index, f"{host}: {', '.join(names)[:200]}")
    print(f"pushed {len(files)} files -> {hub.repo_id} @ {oid}")
    return oid


def cmd_pull(args, hub, root=ROOT):
    index = hub.read_index(args.revision)
    runs, skipped = plan_pull(args.runs, index.get("runs", {}), root / "runs", args.force)
    models, mskipped = ([], [])
    if args.models:
        models, mskipped = plan_pull(args.models, index.get("models", {}), root / "models", args.force)
    for n, why in skipped + mskipped:
        print(f"skip  {n}: {why}")
    patterns = [f"runs/{n}/**" for n in runs] + [f"models/{n}/**" for n in models]
    if not patterns:
        print("nothing to pull")
        return []
    hub.download(patterns, str(root), args.revision)
    for n in runs:
        print(f"pull  runs/{n}: {index['runs'][n]['items']} items from {index['runs'][n]['host']}")
    for n in models:
        print(f"pull  models/{n}")
    return runs + models


def cmd_status(args, hub, root=ROOT):
    index = hub.read_index()
    remote = index.get("runs", {})
    local = {d.name: d for d in local_runs(root / "runs")}
    rows = []
    for n in sorted(set(remote) | set(local)):
        r, d = remote.get(n), local.get(n)
        if r and d:
            same = fingerprint(d, run_files(d, r.get("with_dash", False))) == r.get("fingerprint")
            state = "shared" if same else "DIFFERS"
        else:
            state = "local only" if d else "shared, not here"
        items = r.get("items") if r else len([p for p in d.glob("item_*") if p.is_dir()])
        rows.append((n, state, items, (r or {}).get("host", "")))
    for n, state, items, host in rows:
        print(f"{n:34} {state:17} items {items!s:>4}  {host}")
    print(f"{len(remote)} runs shared, {len(index.get('models', {}))} models: {', '.join(sorted(index.get('models', {})))}")
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", type=Path, default=ROOT, help="folder holding runs/ and models/ (default: this repo; "
                   "on the station /opt/viam/sorter-ali)")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="create the private dataset repo and remember it in config/data_repo.json")
    i.add_argument("repo_id")
    s = sub.add_parser("push"); s.add_argument("runs", nargs="*", help="run names or globs (default: every finished data run)")
    s.add_argument("--models", nargs="*", default=[], help="model bundle names under models/")
    s.add_argument("--min-age", type=float, default=120, help="seconds since a run's newest file (default 120)")
    s.add_argument("--with-dash", action="store_true", help="also upload dash/ (dashboard cache)")
    s.add_argument("--force", action="store_true"); s.add_argument("--dry-run", action="store_true")
    q = sub.add_parser("pull"); q.add_argument("runs", nargs="*", help="run names or globs (default: all)")
    q.add_argument("--models", nargs="*", default=[]); q.add_argument("--revision", help="pin a commit (snapshot)")
    q.add_argument("--force", action="store_true")
    sub.add_parser("status")
    args = p.parse_args(argv)
    if args.cmd == "init":
        hub = Hub(args.repo_id)
        url = hub.create()
        CONFIG.parent.mkdir(exist_ok=True)
        CONFIG.write_text(json.dumps({"repo_id": args.repo_id, "repo_type": "dataset", "private": True}, indent=1) + "\n")
        print(f"ready: {url}\nwrote {CONFIG.relative_to(ROOT)} (commit it so the team and the station use the same repo)")
        return
    hub = Hub(repo_id_from_config())
    {"push": cmd_push, "pull": cmd_pull, "status": cmd_status}[args.cmd](args, hub, args.root.resolve())


if __name__ == "__main__":
    main()
