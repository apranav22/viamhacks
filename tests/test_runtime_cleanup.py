"""Offline checks of extracted grasp primitives and deployable source closure."""
import asyncio
import io
import json
import sys
import tarfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vh.motion import Mover, grasp_height, held, table_height, world_state
from vh.kinematics import load_obstacles


class RuntimeCleanupTests(unittest.TestCase):
    def test_grasp_clearance_and_upright_height(self):
        g = {"min_table_clearance_mm": 2, "tcp_to_tip_mm": 20.5, "empty_below_pos": 30, "table_z": -1.3}
        for surface in (-1.3, 6.5):
            self.assertEqual(grasp_height(SimpleNamespace(top_z=surface + 10), surface, g), surface + 22.5)
            self.assertEqual(grasp_height(SimpleNamespace(top_z=surface + 60), surface, g), surface + 50.5)
        self.assertFalse(held(30, g))
        self.assertTrue(held(31, g))
        self.assertIsNone(held(None, g))
        self.assertEqual(table_height(50, g), -1.3)  # depth noise must not replace a touch measurement

    def test_grab_waits_until_fingers_have_moved_and_settled(self):
        mover = Mover.__new__(Mover)
        mover.live, mover.step, mover.first_motion_at = True, False, None
        mover.gripper = SimpleNamespace(grab=AsyncMock())
        mover.finger_pos = AsyncMock(side_effect=[800, 800, 500, 100, 40, 40, 40, 40])
        result = asyncio.run(mover.grab())
        self.assertEqual(result, 40)
        mover.gripper.grab.assert_awaited_once()
        self.assertEqual(mover.finger_pos.await_count, 8)

    def test_dry_grab_never_commands_the_gripper(self):
        mover = Mover.__new__(Mover)
        mover.live, mover.step = False, False
        mover.gripper = SimpleNamespace(grab=AsyncMock())
        mover.finger_pos = AsyncMock()
        self.assertIsNone(asyncio.run(mover.grab()))
        mover.gripper.grab.assert_not_awaited()
        mover.finger_pos.assert_not_awaited()

    def test_planner_and_joint_checker_share_all_fixture_geometry(self):
        for surface in (-1.3, 6.5):
            expected = load_obstacles(table_z=surface)
            actual = world_state(surface).obstacles[0].geometries
            self.assertEqual([g.label for g in actual], [name for name, _ in expected])
            self.assertTrue({"table", "wall-front", "wall-side", "ceiling"}.issubset({g.label for g in actual}))
            self.assertGreaterEqual(len(actual), 7)  # includes tripod, lamp and box
            for geom, (_, (center, dims)) in zip(actual, expected):
                self.assertEqual((geom.center.x, geom.center.y, geom.center.z), tuple(center))
                self.assertEqual((geom.box.dims_mm.x, geom.box.dims_mm.y, geom.box.dims_mm.z), tuple(dims))

    def test_release_contains_supported_imports_and_excludes_secrets_and_prototypes(self):
        from deploy_station import build_archive
        blob, files = build_archive([])
        self.assertTrue({"sort.py", "vh/motion.py", "vh/detection.py", "vh/config.py"}.issubset(files))
        self.assertTrue({"pipeline.py", "run.py", "api-key.json", "config/current.json", "config/additions.json"}.isdisjoint(files))
        self.assertFalse(any(p.startswith(("archive/", "logs/", "models/")) for p in files))
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
            manifest = json.load(archive.extractfile("DEPLOYMENT_MANIFEST.json"))
            self.assertEqual(manifest["files"], files)
            self.assertEqual(len(manifest["source_commit"]), 40)
            for name in files:
                if name.endswith(".py"):
                    compile(archive.extractfile(name).read(), name, "exec")


if __name__ == "__main__":
    unittest.main()
