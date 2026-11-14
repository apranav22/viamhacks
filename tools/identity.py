"""Runtime identity for calibration notes; unknown fields remain explicit."""
import os
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def identity_line():
    root = Path(__file__).resolve().parents[1]

    def git(*args):
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "unknown"

    agent = os.environ.get("VH_AGENT", "unknown/unknown")
    operator = git("config", "user.name")
    branch = git("branch", "--show-current")
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return f"[{agent} · op {operator} (git: {operator}, github: unknown) · {socket.gethostname()} · {branch} · {timestamp}]"
