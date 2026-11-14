"""[claude-code/claude-fable-5-2 · op Ali (git: Ali) · Alis-MacBook-Air.local · ali/judges-presentation · 2026-11-14]
Curate the coverage-pipeline figures for the judges deck from saved runs. Read-only: no robot imports.

    ../sorter/.venv/bin/python presentation/prepare_pipeline_assets.py                       # defaults below
    ../sorter/.venv/bin/python presentation/prepare_pipeline_assets.py --pick runs/<run>/item_NNN   # one pick, all six views

Current view set (vh/coverage.py, 2026-11-14 10:50): wrist top + oblique +-45 on the pad; webcam under, end_a, end_b.
Defaults use two picks of the same part type (hex bolt) because no local pick has all six views yet:
wrist views from 20261114_103009_collect/item_002, webcam views from 20261114_104514_collect/item_001.
Outputs are display crops only (not model preprocessing); hashes go to presentation/src/pipeline_assets.json.
"""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "site/img"
WRIST = "runs/20261114_103009_collect/item_002"
WEB = "runs/20261114_104514_collect/item_001"
OUT = []


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def curate(name, source, box=None, size=(1400, 1400)):
    src = ROOT / source
    im = Image.open(src).convert("RGB")
    if box:
        im = im.crop(box)
    im.thumbnail(size, Image.Resampling.LANCZOS)
    target = DEST / f"judges-cov-{name}.jpg"
    im.save(target, quality=92)
    OUT.append({"asset": target.name, "source": source, "source_sha256": sha(src),
                "asset_sha256": sha(target), "display_crop": list(box) if box else None})


def around(cx, cy, w=720, h=540, W=1280, H=720):
    x0 = int(max(0, min(W - w, cx - w / 2)))
    y0 = int(max(0, min(H - h, cy - h / 2)))
    return (x0, y0, x0 + w, y0 + h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pick", help="one pick folder that has all six views; replaces both defaults")
    a = ap.parse_args()
    wrist = web = a.pick.rstrip("/") if a.pick else None
    wrist, web = wrist or WRIST, web or WEB
    meta = json.loads((ROOT / wrist / "meta.json").read_text())
    x0, y0, x1, y1 = meta["top"]["top_1"]["bbox"]
    curate("top", f"{wrist}/top_1.jpg", around((x0 + x1) / 2, (y0 + y1) / 2))
    centres = {"oblique+45": (660, 340), "oblique-45": (700, 370)}      # 103009/item_002, by eye
    for name, out in (("oblique+45", "obl-p"), ("oblique-45", "obl-m")):
        box = (meta.get("oblique", {}).get(name) or {}).get("crop_box")
        c = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2) if box else centres[name] if not a.pick else (640, 360)
        curate(out, f"{wrist}/{name}.jpg", around(*c))
    for v in ["under", "end_a", "end_b"]:
        curate(v, f"{web}/crop_{v}.jpg")
    # 2026-11-13 14:55 webcam DLT: 18 fingertip positions (red dot = closed fingertips), curated earlier
    curate("calib-grid", "site/img/webcam_calib_grid.jpg", size=(1920, 540))
    record = {"identity": "claude-code/claude-fable-5-2; operator Ali (git: Ali); host Alis-MacBook-Air.local; "
                          "branch ali/judges-presentation", "wrist_pick": wrist, "webcam_pick": web, "assets": OUT}
    (ROOT / "presentation/src/pipeline_assets.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps([o["asset"] for o in OUT]))


if __name__ == "__main__":
    main()
