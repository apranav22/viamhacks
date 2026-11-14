"""Repository paths and measured configuration. No environment overrides of calibration.

poses.json and checkpoint.json remain the measurement sources of truth.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = str(ROOT)
LOG_DIR = str(ROOT / "logs")
POSES_PATH = str(ROOT / "config" / "poses.json")
POSES = json.loads(Path(POSES_PATH).read_text())
CHECKPOINT = json.loads((ROOT / "config" / "checkpoint.json").read_text())
GRASP = POSES["grasp"]
TABLE_Z = GRASP["table_z"]
