"""Read-only station recovery: transfer integrity and same-name model preservation."""
import asyncio
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import recover_station as recovery
from viam.proto.service.shell import CopyFilesFromMachineResponse, FileData


class DownloadStream:
    def __init__(self):
        self.sent = []
        self.ended = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def send_message(self, request):
        self.sent.append(request)

    async def end(self):
        self.ended = True

    def __aiter__(self):
        async def responses():
            yield CopyFilesFromMachineResponse(file_data=FileData(name="model.bin", data=b"ab"))
            yield CopyFilesFromMachineResponse(file_data=FileData(data=b"c", eof=True))
        return responses()


class StationRecoveryTests(unittest.TestCase):
    def test_download_checks_complete_bytes_and_acknowledges_eof(self):
        stream = DownloadStream()
        stub = SimpleNamespace(CopyFilesFromMachine=SimpleNamespace(open=lambda **kwargs: stream))
        entry = {"path": "/opt/viam/sorter-ali/models/example/model.bin", "size": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}
        with patch.object(recovery, "ShellServiceStub", return_value=stub):
            data = asyncio.run(recovery.read_file(SimpleNamespace(_channel=object()), entry))
        self.assertEqual(data, b"abc")
        self.assertFalse(stream.sent[0].metadata.allow_recursion)
        self.assertEqual(list(stream.sent[0].metadata.paths), [entry["path"]])
        self.assertTrue(stream.sent[-1].ack_last_file)
        self.assertTrue(stream.ended)

    def test_download_rejects_hash_mismatch(self):
        stream = DownloadStream()
        stub = SimpleNamespace(CopyFilesFromMachine=SimpleNamespace(open=lambda **kwargs: stream))
        entry = {"path": "/model.bin", "size": 3, "sha256": "0" * 64}
        with patch.object(recovery, "ShellServiceStub", return_value=stub):
            with self.assertRaisesRegex(RuntimeError, "changed during recovery"):
                asyncio.run(recovery.read_file(SimpleNamespace(_channel=object()), entry))

    def test_inventory_cannot_escape_the_snapshot(self):
        for category, relative in [("release", "../secret"), ("../outside", "file.py"), ("models", "/tmp/file")]:
            with self.assertRaises(ValueError):
                recovery.destination({"category": category, "relative": relative}, Path("/snapshot"))

    def test_same_name_models_remain_separate_and_archived_source_verifies(self):
        with tempfile.TemporaryDirectory() as td, patch.object(recovery, "ROOT", Path(td).resolve()):
            root = Path(td).resolve()
            archive = root / "archive/station/example"
            archive.mkdir(parents=True)
            files = []
            for category, relative, data in [("release", "sort.py", b"# recovered source\n"),
                                              ("models", "bundle/bundle.json", b'{"models":{}}'),
                                              ("models", "bundle/model.bin", b"station weights")]:
                dest = archive / category / relative
                if relative.endswith(".bin"):
                    dest = root / "models/_station/example" / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                files.append({"category": category, "relative": relative, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            original = root / "models/bundle/model.bin"
            original.parent.mkdir(parents=True)
            original.write_bytes(b"laptop weights")
            (archive / "inventory.json").write_text(json.dumps({"identity": "test", "release": "/station/release", "files": files}))
            recovery.pack_snapshot(archive)
            self.assertEqual(original.read_bytes(), b"laptop weights")
            station = root / "models/_station/example/bundle"
            self.assertEqual((station / "model.bin").read_bytes(), b"station weights")
            self.assertEqual(json.loads((station / "bundle.json").read_text()), {"models": {}})
            report = json.loads((archive / "recovery.json").read_text())
            self.assertEqual(report["verified_files"], 3)
            self.assertEqual(report["conflicting_bundles"], ["bundle"])
            self.assertTrue((archive / "evidence.tar.gz").exists())
            self.assertFalse((archive / "release").exists())


if __name__ == "__main__":
    unittest.main()
