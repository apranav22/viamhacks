"""[codex/unknown · op Ali (git: Ali, github: Armib20) · Mac.mynetworksettings.com · ali/judges-presentation · 2026-11-14]
Curate real images and evidence into a portable, read-only presentation. No robot imports.
Run from the repo: ../sorter/.venv/bin/python presentation/prepare_assets.py
"""
import hashlib
import json
import statistics
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vh.anomaly import model_crop

DEST = ROOT / "site/img"
MANIFEST = []


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def curate(name, source, box=None, policy=None):
    path = ROOT / source
    im = Image.open(path).convert("RGB")
    transform = "Full saved frame, resized only"
    if policy:
        im, crop = model_crop(im, box, "top", policy=policy)
        transform = {"policy": policy, "bbox": box, "crop": crop}
    elif box:
        im = im.crop(box)
        transform = {"display_crop": box, "note": "Display crop; not model preprocessing"}
    im.thumbnail((1600, 1000), Image.Resampling.LANCZOS)
    target = DEST / f"judges-{name}.jpg"
    im.save(target, quality=93)
    MANIFEST.append({"asset": target.name, "source": source,
                     "source_sha256": digest(path), "asset_sha256": digest(target),
                     "transform": transform})
    return target.name


def decision(run, item):
    source = ROOT / "runs" / run / "decisions.jsonl"
    return next(json.loads(line) for line in source.read_text().splitlines()
                if json.loads(line)["item"] == item)


def main():
    DEST.mkdir(exist_ok=True)
    replay_path = ROOT / "runs/_analysis/curated-candidate-top-replay.json"
    replay = json.loads(replay_path.read_text())
    rows = replay["rows"]
    live_run, live_item = "20261113_173234_sort", "item_002"
    folder = f"runs/{live_run}/{live_item}"
    meta = json.loads((ROOT / folder / "meta.json").read_text())
    live = decision(live_run, 2)
    assets = {
        "watch": curate("watch", folder + "/watch.jpg"),
        "top": curate("top", folder + "/top_1.jpg"),
        "held": curate("held", folder + "/web_front.jpg"),
        "heldCrop": curate("held-crop", folder + "/crop_front.jpg"),
        "detail": curate("detail", folder + "/top_1.jpg", meta["top"]["top_1"]["bbox"]),
    }
    examples = {}
    for name, pick in {"marker": "20261113_171810_collect/item_004",
                       "miss": "20261113_173029_collect/item_001"}.items():
        row = next(r for r in rows if r["pick"] == pick)
        source = f"runs/{pick}/{row['file']}"
        assert digest(ROOT / source) == row["image_sha256"], source
        examples[name] = {**row,
            "image": curate(name, source, row["bbox"]),
            "modelImage": curate(name + "-model", source, row["bbox"], replay["crop_policy"]),
            "original": decision(*[pick.split('/')[0], int(pick.split('_')[-1])])}
    good_examples = [r for r in rows if r["label"] == "good" and r["split"] == "train"][:6]
    good_images = []
    for i, row in enumerate(good_examples):
        source = f"runs/{row['pick']}/{row['file']}"
        assert digest(ROOT / source) == row["image_sha256"]
        good_images.append(curate(f"normal-{i}", source, row["bbox"], replay["crop_policy"]))
    test = [r for r in rows if r["split"] == "test"]
    groups = {}
    for label in ["good", "tape", "marker", "other"]:
        group = [r for r in test if r["label"] == label]
        groups[label] = {"total": len(group),
            "flagged": sum(r["routed"].get("anomalous") is True for r in group),
            "clear": sum(r["routed"].get("anomalous") is False for r in group),
            "unknown": sum(r["routed"]["status"] != "ok" for r in group),
            "oracleFlagged": sum(r["oracle"].get("anomalous") is True for r in group)}
    timings = sorted(r["routed"]["infer_ms"] for r in rows if r["routed"]["status"] == "ok")
    # Every displayed score is pinned to the original image bytes, including aggregate rows.
    for row in rows:
        assert digest(ROOT / f"runs/{row['pick']}/{row['file']}") == row["image_sha256"]
    data = {"identity": "codex/unknown; operator Ali (git: Ali, github: Armib20); host Mac.mynetworksettings.com; branch ali/judges-presentation",
        "assets": assets, "live": {"pick": f"{live_run}/{live_item}", "decision": live,
        "bbox": meta["top"]["top_1"]["bbox"], "meta": meta},
        "examples": examples, "normalImages": good_images, "groups": groups,
        "timing": {"n": len(timings), "median": statistics.median(timings),
                   "p95": timings[min(len(timings)-1, int(len(timings)*0.95))]},
        "replay": {k: v for k, v in replay.items() if k != "rows"},
        "replay_sha256": digest(replay_path), "manifest": MANIFEST,
        "sources": [
            {"name": "Viam Overview", "path": "[Edge of Intelligence] Viam Overview.pdf", "page": 6,
             "sha256": digest(Path('/Users/alirizwan/Downloads/[Edge of Intelligence] Viam Overview.pdf'))},
            {"name": "Edge of Intelligence reference sheet", "path": "Edge of Intelligence - reference sheet.pdf", "pages": [9,10],
             "sha256": digest(Path('/Users/alirizwan/Downloads/Edge of Intelligence - reference sheet.pdf'))},
            {"path": "docs/TRAINING_RUN_20261114.md", "sha256": digest(ROOT / 'docs/TRAINING_RUN_20261114.md')},
            {"path": "docs/THRESHOLD_FINDINGS.md", "sha256": digest(ROOT / 'docs/THRESHOLD_FINDINGS.md')},
            {"path": "docs/DAY1_RECAP.md", "sha256": digest(ROOT / 'docs/DAY1_RECAP.md')} ]}
    (ROOT / "presentation/src/evidence.json").write_text(json.dumps(data, indent=2) + "\n")
    (ROOT / "presentation/public/evidence.json").write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({"assets": len(MANIFEST), "groups": groups, "timing": data['timing']}, indent=2))


if __name__ == "__main__":
    main()
