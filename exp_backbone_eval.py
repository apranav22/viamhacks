"""Offline backbone comparison for the anomaly banks: ResNet-18 PatchCore features vs DINOv2 patch features.

python exp_backbone_eval.py --runs runs/*_collect --background cardboard --out exp/backbone_eval
python exp_backbone_eval.py --runs runs/*_collect --background cardboard --views top --backbones dinov2_s

Saved images only. NO robot connection, no model activation, no threshold change in any bundle.
Uses the same crops as training and live inference (vh.anomaly.model_crop) and the same groups
(part type x held pose x view x background).

Protocol (the point of this script):
- Specimen proxy = collection run. A collect run grabs the same physical part repeatedly, so a held-out pick
  from the same run is NOT independent. Good picks are scored with a bank built from OTHER runs of the
  same type only (leave-one-run-out). Groups with a single good run fall back to leave-one-pick-out and are
  flagged `same_specimen` in the report.
- Defect picks are scored against a bank of all good picks of their type.
- Thresholds come from good scores only. Misses use max(out-of-run good) * margin. False rejects for run R use a
  threshold computed without run R. Defect picks never set a threshold.
- No coreset: exact nearest neighbour, i.e. the best case for PatchCore's bank. Both backbones get the same
  flip augmentation of the bank (canonical crops have a 180 degree ambiguity).

Image score: mean of the top 1% patch nearest-neighbour distances (`top1`), and the max (`max`, PatchCore's
definition). Both are reported; `--aggregate` picks the one used for decisions.
Known-defect probe: logistic regression on frozen image embeddings, grouped by run. It names known defects; it is
reported separately and never used to call a part good.
"""
import argparse
import glob
import json
import platform
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from vh.anomaly import CROP_POLICY, group_key, model_crop
from vh.anomaly_data import collect_samples

MEAN = np.array([0.485, 0.456, 0.406], np.float32).reshape(3, 1, 1)
STD = np.array([0.229, 0.224, 0.225], np.float32).reshape(3, 1, 1)
MARGINS = (1.0, 1.03, 1.15)


# ---------------------------------------------------------------- data

def load_records(run_dirs, background, views):
    records, skipped = collect_samples(run_dirs, "each", background)
    if views:
        records = [r for r in records if r["view"] in views]
    tops = [r for r in records if r["view"] == "top"]
    if tops:  # same rule as vh.anomaly_data.build_dataset: never mix wrist resolutions
        def size(r):
            with Image.open(r["image"]) as im:
                return im.size
        newest = size(max(tops, key=lambda r: Path(r["image"]).stat().st_mtime))
        for r in list(tops):
            if size(r) != newest:
                records.remove(r)
                skipped.append({"pick": r["pick_id"], "view": "top", "reason": f"wrist frame {size(r)} != {newest}"})
    out = []
    for r in records:
        try:
            crop, _ = model_crop(r["image"], r["bbox"], r["view"])
        except (ValueError, OSError) as e:
            skipped.append({"pick": r["pick_id"], "view": r["view"], "reason": str(e)})
            continue
        if r.get("label") in (None, "", "unknown"):
            skipped.append({"pick": r["pick_id"], "view": r["view"], "reason": "no label"})
            continue
        r = dict(r, run=Path(r["source_run"]).name, crop=crop.convert("RGB"),
                 group=group_key(r["part_type"], r["pose"], r["view"], r["background"]))
        out.append(r)
    return out, skipped


# ---------------------------------------------------------------- backbones

class Backbone:
    name = "?"
    metric = "l2"

    def __init__(self, size, device):
        self.size, self.device = size, device

    def tensor(self, images):
        import torch
        arr = [((np.asarray(im.resize((self.size, self.size), Image.Resampling.BILINEAR), np.float32)
                 .transpose(2, 0, 1) / 255) - MEAN) / STD for im in images]
        return torch.from_numpy(np.stack(arr)).to(self.device)

    def embed(self, images):
        """-> (patches [B, P, D] float32, image embedding [B, E] float32)"""
        raise NotImplementedError


class ResNetPatchCore(Backbone):
    """Anomalib PatchCore features: ResNet-18 layer2 + layer3, 3x3 local average, layer3 upsampled to layer2."""
    name, metric = "resnet18_patchcore", "l2"

    def __init__(self, size, device, pretrained=True):
        super().__init__(size, device)
        import torchvision
        weights = torchvision.models.ResNet18_Weights.IMAGENET1K_V1 if pretrained else None
        self.net = torchvision.models.resnet18(weights=weights).eval().to(device)

    def embed(self, images):
        import torch
        import torch.nn.functional as F
        n = self.net
        with torch.no_grad():
            x = n.maxpool(n.relu(n.bn1(n.conv1(self.tensor(images)))))
            l2 = n.layer2(n.layer1(x))
            l3 = n.layer3(l2)
            l2, l3 = (F.avg_pool2d(f, 3, 1, 1) for f in (l2, l3))
            f = torch.cat([l2, F.interpolate(l3, size=l2.shape[-2:], mode="bilinear", align_corners=False)], 1)
            emb = torch.cat([F.adaptive_avg_pool2d(n.layer4(l3), 1).flatten(1), f.mean((2, 3))], 1)
        self.grid = tuple(f.shape[-2:])
        return f.flatten(2).transpose(1, 2).float().cpu().numpy(), emb.float().cpu().numpy()


class DinoV2(Backbone):
    """DINOv2 ViT patch tokens (14 px patches), cosine distance."""
    metric = "cos"

    ARCH = {"dinov2_s": ("vit_small_patch14_dinov2.lvd142m", 14), "dinov2_b": ("vit_base_patch14_dinov2.lvd142m", 14),
            "dinov3_s": ("vit_small_patch16_dinov3.lvd1689m", 16), "dinov3_splus": ("vit_small_plus_patch16_dinov3.lvd1689m", 16)}

    def __init__(self, size, device, variant="dinov2_s", pretrained=True):
        arch, patch = self.ARCH[variant]
        super().__init__(size - size % patch, device)
        self.name = variant
        import timm
        self.net = timm.create_model(arch, pretrained=pretrained, img_size=self.size, num_classes=0).eval().to(device)
        self.prefix = getattr(self.net, "num_prefix_tokens", 1)
        self.grid = (self.size // patch, self.size // patch)

    def embed(self, images):
        import torch
        with torch.no_grad():
            tok = self.net.forward_features(self.tensor(images))
            patches, cls = tok[:, self.prefix:], tok[:, 0]
            emb = torch.cat([cls, patches.mean(1)], 1)
        return patches.float().cpu().numpy(), emb.float().cpu().numpy()


def make_backbone(name, device, pretrained, sizes):
    if name == "resnet18":
        return ResNetPatchCore(sizes["resnet18"], device, pretrained)
    if name in DinoV2.ARCH:
        return DinoV2(sizes["dinov2"], device, name, pretrained)
    raise ValueError(name)


def features(backbone, records, batch=8, augment=True):
    """Cache patches for each crop and its flips (bank augmentation). Returns per-record dict and ms/crop."""
    out, times = {}, []
    for i in range(0, len(records), batch):
        chunk = records[i:i + batch]
        ims = [r["crop"] for r in chunk]
        start = time.perf_counter()
        p, e = backbone.embed(ims)
        times.append((time.perf_counter() - start) * 1000 / len(chunk))
        k = len(chunk)
        if augment:
            flips = [im.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for im in ims] + \
                    [im.transpose(Image.Transpose.FLIP_TOP_BOTTOM) for im in ims] + \
                    [im.transpose(Image.Transpose.ROTATE_180) for im in ims]
            pf, _ = backbone.embed(flips)
        for j, r in enumerate(chunk):
            if LOCAL_R:
                # position-aware: keep the patch grid; only the top-bottom flip keeps part-top-v2's head-left layout
                aug = np.stack([p[j], pf[k + j]]) if augment else p[j][None]
            else:
                aug = np.concatenate([p[j], pf[j], pf[k + j], pf[2 * k + j]]) if augment else p[j]
            if backbone.metric == "cos":
                p_j = p[j] / np.linalg.norm(p[j], axis=-1, keepdims=True)
                aug = aug / np.linalg.norm(aug, axis=-1, keepdims=True)
            else:
                p_j = p[j]
            out[id(r)] = {"query": p_j.astype(np.float32), "bank": aug.astype(np.float32), "emb": e[j]}
        print(f"  {backbone.name}: {min(i + batch, len(records))}/{len(records)} crops", flush=True)
    return out, float(np.median(times)) if times else None


LOCAL_R = 0        # --local-radius: 0 = match any bank patch; R = only bank patches within R grid cells of the same spot
GRID = None        # (H, W) patch grid of the current backbone, set in main()


def nn_dist_local(query, bank, metric, r=None, grid=None):
    """Nearest bank patch per query patch, searching only a (2R+1)^2 window around the same grid position.
    query [H*W, C]; bank [N, H*W, C] (aligned part-top-v2 crops)."""
    import torch
    import torch.nn.functional as F
    r, (H, W) = r or LOCAL_R, grid or GRID
    q = torch.from_numpy(query).view(H, W, -1)
    b = torch.from_numpy(bank).view(-1, H, W, q.shape[-1])
    qq = (q * q).sum(-1)
    best = torch.full((H, W), float("inf"))
    for s in range(0, b.shape[0], 16):
        bp = F.pad(b[s:s + 16].permute(0, 3, 1, 2), (r, r, r, r), value=float("nan")).permute(0, 2, 3, 1)
        for di in range(2 * r + 1):
            for dj in range(2 * r + 1):
                sh = bp[:, di:di + H, dj:dj + W]
                dot = (sh * q).sum(-1)
                d = 1 - dot if metric == "cos" else (qq + (sh * sh).sum(-1) - 2 * dot).clamp_min(0).sqrt()
                best = torch.minimum(best, torch.nan_to_num(d, nan=float("inf")).min(0).values)
    return best.flatten().numpy()


def nn_dist(query, bank, metric):
    if LOCAL_R:
        return nn_dist_local(query, bank, metric)
    import torch
    q, b = torch.from_numpy(query), torch.from_numpy(bank)
    best = []
    for s in range(0, len(q), 512):
        qc = q[s:s + 512]
        if metric == "cos":
            d = 1 - (qc @ b.T).max(1).values
        else:
            d2 = (qc * qc).sum(1, keepdim=True) + (b * b).sum(1)[None] - 2 * qc @ b.T
            d = d2.min(1).values.clamp_min(0).sqrt()
        best.append(d)
    return torch.cat(best).numpy()


def aggregate(dist):
    k = max(1, int(round(len(dist) * 0.01)))
    return {"top1": float(np.sort(dist)[-k:].mean()), "max": float(dist.max())}


# ---------------------------------------------------------------- protocol

def auroc(good, bad):
    if not good or not bad:
        return None
    g, b = np.asarray(good), np.asarray(bad)
    return float(((b[:, None] > g[None]).sum() + 0.5 * (b[:, None] == g[None]).sum()) / (len(g) * len(b)))


def score_group(recs, feats, metric, agg):
    good = [r for r in recs if r["label"] == "good"]
    bad = [r for r in recs if r["label"] != "good"]
    runs = sorted({r["run"] for r in good})
    same_specimen = len(runs) < 2
    bank_of = lambda rs: np.concatenate([feats[id(r)]["bank"] for r in rs]) if rs else None
    scores = {}
    for r in good:
        others = [g for g in good if (g["pick_id"] != r["pick_id"] if same_specimen else g["run"] != r["run"])]
        if not others:
            continue
        scores[id(r)] = aggregate(nn_dist(feats[id(r)]["query"], bank_of(others), metric))
    full = bank_of(good)
    for r in bad:
        if full is not None:
            scores[id(r)] = aggregate(nn_dist(feats[id(r)]["query"], full, metric))
    g_scores = {id(r): scores[id(r)][agg] for r in good if id(r) in scores}
    result = {"n_good": len(g_scores), "good_runs": runs, "same_specimen": same_specimen,
              "n_defect": defaultdict(int), "auroc": auroc(list(g_scores.values()),
                                                          [scores[id(r)][agg] for r in bad if id(r) in scores]),
              "margins": {}}
    for r in bad:
        result["n_defect"][r["label"]] += 1
    for m in MARGINS:
        thr_all = max(g_scores.values()) * m if g_scores else None
        fr = 0
        for r in good:
            if id(r) not in g_scores:
                continue
            rest = [v for g, v in ((g, g_scores[id(g)]) for g in good if id(g) in g_scores)
                    if (g["pick_id"] != r["pick_id"] if same_specimen else g["run"] != r["run"])]
            if rest and g_scores[id(r)] >= max(rest) * m:
                fr += 1
        misses = defaultdict(int)
        for r in bad:
            if thr_all is None or scores.get(id(r), {}).get(agg, -1) < thr_all:
                misses[r["label"]] += 1
        result["margins"][str(m)] = {"threshold": thr_all, "false_rejects": fr, "misses": dict(misses)}
    result["n_defect"] = dict(result["n_defect"])
    per_pick = {r["pick_id"]: {"label": r["label"], **scores[id(r)]} for r in recs if id(r) in scores}
    return result, per_pick


def probe(records, feats):
    """Known-defect probe per view: good vs tape, leave-one-run-out; then the full tape probe on other families.

    A held-out run whose remaining runs contain no tape is NOT scored (reported as not measurable).
    """
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return {"status": "sklearn not installed"}
    clf = lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.1, class_weight="balanced"))
    out = {}
    for view in sorted({r["view"] for r in records}):
        rs = [r for r in records if r["view"] == view]
        X = np.stack([feats[id(r)]["emb"] for r in rs])
        labels = np.array([r["label"] for r in rs])
        runs = np.array([r["run"] for r in rs])
        if "tape" not in labels or "good" not in labels:
            out[view] = "not measurable: needs good and tape"
            continue
        pred = np.full(len(rs), np.nan)
        for run in sorted(set(runs)):
            tr = (runs != run) & np.isin(labels, ["good", "tape"])
            if len(set(labels[tr])) < 2:
                continue
            pred[runs == run] = clf().fit(X[tr], labels[tr] == "tape").predict_proba(X[runs == run])[:, 1]
        ok = ~np.isnan(pred)
        t, g = ok & (labels == "tape"), ok & (labels == "good")
        v = {"tape_caught": f"{int((pred[t] >= .5).sum())}/{int(t.sum())}",
             "good_flagged": f"{int((pred[g] >= .5).sum())}/{int(g.sum())}",
             "tape_not_measurable": int(((labels == "tape") & ~ok).sum())}
        tr = np.isin(labels, ["good", "tape"])
        m = clf().fit(X[tr], labels[tr] == "tape")
        for f in sorted(set(labels) - {"good", "tape"}):
            pf = m.predict_proba(X[labels == f])[:, 1]
            v[f"tape_probe_flags_{f}"] = f"{int((pf >= .5).sum())}/{len(pf)}"
        out[view] = v
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", nargs="+", required=True, help="run folders or globs (collect runs)")
    p.add_argument("--background", default="cardboard", choices=["white", "cardboard"])
    p.add_argument("--views", nargs="*", default=None, help="limit views, e.g. top front")
    p.add_argument("--backbones", nargs="+", default=["resnet18", "dinov2_s"], choices=["resnet18", "dinov2_s", "dinov2_b", "dinov3_s", "dinov3_splus"])
    p.add_argument("--resnet-size", type=int, default=320, help="train_anomaly.py default")
    p.add_argument("--dino-size", type=int, default=448)
    p.add_argument("--aggregate", default="top1", choices=["top1", "max"])
    p.add_argument("--device", default="cpu", help="torch device: cpu or xpu")
    p.add_argument("--benchmark", type=Path, default=Path("config/benchmarks/development-v1.json"))
    p.add_argument("--no-augment", action="store_true", help="skip flipped bank copies (4x faster, weaker bank)")
    p.add_argument("--no-pretrained", action="store_true", help="smoke test only: random weights")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--local-radius", type=int, default=0, help="position-aware kNN: match only within R patch cells (aligned crops)")
    a = p.parse_args()
    global LOCAL_R, GRID
    LOCAL_R = a.local_radius
    dirs = sorted({d for pat in a.runs for d in (glob.glob(pat) or [pat]) if (Path(d) / "decisions.jsonl").exists()})
    if not dirs:
        raise SystemExit("No run folders with decisions.jsonl")
    a.out.mkdir(parents=True, exist_ok=True)
    records, skipped = load_records(dirs, a.background, set(a.views) if a.views else None)
    if not records:
        raise SystemExit("No usable samples; check --background and the runs' meta.json")
    groups = defaultdict(list)
    for r in records:
        groups[r["group"]].append(r)
    print(f"{len(records)} crops, {len({r['pick_id'] for r in records})} picks, {len(dirs)} runs, "
          f"{len(groups)} groups, {len(skipped)} skipped", flush=True)
    bench = {}
    if a.benchmark.exists():
        bench = {m["pick"]: m["label"] for m in json.loads(a.benchmark.read_text())["members"]}
    import torch
    torch.set_num_threads(max(1, torch.get_num_threads()))
    report = {"host": platform.node(), "augment": not a.no_augment, "device": a.device, "crop_policy": CROP_POLICY, "background": a.background, "aggregate": a.aggregate,
              "runs": [Path(d).name for d in dirs], "skipped": skipped, "backbones": {}}
    for name in a.backbones:
        bb = make_backbone(name, a.device, not a.no_pretrained, {"resnet18": a.resnet_size, "dinov2": a.dino_size})
        print(f"BACKBONE {bb.name} input {bb.size}px metric {bb.metric}", flush=True)
        feats, ms = features(bb, records, augment=not a.no_augment)
        GRID = bb.grid
        res = {"input_px": bb.size, "metric": bb.metric, "torch_ms_per_crop": ms, "groups": {}, "picks": {}}
        for key, recs in sorted(groups.items()):
            g, per_pick = score_group(recs, feats, bb.metric, a.aggregate)
            res["groups"][key] = g
            view = key.split("|")[2]
            for pick, v in per_pick.items():
                res["picks"].setdefault(pick, {})[view] = {**v, "threshold": {m: g["margins"][str(m)]["threshold"] for m in MARGINS}}
        # whole-pick anomaly-only decision: reject if any scored view >= its view threshold
        fused = {}
        for m in MARGINS:
            c = defaultdict(int)
            for pick, views in res["picks"].items():
                label = next(iter(views.values()))["label"]
                rej = any(v["threshold"][m] is not None and v[a.aggregate] >= v["threshold"][m] for v in views.values())
                c[("FR" if rej else "TN") if label == "good" else ("TP" if rej else "FN")] += 1
            fused[str(m)] = dict(c)
        res["whole_pick"] = fused
        dev = {}
        for m in MARGINS:  # top-view decisions on the frozen development-v1 picks (labels from the benchmark file)
            c = {"TP": 0, "FN": 0, "FR": 0, "TN": 0}
            for pk, lab in bench.items():
                v = res["picks"].get(pk, {}).get("top")
                if v is None or v["threshold"][m] is None:
                    continue
                rej = v[a.aggregate] >= v["threshold"][m]
                c[("FR" if rej else "TN") if lab == "good" else ("TP" if rej else "FN")] += 1
            dev[str(m)] = c
        res["development_v1_top"] = dev if bench else None
        res["development_v1_covered"] = sum(1 for pk in bench if "top" in res["picks"].get(pk, {}))
        res["probe"] = probe(records, feats)
        report["backbones"][bb.name] = res
        (a.out / "report.json").write_text(json.dumps(report, indent=2, default=str))
        del feats
    lines = [f"# Backbone comparison ({a.background}, aggregate={a.aggregate}, host {platform.node()})", "",
             "Leave-one-run-out good scores; thresholds from good only. FR = good rejected, FN = defect passed.", ""]
    for name, res in report["backbones"].items():
        lines += [f"## {name} ({res['input_px']} px, {res['torch_ms_per_crop']:.1f} ms/crop torch {a.device})", "",
                  "| group | good (runs) | defects | AUROC | FR@1.0 | miss@1.0 | FR@1.03 | miss@1.03 | FR@1.15 | miss@1.15 |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for key, g in res["groups"].items():
            cells = []
            for m in MARGINS:
                mm = g["margins"][str(m)]
                cells += [str(mm["false_rejects"]), ",".join(f"{k} {v}" for k, v in mm["misses"].items()) or "0"]
            flag = " (same specimen)" if g["same_specimen"] else ""
            auc = f"{g['auroc']:.3f}" if g["auroc"] is not None else "n/a"
            lines.append(f"| {key} | {g['n_good']} ({len(g['good_runs'])}){flag} | "
                         f"{', '.join(f'{k} {v}' for k, v in g['n_defect'].items()) or '0'} | {auc} | " + " | ".join(cells) + " |")
        lines += ["", "Whole pick, anomaly only (any view over threshold rejects):", ""]
        for m, c in res["whole_pick"].items():
            lines.append(f"- margin {m}: {c}")
        if res["development_v1_top"]:
            lines += ["", f"development-v1 members with a top crop here: {res['development_v1_covered']}"]
            for m, c in res["development_v1_top"].items():
                lines.append(f"- margin {m}: {c}")
        lines += ["", f"Known-defect probe: `{json.dumps(res['probe'])}`", ""]
    (a.out / "summary.md").write_text("\n".join(lines))
    print("\n".join(lines))
    print("REPORT", a.out / "report.json")


if __name__ == "__main__":
    main()
