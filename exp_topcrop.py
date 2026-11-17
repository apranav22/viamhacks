"""Offline experiment: top-view PatchCore with the square context crop (v1) vs the rotated masked part crop (v2).
Good-only bank; threshold from good calibration + synthetic defects; tested on held-out goods and REAL taped parts.
No robot. python exp_topcrop.py
"""
import glob
import json
import os
import random
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

import os
ROOT = Path(os.environ.get("EXP_ROOT") or Path(__file__).resolve().parent)
sys.path.insert(0, str(ROOT))
from vh.anomaly import context_crop, part_crop  # noqa: E402

SIZE = {"v1": 256, "v2": 320}
GOOD_RUNS = ["20261113_173414_collect", "20261113_173900_collect", "20261113_175140_collect",
             "20261113_181752_collect", "20261113_183403_collect", "20261113_185701_collect"]
BACKBONE = os.environ.get("EXP_BACKBONE", "resnet18")
DEVICE = os.environ.get("EXP_DEVICE", "cpu")
PER_TYPE = os.environ.get("EXP_PER_TYPE") == "1"
LAYERS = os.environ.get("EXP_LAYERS", "layer2,layer3").split(",")
HB, M16, BTN = "hex_bolt_partial", "socket_m16", "button_ss_long"
REAL_DEFECT = [("20261113_180637_sort", 2, HB), ("20261113_180637_sort", 3, HB), ("20261113_181214_sort", 1, HB),
               ("20261113_181214_sort", 2, HB), ("20261113_184840_sort", 2, HB), ("20261113_184840_sort", 3, HB),
               ("20261113_184840_sort", 5, M16), ("20261113_184840_sort", 6, BTN)]
REAL_GOOD = [("20261113_180637_sort", 1, HB), ("20261113_181214_sort", 3, HB), ("20261113_184840_sort", 1, BTN),
             ("20261113_184840_sort", 4, M16)]


def top(run, i):
    d = ROOT / "runs" / run / f"item_{i:03d}"
    m = json.loads((d / "meta.json").read_text())
    return d / "top_1.jpg", m["top"]["top_1"]["bbox"]


def good_picks():
    out = []
    for run in GOOD_RUNS:
        rd = ROOT / "runs" / run
        excl = json.loads((rd / "exclude.json").read_text()) if (rd / "exclude.json").exists() else {}
        for line in (rd / "decisions.jsonl").read_text().splitlines():
            r = json.loads(line)
            if r.get("decision") != "collect" or f"item_{r['item']:03d}" in excl:
                continue
            try:
                p, b = top(run, r["item"])
            except (KeyError, TypeError, FileNotFoundError):
                continue
            if b and Image.open(p).size == (1280, 720):
                out.append((run, r["item"], r.get("type") or json.loads((p.parent / "meta.json").read_text())["type"]))
    return out


def crop(version, run, i):
    p, b = top(run, i)
    if version == "v1":
        return context_crop(p, b)[0].resize((SIZE["v1"],) * 2, Image.Resampling.BILINEAR)
    return part_crop(p, b, out=SIZE["v2"])[0]


def synth(img, kind, rng):
    """Paste a tape band / marker stroke onto the part (non-grey pixels) of a v2 crop."""
    a = np.asarray(img).astype(np.float32).copy()
    part = np.abs(a - 128).sum(-1) > 12
    ys, xs = np.nonzero(part)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    L = x1 - x0
    cx = rng.uniform(x0 + 0.1 * L, x1 - 0.1 * L)
    w = rng.uniform(0.08, 0.2) * L if kind == "tape" else rng.uniform(0.02, 0.05) * L
    band = np.zeros_like(part)
    band[:, int(cx - w / 2):int(cx + w / 2) + 1] = True
    if kind == "marker":   # short stroke, not the full width
        yy = rng.uniform(y0, y1)
        band[: int(max(0, yy - 0.3 * (y1 - y0)))] = False
        band[int(yy + 0.3 * (y1 - y0)):] = False
    region = band & part
    col = np.array([30, 95, 175]) if kind == "tape" else np.array([35, 35, 40])
    shade = a[region].mean(-1, keepdims=True) / 160.0
    a[region] = np.clip(col * shade + rng.normal(0, 6, (region.sum(), 3)), 0, 255)
    return Image.fromarray(a.astype(np.uint8))


def model_scores(train_imgs, size):
    from anomalib.models.image.patchcore.torch_model import PatchcoreModel
    torch.manual_seed(17)
    m = PatchcoreModel(layers=LAYERS, backbone=BACKBONE, pre_trained=True, num_neighbors=1).to(DEVICE)
    for p in m.parameters():
        p.requires_grad_(False)
    mean = torch.tensor([0.485, 0.456, 0.406]).reshape(1, 3, 1, 1).to(DEVICE)
    std = torch.tensor([0.229, 0.224, 0.225]).reshape(1, 3, 1, 1).to(DEVICE)
    t = lambda im: (torch.from_numpy(np.asarray(im.resize((size, size)), np.float32).transpose(2, 0, 1)[None] / 255).to(DEVICE) - mean) / std
    m.train(); m.feature_extractor.eval()
    with torch.no_grad():
        for im in train_imgs:
            m(t(im))
    m.embedding_store = [e.cpu() for e in m.embedding_store]
    m.cpu()
    m.subsample_embedding(sampling_ratio=0.1)
    m.to(DEVICE)
    m.eval()

    def score(im):
        with torch.no_grad():
            return float(m(t(im)).pred_score.reshape(-1)[0])
    return score


def main():
    from sklearn.metrics import roc_auc_score
    rng = random.Random(17)
    picks = good_picks()
    rng.shuffle(picks)
    n = len(picks)
    cal, test, train = picks[: n // 5], picks[n // 5: 2 * n // 5], picks[2 * n // 5:]
    test = test + REAL_GOOD
    print(f"{BACKBONE} {LAYERS} per_type={PER_TYPE} dev={DEVICE}: train {len(train)} cal {len(cal)} test good {len(test)} real defect {len(REAL_DEFECT)}", flush=True)
    im = lambda p: crop("v2", p[0], p[1])
    types = sorted({p[2] for p in picks}) if PER_TYPE else ["*"]
    g_cal, g_test, d_real = [], [], []
    for ty in types:
        sel = (lambda p: True) if ty == "*" else (lambda p, ty=ty: p[2] == ty)
        score = model_scores([im(p) for p in train if sel(p)], SIZE["v2"])
        c = [score(im(p)) for p in cal if sel(p)]
        # per-type: normalise by that type's calibration max so one global threshold applies
        norm = max(c) if PER_TYPE else 1.0
        g_cal += [x / norm for x in c]
        g_test += [score(im(p)) / norm for p in test if sel(p)]
        d_real += [(score(im(p)) / norm, p) for p in REAL_DEFECT if sel(p)]
    d = [x for x, _ in d_real]
    auc = roc_auc_score([0] * len(g_test) + [1] * len(d), g_test + d)
    thr = max(g_cal) * 1.02
    print(f"  AUROC good-test vs real tape {auc:.3f} | good test max {max(g_test):.3f} p50 {np.median(g_test):.3f} | tape {sorted(round(x, 3) for x in d)}")
    print(f"  @thr=1.02*cal max {thr:.3f}: good FR {sum(x >= thr for x in g_test)}/{len(g_test)}, tape caught {sum(x >= thr for x in d)}/{len(d)}")
    print(f"  tape above every good test score: {sum(x > max(g_test) for x in d)}/{len(d)}; missed: "
          + str([(p[0][-12:], p[1], round(x, 3)) for x, p in d_real if x < thr]), flush=True)


if __name__ == "__main__":
    main()
