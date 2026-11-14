"""Offline tests for sync_data.py: a fake hub backed by a temp directory stands in for Hugging Face."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sync_data as S


class FakeHub:
    """Same methods as S.Hub; the 'repo' is a directory, each commit a counter."""

    def __init__(self, remote: Path):
        self.repo_id, self.remote, self.commits = "team/fake", remote, 0

    def read_index(self, revision=None):
        p = self.remote / "index.json"
        return json.loads(p.read_text()) if p.exists() else {"runs": {}, "models": {}}

    def commit(self, files, index, message):
        for rel, local in files:
            dst = self.remote / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local, dst)
        (self.remote / "index.json").write_text(json.dumps(index))
        self.commits += 1
        return f"commit{self.commits}"

    def download(self, patterns, local_dir, revision=None):
        import fnmatch
        for p in self.remote.rglob("*"):
            rel = p.relative_to(self.remote).as_posix()
            if p.is_file() and any(fnmatch.fnmatch(rel, pat) for pat in patterns):
                dst = Path(local_dir) / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, dst)


def make_run(root: Path, name, items=2, label="good", type_="hex_bolt_short", age=600, dash=True, meta=True):
    run = root / "runs" / name
    for i in range(1, items + 1):
        d = run / f"item_{i:03d}"
        d.mkdir(parents=True)
        if meta:
            (d / "meta.json").write_text(json.dumps({"item": i, "label": label, "type": type_, "background": "cardboard"}))
        (d / "top_1.jpg").write_bytes(os.urandom(64))
    (run / "decisions.jsonl").write_text("".join(json.dumps({"item": i, "label": label, "type": type_}) + "\n"
                                                 for i in range(1, items + 1)))
    if dash:
        (run / "dash" / "frames").mkdir(parents=True)
        (run / "dash" / "frames" / "f.jpg").write_bytes(b"cache")
    old = time.time() - age
    for p in run.rglob("*"):
        os.utime(p, (old, old))
    return run


def push_args(**kw):
    a = dict(runs=[], models=[], min_age=120, with_dash=False, force=False, dry_run=False)
    a.update(kw)
    return Namespace(**a)


def pull_args(**kw):
    a = dict(runs=[], models=[], revision=None, force=False)
    a.update(kw)
    return Namespace(**a)


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.laptop, self.station, self.remote = self.tmp / "laptop", self.tmp / "station", self.tmp / "remote"
        for d in (self.laptop, self.station, self.remote):
            d.mkdir()
        self.hub = FakeHub(self.remote)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def push(self, root, host="laptop", **kw):
        with patch("socket.gethostname", return_value=host):
            return S.cmd_push(push_args(**kw), self.hub, root)

    def test_push_selects_finished_data_runs_without_dash(self):
        make_run(self.laptop, "20261113_150000_collect")
        make_run(self.laptop, "20261113_150500_sort", items=1, label="defect")
        make_run(self.laptop, "20261113_151000_dry", items=1)            # dry runs: not data
        (self.laptop / "runs" / "20261113_152000_collect" / "dash").mkdir(parents=True)  # dashboard mirror only
        make_run(self.laptop, "20261113_153000_collect", age=5)          # still being written
        oid = self.push(self.laptop)
        self.assertEqual(oid, "commit1")
        idx = self.hub.read_index()
        self.assertEqual(sorted(idx["runs"]), ["20261113_150000_collect", "20261113_150500_sort"])
        e = idx["runs"]["20261113_150000_collect"]
        self.assertEqual((e["items"], e["labels"], e["types"], e["host"]), (2, {"good": 2}, {"hex_bolt_short": 2}, "laptop"))
        self.assertTrue((self.remote / "runs/20261113_150000_collect/item_002/top_1.jpg").exists())
        self.assertFalse((self.remote / "runs/20261113_150000_collect/dash").exists())

    def test_push_is_idempotent_and_repushes_edits(self):
        run = make_run(self.laptop, "20261113_150000_collect")
        self.push(self.laptop)
        self.assertIsNone(self.push(self.laptop))                         # unchanged: no commit
        self.assertEqual(self.hub.commits, 1)
        (run / "exclude.json").write_text('{"item_002": "bad crop"}')     # reviewed later
        old = time.time() - 600
        os.utime(run / "exclude.json", (old, old))
        self.push(self.laptop)
        self.assertEqual(self.hub.commits, 2)
        self.assertEqual(self.hub.read_index()["runs"]["20261113_150000_collect"]["excluded"], 1)

    def test_name_collision_from_another_host_is_refused(self):
        make_run(self.laptop, "20261113_171443_collect")
        self.push(self.laptop, host="laptop")
        make_run(self.station, "20261113_171443_collect")                 # same name, different bytes
        self.assertIsNone(self.push(self.station, host="armfarm04b"))
        self.assertEqual(self.hub.read_index()["runs"]["20261113_171443_collect"]["host"], "laptop")

    def test_same_run_copied_to_station_is_not_reuploaded(self):
        run = make_run(self.laptop, "20261113_150000_collect")
        self.push(self.laptop)
        shutil.copytree(run, self.station / "runs" / run.name)            # deploy_station.py --runs
        self.assertIsNone(self.push(self.station, host="armfarm04b"))

    def test_pull_roundtrip_and_never_clobbers_local_edits(self):
        make_run(self.station, "20261113_171443_collect", items=3, label="defect")
        make_run(self.station, "20261113_171810_collect")
        self.push(self.station, host="armfarm04b")
        got = S.cmd_pull(pull_args(runs=["*_171443_*"]), self.hub, self.laptop)
        self.assertEqual(got, ["20261113_171443_collect"])
        self.assertTrue((self.laptop / "runs/20261113_171443_collect/item_003/meta.json").exists())
        self.assertEqual(S.cmd_pull(pull_args(runs=["*_171443_*"]), self.hub, self.laptop), [])   # up to date
        (self.laptop / "runs/20261113_171443_collect/exclude.json").write_text("{}")             # local review
        self.assertEqual(S.cmd_pull(pull_args(runs=["*_171443_*"]), self.hub, self.laptop), [])   # kept
        self.assertTrue((self.laptop / "runs/20261113_171443_collect/exclude.json").exists())

    def test_models_push_and_pull(self):
        m = self.laptop / "models" / "any_cardboard_v2"
        m.mkdir(parents=True)
        (m / "bundle.json").write_text("{}")
        (m / "top.bin").write_bytes(os.urandom(128))
        old = time.time() - 600
        for p in [m, *m.iterdir()]:
            os.utime(p, (old, old))
        self.push(self.laptop, models=["any_cardboard_v2", "nope"])
        self.assertIn("any_cardboard_v2", self.hub.read_index()["models"])
        S.cmd_pull(pull_args(models=["any_cardboard_v2"]), self.hub, self.station)
        self.assertEqual((self.station / "models/any_cardboard_v2/top.bin").read_bytes(), (m / "top.bin").read_bytes())

    def test_legacy_run_without_meta_is_shared_with_labels_from_decisions(self):
        make_run(self.laptop, "20261113_151143_collect", items=2, label="good", type_="button_ss_long", meta=False)
        self.push(self.laptop)
        e = self.hub.read_index()["runs"]["20261113_151143_collect"]
        self.assertEqual((e["items"], e["without_meta"], e["labels"], e["types"]), (2, 2, {"good": 2}, {"button_ss_long": 2}))

    def test_post_run_push_spawns_one_detached_run_push(self):
        run = make_run(self.station, "20261114_120000_collect", age=0)
        calls = []

        def fake_popen(cmd, **kw):
            calls.append((cmd, kw))
            return "proc"
        self.assertEqual(S.spawn_push(run, popen=fake_popen), "proc")
        (cmd, kw), = calls
        self.assertEqual(cmd[cmd.index("--root") + 1], str(self.station))
        self.assertEqual(cmd[-4:], ["push", "20261114_120000_collect", "--min-age", "0"])
        self.assertEqual(cmd[:3], ["nice", "-n", "10"])
        self.assertTrue(kw["start_new_session"])
        self.assertIn("post-run push 20261114_120000_collect", (self.station / "runs" / S.POST_RUN_LOG).read_text())
        # the command it builds pushes the fresh run (min-age 0) and nothing else
        make_run(self.station, "20261114_110000_collect")
        with patch("socket.gethostname", return_value="station"):
            S.cmd_push(push_args(runs=[cmd[-3]], min_age=0), self.hub, self.station)
        self.assertEqual(sorted(self.hub.read_index()["runs"]), ["20261114_120000_collect"])

    def test_post_run_push_skips_runs_without_picks(self):
        empty = self.station / "runs" / "20261114_120500_collect"
        empty.mkdir(parents=True)
        (empty / "decisions.jsonl").write_text("")
        self.assertIsNone(S.spawn_push(empty, popen=lambda *a, **k: self.fail("spawned")))

    def test_push_holds_the_host_lock_around_index_read_and_commit(self):
        import fcntl
        make_run(self.laptop, "20261113_150000_collect")
        lock = (self.laptop / "runs" / S.LOCK_NAME)
        seen = []
        real_read = self.hub.read_index

        def read_index(revision=None):
            with open(lock) as f:   # a second locker must not get in while the push runs
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    seen.append("free")
                except BlockingIOError:
                    seen.append("held")
            return real_read(revision)
        self.hub.read_index = read_index
        self.push(self.laptop)
        self.assertEqual(seen, ["held"])
        with open(lock) as f:       # released afterwards
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_dry_run_commits_nothing(self):
        make_run(self.laptop, "20261113_150000_collect")
        self.assertIsNone(self.push(self.laptop, dry_run=True))
        self.assertEqual(self.hub.commits, 0)


if __name__ == "__main__":
    unittest.main()
