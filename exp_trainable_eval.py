"""Trainable anomaly models vs ResNet-18 PatchCore, same data and protocol as exp_backbone_eval.py (top view).

    python exp_trainable_eval.py --runs 'runs/*_collect' --background cardboard --models efficientad padim --out exp/trainable_top

Per part-type group: good picks scored by a model trained WITHOUT their run (leave-one-run-out); groups with a single
run (same specimen) use 5 pick-folds instead of leave-one-pick-out (one model per pick would be ~40 trainings). Defects
are scored by a model trained on all good picks of their group. Thresholds and false rejects follow score_group:
threshold = max held-out good score x margin; a good pick is a false reject when its score >= max(other runs' good
scores) x margin. Needs the CUDA env (.venv-ad) with anomalib.
"""
import argparse
import glob
import json
import platform
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from exp_backbone_eval import MARGINS, auroc, load_records

FOLDS_SAME_SPECIMEN = 5


def fold_units(good):
    runs = sorted({r["run"] for r in good})
    if len(runs) >= 2:
        return False, [[r for r in good if r["run"] == run] for run in runs]
    picks = sorted({r["pick_id"] for r in good})
    chunks = [picks[i::FOLDS_SAME_SPECIMEN] for i in range(min(FOLDS_SAME_SPECIMEN, len(picks)))]
    return True, [[r for r in good if r["pick_id"] in set(c)] for c in chunks]


def score_group(recs, backend, log):
    good = [r for r in recs if r["label"] == "good"]
    bad = [r for r in recs if r["label"] != "good"]
    same, units = fold_units(good)
    scores, train_s = {}, []
    for k, held in enumerate(units):
        train = [r for r in good if all(r is not h for h in held)]
        if not train:
            continue
        t = time.time()
        model = backend.fit([r["crop"] for r in train])
        train_s.append(time.time() - t)
        for r, s in zip(held, backend.score(model, [r["crop"] for r in held])):
            scores[id(r)] = s
        log(f"    fold {k + 1}/{len(units)}: train {len(train)} -> {train_s[-1]:.0f}s")
        del model
    if bad:
        t = time.time()
        model = backend.fit([r["crop"] for r in good])
        train_s.append(time.time() - t)
        for r, s in zip(bad, backend.score(model, [r["crop"] for r in bad])):
            scores[id(r)] = s
        del model
    unit_of = {id(r): k for k, held in enumerate(units) for r in held}
    g_scores = {id(r): scores[id(r)] for r in good if id(r) in scores}
    res = {"n_good": len(g_scores), "good_runs": sorted({r["run"] for r in good}), "same_specimen": same,
           "n_defect": dict(defaultdict(int, {l: sum(r["label"] == l for r in bad) for l in {r["label"] for r in bad}})),
           "auroc": auroc(list(g_scores.values()), [scores[id(r)] for r in bad if id(r) in scores]),
           "train_s": train_s, "margins": {}}
    for m in MARGINS:
        thr = max(g_scores.values()) * m if g_scores else None
        fr = 0
        for r in good:
            if id(r) not in g_scores:
                continue
            rest = [g_scores[id(g)] for g in good if id(g) in g_scores and unit_of[id(g)] != unit_of[id(r)]]
            if rest and g_scores[id(r)] >= max(rest) * m:
                fr += 1
        misses = defaultdict(int)
        for r in bad:
            if thr is None or scores.get(id(r), -np.inf) < thr:
                misses[r["label"]] += 1
        res["margins"][str(m)] = {"threshold": thr, "false_rejects": fr, "misses": dict(misses)}
    per_pick = {r["pick_id"]: {"label": r["label"], "score": scores[id(r)]} for r in recs if id(r) in scores}
    return res, per_pick


def make_backend(name, device, args):
    if name == "efficientad":
        from trainable_backends import EfficientAD
        return EfficientAD(device, steps=args.steps, size=args.size)
    if name == "padim":
        from trainable_backends import Padim
        return Padim(device, size=args.size)
    if name in ("simplenet", "glass"):
        from trainable_backends import Generic
        return Generic(name, device, steps=args.steps, size=args.size)
    raise ValueError(name)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", nargs="+", required=True)
    p.add_argument("--background", default="cardboard")
    p.add_argument("--models", nargs="+", default=["efficientad", "padim"])
    p.add_argument("--device", default="cuda")
    p.add_argument("--steps", type=int, default=300)
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--max-fold-s", type=float, default=180, help="stop a model when one fold trains longer than this")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    dirs = sorted({d for pat in a.runs for d in (glob.glob(pat) or [pat]) if (Path(d) / "decisions.jsonl").exists()})
    a.out.mkdir(parents=True, exist_ok=True)
    records, skipped = load_records(dirs, a.background, {"top"})
    groups = defaultdict(list)
    for r in records:
        groups[r["group"]].append(r)
    print(f"{len(records)} crops, {len(groups)} groups", flush=True)
    report = {"host": platform.node(), "background": a.background, "steps": a.steps, "size": a.size,
              "folds_same_specimen": FOLDS_SAME_SPECIMEN, "models": {}}
    rp = a.out / "report.json"
    if rp.exists():
        report["models"] = json.loads(rp.read_text()).get("models", {})
    for name in a.models:
        try:
            backend = make_backend(name, a.device, a)
        except Exception as e:  # noqa: BLE001
            print(f"MODEL {name} unavailable: {type(e).__name__}: {e}", flush=True)
            report["models"][name] = {"error": f"{type(e).__name__}: {e}"}
            continue
        print(f"MODEL {name}", flush=True)
        res = {"groups": {}, "picks": {}, "info": getattr(backend, "info", {})}
        try:
            for key, recs in sorted(groups.items()):
                print(f"  group {key}", flush=True)
                g, per_pick = score_group(recs, backend, lambda s: print(s, flush=True))
                res["groups"][key] = g
                if g["train_s"] and max(g["train_s"]) > a.max_fold_s:
                    raise TimeoutError(f"fold took {max(g['train_s']):.0f}s > {a.max_fold_s}s in {key}")
                for pick, v in per_pick.items():
                    res["picks"][pick] = {**v, "threshold": {m: g["margins"][str(m)]["threshold"] for m in MARGINS}}
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            res["error"] = f"{type(e).__name__}: {e}"
        fused = {}
        for m in MARGINS:
            c = defaultdict(int)
            for v in res["picks"].values():
                rej = v["threshold"][m] is not None and v["score"] >= v["threshold"][m]
                c[("FR" if rej else "TN") if v["label"] == "good" else ("TP" if rej else "FN")] += 1
            fused[str(m)] = dict(c)
        res["whole_pick"] = fused
        res["ms_per_crop"] = backend.bench([r["crop"] for r in records[:32]]) if not res.get("error") else None
        report["models"][name] = res
        rp.write_text(json.dumps(report, indent=2, default=str))
    lines = [f"# Trainable anomaly models ({a.background}, top view, host {platform.node()})", "",
             "Leave-one-run-out good scores (single-run groups: 5 pick-folds); thresholds from good only. "
             "FR = good rejected, FN = defect passed.",
             "Baseline ResNet-18 PatchCore (exp/backbone_top): margin 1.0 TP 12 FR 7; 1.03 TP 10 FR 0; 1.15 TP 2 FR 0.", ""]
    for name, res in report["models"].items():
        if "groups" not in res:
            lines += [f"## {name}: not run ({res.get('error')})", ""]
            continue
        ms = res.get("ms_per_crop") or {}
        tr = [t for g in res["groups"].values() for t in g["train_s"]]
        lines += [f"## {name} ({ms.get('gpu_ms', float('nan')):.1f} ms/crop GPU, {ms.get('cpu_ms', float('nan')):.1f} ms/crop CPU; "
                  f"train per fold median {np.median(tr) if tr else float('nan'):.0f}s)" + (f" ERROR: {res['error']}" if res.get("error") else ""), "",
                  "| group | good (runs) | defects | AUROC | FR@1.0 | miss@1.0 | FR@1.03 | miss@1.03 | FR@1.15 | miss@1.15 |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for key, g in res["groups"].items():
            cells = []
            for m in MARGINS:
                mm = g["margins"][str(m)]
                cells += [str(mm["false_rejects"]), ",".join(f"{k} {v}" for k, v in mm["misses"].items()) or "0"]
            flag = " (same specimen, 5 folds)" if g["same_specimen"] else ""
            auc = f"{g['auroc']:.3f}" if g["auroc"] is not None else "n/a"
            lines.append(f"| {key} | {g['n_good']} ({len(g['good_runs'])}){flag} | "
                         f"{', '.join(f'{k} {v}' for k, v in g['n_defect'].items()) or '0'} | {auc} | " + " | ".join(cells) + " |")
        lines += ["", "Whole pick, anomaly only:", ""] + [f"- margin {m}: {c}" for m, c in res["whole_pick"].items()] + [""]
    (a.out / "summary.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
