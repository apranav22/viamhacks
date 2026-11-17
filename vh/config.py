"""Every constant the baseline pipeline uses. Any of them can be overridden with an
environment variable of the same name, e.g. `CAM_HOVER_MM=300 python run.py pick`.

Units: mm, degrees, seconds. World frame = the arm base (z up, table top at TABLE_Z).
Values marked MEASURE need a bring-up test on the station before they're trusted.
"""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- Connection --------------------------------------------------------------------------
API_KEY_FILE = ROOT / "api-key.json"   # {"address", "api_key", "api_key_id"} (gitignored)

# --- Resource names (machine config) --------------------------------------------------------
ARM = "arm"
GRIPPER = "gripper"
CAM = "cam"                 # wrist RealSense, color + aligned depth
MOTION = "builtin"
HOME_SWITCH = "home-pose"   # erh:vmodutils:arm-position-saver; its saved joints are our watch pose

# --- Scene --------------------------------------------------------------------------------
TABLE_Z = -4.0              # measured: 31 table pixels -> world z = -4 ± 5 mm
WORKSPACE = {"x": (150.0, 650.0), "y": (-350.0, 350.0)}   # refuse targets outside (arm reach + table)
TABLE_OBSTACLE_MARGIN = 6.0  # the planner's table box top sits this far below TABLE_Z (gripper geometry slack)

# --- Perception -------------------------------------------------------------------------
SAT_MIN = 0.22              # saturation above this = not white table (zinc parts are cyan, tape is blue)
DARK_DELTA = 0.28           # this much darker than the table's median brightness = not table
REF_DIFF = 0.12             # per-pixel difference from the empty-table reference that counts as "changed"
MIN_ITEM_PX_WATCH = 40      # blob size limits at the watch pose (~1.06 mm/px)
MAX_ITEM_PX_WATCH = 6000
MIN_ITEM_PX_HOVER = 150     # at the hover pose (~0.43 mm/px)
MASK_RECTS = [[430, 430, 640, 480]]   # [x0, y0, x1, y1] px always ignored (gripper finger at the watch pose)
STABLE_FRAMES = 2           # consecutive frames with the item in the same place = "placed, hand gone"
STABLE_PX = 4.0             # max centroid drift between those frames
HAND_PX = 2500              # a blob this big touching the image border = a hand/arm in view

# --- Motion -------------------------------------------------------------------------------
CAM_HOVER_MM = 260          # the hover look: camera this high above the table, looking straight down
PREGRASP_MM = 80            # gripper this far above the grasp height before the straight descent
LIFT_MM = 120               # straight lift after the grab
MIN_TIP_CLEARANCE = 2.0     # fingertips never commanded closer than this to the table
TCP_TIP_OFFSET_MM = 0.0     # MEASURE: fingertip distance past the gripper frame origin along the tool axis
JAW_AXIS = "x"              # MEASURE: gripper-frame axis the jaws open along ("x" or "y")
LINEAR_TOL_MM = 5.0         # straight-line tolerance for the descent and the lift
MOVE_TIMEOUT_S = 30.0

# --- Gripper ------------------------------------------------------------------------------
GRIP_EMPTY_POS = 15         # jaw position (0-850, ~0.1 mm) at or below this after grab() = closed on nothing
GRASP_RETRIES = 2           # L2 recovery: re-look and retry this many times after an empty grab

# --- Telemetry (dashboard) -----------------------------------------------------------------
TELEMETRY_HOST = "127.0.0.1"  # where dashboard/server.py listens (UDP); the station itself by default
TELEMETRY_PORT = 8766
TELEMETRY = True

# --- Logs ---------------------------------------------------------------------------------
RUNS_DIR = ROOT / "runs"


def _override(name, value):
    raw = os.environ.get(name)
    if raw is None:
        return value
    if isinstance(value, Path):
        return Path(raw)
    if isinstance(value, bool):
        return raw.lower() in ("1", "true", "yes")
    if isinstance(value, (int, float)):
        return type(value)(raw)
    if isinstance(value, (dict, list)):
        return json.loads(raw)
    return raw


for _k, _v in list(globals().items()):
    if _k.isupper():
        globals()[_k] = _override(_k, _v)
