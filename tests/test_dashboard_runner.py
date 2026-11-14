"""Dashboard run control: argument whitelist, safety refusals, ARM log lines. Offline: a fake sort.py, no robot."""
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dashboard.runner import Runner, build_args  # noqa: E402
from dashboard.server import Hub, make_handler  # noqa: E402

TYPES = ["hex_bolt_short", "socket_m16"]


class FakeHub:
    active = False

    def run_active(self):
        return self.active


class BuildArgs(unittest.TestCase):
    def test_capture(self):
        kind, args = build_args({"kind": "capture", "type": "socket_m16", "label": "other:scratched", "reps": 3,
                                 "views": "coverage", "assume_lying": True}, TYPES)
        self.assertEqual(kind, "capture")
        self.assertEqual(args[:8], ["--mode", "collect", "--type", "socket_m16", "--label", "other:scratched", "--reps", "3"])
        self.assertIn("coverage", args)
        self.assertIn("--assume-lying", args)

    def test_detect(self):
        kind, args = build_args({"kind": "detect", "items": 4, "bundle": "models/each_cardboard_v4/bundle_m103.json",
                                 "decide": "top"}, TYPES)
        self.assertEqual(kind, "detect")
        self.assertEqual(args[:4], ["--mode", "sort", "--items", "4"])
        self.assertIn("top", args)

    def test_rejects_unsafe_or_unknown_values(self):
        bad = [{"kind": "capture", "type": "rm -rf"}, {"kind": "capture", "label": "good; reboot"},
               {"kind": "capture", "reps": 0}, {"kind": "detect", "bundle": "../../etc/passwd"},
               {"kind": "detect", "device": "TPU"}, {"kind": "move"}, {"kind": "capture", "background": "floor"}]
        for spec in bad:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                build_args(spec, TYPES)


class RunnerLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "config").mkdir()
        (self.tmp / "config" / "part_sizes.json").write_text(json.dumps({t: {} for t in TYPES}))
        (self.tmp / "sort.py").write_text("import sys, time\nprint('fake sort', ' '.join(sys.argv[1:]), flush=True)\ntime.sleep(float(__import__('os').environ.get('FAKE_S', '0.2')))\n")
        self.log = self.tmp / "AGENT_LOG.md"
        self.hub = FakeHub()
        self.runner = Runner(self.hub, root=self.tmp, log_path=self.log, other_sorter=lambda: False)
        self.spec = {"kind": "capture", "type": "socket_m16", "label": "good", "reps": 2, "estop_confirmed": True}

    def wait_end(self):
        for _ in range(100):
            if not self.runner.status()["running"]:
                return
            time.sleep(0.05)
        self.fail("run did not end")

    def test_requires_estop_confirmation(self):
        with self.assertRaises(PermissionError):
            self.runner.start({**self.spec, "estop_confirmed": False})
        self.assertFalse(self.log.exists())

    def test_refuses_while_other_run_active(self):
        self.hub.active = True
        with self.assertRaises(RuntimeError):
            self.runner.start(self.spec)
        self.hub.active = False
        busy = Runner(self.hub, root=self.tmp, log_path=self.log, other_sorter=lambda: True)
        with self.assertRaises(RuntimeError):
            busy.start(self.spec)

    def test_local_run_logs_taken_and_released(self):
        st = self.runner.start(self.spec)
        self.assertTrue(st["running"])
        with self.assertRaises(RuntimeError):         # one run at a time
            self.runner.start(self.spec)
        self.wait_end()
        st = self.runner.status()
        self.assertEqual(st["run"]["rc"], 0)
        self.assertTrue(any("fake sort --mode collect" in line for line in st["output"]))
        self.assertIn("--dash-host 127.0.0.1", st["output"][0])
        log = self.log.read_text()
        self.assertIn("ARM: taken from the dashboard capture button (local)", log)
        self.assertIn("ARM: released (sort.py exited, rc 0)", log)

    def test_stop_terminates_local_run(self):
        import os
        os.environ["FAKE_S"] = "30"
        try:
            self.runner.start(self.spec)
            time.sleep(0.3)
            self.runner.stop()
            self.wait_end()
        finally:
            os.environ.pop("FAKE_S")
        self.assertNotEqual(self.runner.status()["run"]["rc"], 0)
        self.assertIn("ARM: released", self.log.read_text())


class Endpoints(unittest.TestCase):
    def serve(self, runner):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Hub(None), runner=runner))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    def post(self, url, body, headers=None):
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_disabled_without_runner(self):
        base = self.serve(None)
        with urllib.request.urlopen(base + "/api/run/status") as r:
            self.assertEqual(json.loads(r.read()), {"enabled": False})
        self.assertEqual(self.post(base + "/api/run/start", {})[0], 403)

    def test_start_validation_and_cross_origin(self):
        runner = Runner(FakeHub(), root=Path(tempfile.mkdtemp()), log_path=Path(tempfile.mkdtemp()) / "log",
                        other_sorter=lambda: False)
        base = self.serve(runner)
        code, data = self.post(base + "/api/run/start", {"kind": "capture"})
        self.assertEqual(code, 400)
        self.assertIn("E-stop", data["error"])
        code, _ = self.post(base + "/api/run/start", {"kind": "capture", "estop_confirmed": True},
                            {"Origin": "http://evil.example"})
        self.assertEqual(code, 403)


if __name__ == "__main__":
    unittest.main()
