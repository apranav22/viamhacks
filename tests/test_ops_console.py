"""ops/console.py arm/confirm/preflight logic with a fake station: nothing connects, nothing starts."""
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops"))
import console  # noqa: E402


class FakeStation:
    def __init__(self, reply):
        self.reply, self.cmds = reply, []

    def sh(self, cmd, timeout=30):
        self.cmds.append(cmd)
        return 0, self.reply


def make(reply):
    c = console.Console.__new__(console.Console)
    c.st, c.python = FakeStation(reply), sys.executable
    c.presets = {"judged": {"title": "j", "args": ["--mode", "sort", "--type-clf", "x"]}}
    import threading
    c.lock, c.armed, c.job, c.cache, c.snaps = threading.Lock(), None, None, {}, {}
    return c


class TestConsole(unittest.TestCase):
    def setUp(self):
        self.run = mock.patch.object(console.subprocess, "run", side_effect=AssertionError("must not start")).start()
        mock.patch.object(console.Console, "log", lambda *a, **k: None).start()

    def tearDown(self):
        mock.patch.stopall()

    def wait(self, c):
        for _ in range(100):
            if c.job and c.job["ended"]:
                return
            time.sleep(0.01)
        self.fail("job did not end")

    def test_confirm_needs_arm_and_window(self):
        c = make("")
        self.assertEqual(c.confirm()[0], 409)
        c.arm("judged")
        c.armed = ("judged", time.monotonic() - 6)
        self.assertEqual(c.confirm()[0], 409)
        self.assertEqual(c.arm("nope")[0], 409)
        c.arm("judged")
        self.assertEqual(c.confirm("other")[0], 409)

    def test_refuses_when_running(self):
        c = make("12345\nALREADY_RUNNING")
        c.arm("judged")
        self.assertEqual(c.confirm()[0], 200)
        self.wait(c)
        self.assertEqual(c.job["rc"], 2)
        self.assertIn("ALREADY_RUNNING", c.job["output"])

    def test_refuses_unknown_flag_and_checks_every_flag(self):
        c = make("MISSING --type-clf")
        c.arm("judged")
        c.confirm("judged")
        self.wait(c)
        self.assertEqual(c.job["rc"], 2)
        self.assertIn("'\"--type-clf\"'", c.st.cmds[0])
        self.assertIn("'\"--mode\"'", c.st.cmds[0])
        self.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
