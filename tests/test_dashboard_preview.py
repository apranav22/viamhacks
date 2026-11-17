"""Offline preview contract tests; no SDK connection or robot commands."""
import argparse
import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from dashboard import server


class PreviewTests(unittest.IsolatedAsyncioTestCase):
    async def run_preview(self, *, opt_in=False, active=True, transition=False, timeout=False):
        hub = server.Hub(None)
        running = [active]
        hub.run_active = lambda: running[0]
        hub.latest = {"arm_state": {"tcp": []}, "overview-cam": (b"old", {"stale": True})}
        image = types.SimpleNamespace(data=b"jpeg", mime_type="image/jpeg")

        async def capture(**kwargs):
            if transition:
                running[0] = True
            if timeout:
                await asyncio.Future()  # only the preview's wait_for deadline can release this
            return [image], None

        camera = types.SimpleNamespace(get_images=AsyncMock(side_effect=capture))
        arm = Mock()
        grip = Mock()
        robot = types.SimpleNamespace(close=AsyncMock(), transform_pose=AsyncMock())
        client = Mock()
        client.at_address = AsyncMock(return_value=robot)
        wrist, overhead = Mock(), Mock()
        intrinsics = types.SimpleNamespace(from_camera=AsyncMock())
        geometry = AsyncMock()
        modules = {}
        for name in ["viam", "viam.components", "viam.components.arm", "viam.components.camera",
                     "viam.components.gripper", "viam.proto", "viam.proto.common", "viam.robot",
                     "viam.robot.client", "vh.live_detect", "vh.geometry"]:
            modules[name] = types.ModuleType(name)
        modules["viam.components.arm"].Arm = types.SimpleNamespace(from_robot=lambda *a: arm)
        modules["viam.components.gripper"].Gripper = types.SimpleNamespace(from_robot=lambda *a: grip)
        modules["viam.components.camera"].Camera = types.SimpleNamespace(from_robot=lambda *a: camera)
        modules["viam.robot.client"].RobotClient = client
        modules["viam.proto.common"].Pose = Mock()
        modules["viam.proto.common"].PoseInFrame = Mock()
        modules["vh.live_detect"].wrist = wrist
        modules["vh.live_detect"].overhead = overhead
        modules["vh.geometry"].Intrinsics = intrinsics
        modules["vh.geometry"].frame_to_world = geometry
        sleep = AsyncMock(side_effect=asyncio.CancelledError)
        with patch.dict(sys.modules, modules), patch.object(server, "load_creds", return_value={
            "address": "fake", "api_key": "fake", "api_key_id": "fake"
        }), patch.object(server.asyncio, "sleep", sleep), patch.object(server, "PREVIEW_CAMERA_TIMEOUT", 0.01):
            with self.assertRaises(asyncio.CancelledError):
                await server.preview_loop(hub, "unused", ["overview-cam"], 4, opt_in, 1)
        wrist.assert_not_called()
        overhead.assert_not_called()
        intrinsics.from_camera.assert_not_awaited()
        geometry.assert_not_awaited()
        robot.transform_pose.assert_not_awaited()
        self.assertEqual(arm.mock_calls, [])
        self.assertEqual(grip.mock_calls, [])
        return hub, camera, sleep

    async def test_default_yields_without_camera_calls(self):
        hub, camera, _ = await self.run_preview()
        camera.get_images.assert_not_awaited()
        self.assertEqual(hub.events[-1][2]["state"], "paused")

    async def test_opt_in_camera_only_rate_and_no_stale_detection(self):
        hub, camera, sleep = await self.run_preview(opt_in=True)
        camera.get_images.assert_awaited_once_with(filter_source_names=None)
        self.assertEqual(hub.events[0][2]["state"], "run_preview")
        event = hub.events[-1][2]
        self.assertEqual(event["k"], "preview")
        self.assertIsNone(event["det"])
        self.assertEqual(event["det_ms"], 0)
        self.assertEqual(hub.get_frame(event["frame"]["id"]), ("image/jpeg", b"jpeg"))
        self.assertNotIn("arm_state", hub.latest)
        self.assertIsNone(hub.latest["overview-cam"][1])
        self.assertGreater(sleep.call_args.args[0], 0.8)

    async def test_run_start_during_capture_discards_idle_frame(self):
        hub, camera, _ = await self.run_preview(active=False, transition=True)
        camera.get_images.assert_awaited_once()
        self.assertFalse(any(e[2]["k"] == "preview" for e in hub.events))

    async def test_timeout_reports_error(self):
        hub, _, _ = await self.run_preview(opt_in=True, timeout=True)
        self.assertEqual(hub.events[-1][2]["state"], "error")
        self.assertIn("TimeoutError", hub.events[-1][2]["error"])

    def test_fps_validation(self):
        for value in ["0", "-1", "nan", "inf", "-inf"]:
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                server.positive_fps(value)
        with self.assertRaises(argparse.ArgumentTypeError):
            server.run_preview_fps("2.01")
        self.assertEqual(server.run_preview_fps("0.5"), 0.5)
        self.assertEqual(server.run_preview_fps("2"), 2)
        self.assertEqual(server.positive_fps("4"), 4)


if __name__ == "__main__":
    unittest.main()
