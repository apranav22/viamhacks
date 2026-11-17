"""Read-only EDA of collected runs; no robot imports or network calls.

Refresh: python site/eda.py && python site/build.py
Analysis requires Pillow (already in the project requirements). Rendering is stdlib-only.
Agent: pi/gpt-6.1-sol; operator: Ali (git Ali, GitHub unknown);
host: Alis-MacBook-Air.local; branch: ali/pipeline.
"""
import argparse
import ast
import csv
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from html import escape as esc
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VIEWS = ("front", "yaw-20", "yaw+35", "pitch-25", "end", "side0", "side+120", "side-120")


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    p = (len(values) - 1) * q
    lo = int(p)
    return values[lo] + (values[math.ceil(p)] - values[lo]) * (p - lo)


def distribution(values):
    values = [float(v) for v in values if isinstance(v, (float, int)) and math.isfinite(v)]
    return {"n": len(values), "min": min(values) if values else None, "p50": percentile(values, .5),
            "p95": percentile(values, .95), "max": max(values) if values else None}


def valid_box(box, width, height):
    return (isinstance(box, list) and len(box) == 4
            and all(isinstance(x, (float, int)) and math.isfinite(x) for x in box)
            and 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height)


def image_stats(path):
    """Intensity + a fixed-scale focus proxy; neither measures part-only sharpness."""
    from PIL import Image
    raw = path.read_bytes()
    with Image.open(io.BytesIO(raw)) as im:
        im.load()  # Full decode, not just a header check.
        width, height = im.size
        small = im.convert("L").resize((128, 128))
        px = list(small.tobytes())
        lap = [px[y * 128 + x - 1] + px[y * 128 + x + 1] + px[(y - 1) * 128 + x]
               + px[(y + 1) * 128 + x] - 4 * px[y * 128 + x]
               for y in range(1, 127) for x in range(1, 127)]
        mean = sum(lap) / len(lap)
        dh = list(im.convert("L").resize((9, 8)).tobytes())
        dhash = sum((dh[y * 9 + x] > dh[y * 9 + x + 1]) << (y * 8 + x)
                    for y in range(8) for x in range(8))
        return {"width": width, "height": height, "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(), "dhash": f"{dhash:016x}",
                "brightness": round(sum(px) / len(px), 2),
                "dark_pct": round(100 * sum(v <= 5 for v in px) / len(px), 2),
                "bright_pct": round(100 * sum(v >= 250 for v in px) / len(px), 2),
                "focus": round(sum((v - mean) ** 2 for v in lap) / len(lap), 2)}


def read_json(path, issues):
    try:
        obj = json.loads(path.read_text())
        if not isinstance(obj, dict):
            raise ValueError("expected an object")
        return obj
    except (OSError, ValueError) as exc:
        issues.append({"path": str(path), "issue": f"unreadable JSON: {exc}"})
        return {}


def tape_threshold(source):
    """Read a literal setting without importing or executing any robot code."""
    if not source.exists():
        return None
    for node in ast.parse(source.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TAPE_FRAC" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                return None
            return value if isinstance(value, (int, float)) and 0 <= value <= 1 else None
    return None


def item_tape_max(pick):
    scores = [pick.get("top_tape")] + [s.get("tape") for s in pick.get("scores", {}).values()]
    return max((s for s in scores if isinstance(s, (int, float))), default=None)


def analyze(runs):
    """Take an inventory first, join by (run, item), then inspect only captured files."""
    runs = Path(runs)
    run_dirs = sorted(p for p in runs.glob("*_collect") if p.is_dir())
    inventory = sorted(p for r in run_dirs for p in r.glob("item_*/*") if p.is_file())
    inventory += [r / "decisions.jsonl" for r in run_dirs if (r / "decisions.jsonl").exists()]
    background_meta = sorted(runs.glob("background*/*/meta.json"))
    inventory += background_meta
    stamps = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in inventory}
    picks, images, issues, background = [], [], [], []
    for run in run_dirs:
        records = {}
        log = run / "decisions.jsonl"
        if log.exists():
            for n, line in enumerate(log.read_text().splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    key = int(rec["item"])
                    if key in records:
                        issues.append({"path": f"{run.name}:{n}", "issue": "duplicate item log row; last row used"})
                    records[key] = rec
                except (ValueError, KeyError, TypeError):
                    issues.append({"path": f"{run.name}:{n}", "issue": "invalid / partial decision row skipped"})
        dirs = {int(p.name.split("_")[-1]): p for p in run.glob("item_*")
                if p.is_dir() and p.name.split("_")[-1].isdigit()}
        for item in sorted(set(records) | set(dirs)):
            folder = dirs.get(item, run / f"item_{item:03d}")
            available = [p for p in inventory if p.parent == folder and p.suffix.lower() in (".jpg", ".png")]
            logrow = records.get(item, {})
            meta = read_json(folder / "meta.json", issues) if folder / "meta.json" in stamps else {}
            flags = []
            values = {}
            for key in ("label", "type", "pose"):
                lv, mv = logrow.get(key), meta.get(key)
                if lv is not None and mv is not None and lv != mv:
                    flags.append(f"{key} conflict: log={lv}, meta={mv}")
                values[key] = lv or mv or "unknown"
            outcome = logrow.get("decision") or meta.get("decision") or "unlogged"
            complete = logrow.get("decision") == "collect" and logrow.get("t_released") is not None
            if not meta:
                flags.append("missing metadata")
            if not logrow:
                flags.append("no decision log row")
            # Timestamp-based run identity, not an inferred collision label for a particular pick.
            if run.name == "20261113_154405_collect":
                flags.append("run-level safety review: E-stop incident (AGENT_LOG)")
            row = {"id": f"{run.name}/{folder.name}", "run": run.name, "item": item, **values,
                   "label_source": "log" if logrow.get("label") else "meta" if meta.get("label") else "unknown",
                   "decision": outcome, "reason": logrow.get("reason", ""), "complete": complete,
                   "has_meta": bool(meta), "has_log": bool(logrow), "flags": flags,
                   "latency_ms": logrow.get("latency_ms"), "cycle_s": logrow.get("cycle_s"),
                   "xy": logrow.get("pick_xy"), "yaw": logrow.get("yaw"), "height_mm": logrow.get("height_mm", meta.get("height_mm")),
                   "scores": logrow.get("scores", {}), "top_tape": logrow.get("top_tape"),
                   "pose": values["pose"], "placed_next": meta.get("placed_next"), "images": []}
            for path in sorted(available):
                name = path.stem
                kind = "crop" if name.startswith("crop_") else "web" if name.startswith("web_") else "top" if name.startswith("top_") else "watch" if name == "watch" else "other"
                view = name.split("_", 1)[1] if "_" in name else name
                rec = {"path": str(path.relative_to(runs.parent)), "pick": row["id"], "kind": kind,
                       "view": view, "label": row["label"], "type": row["type"], "complete": complete}
                try:
                    rec.update(image_stats(path))
                    rec["readable"] = True
                except (OSError, ValueError) as exc:
                    rec.update(readable=False, error=str(exc))
                    flags.append(f"unreadable image {path.name}")
                if rec["readable"] and kind == "top":
                    top = meta.get("top", {}).get(name, {})
                    box = top.get("bbox")
                    rec["bbox"] = box
                    rec["has_top_metadata"] = bool(top)
                    cam_t = top.get("cam_t")
                    rec["camera_z_mm"] = cam_t[2] if isinstance(cam_t, list) and len(cam_t) == 3 else None
                    rec["bbox_valid"] = valid_box(box, rec["width"], rec["height"])
                    rec["pixels"] = top.get("pixels")
                    if rec["bbox_valid"]:
                        rec["bbox_edge"] = min(box[0], box[1], rec["width"] - box[2], rec["height"] - box[3]) <= 2
                        rec["bbox_area_pct"] = round(100 * (box[2] - box[0]) * (box[3] - box[1]) / (rec["width"] * rec["height"]), 3)
                if rec["readable"] and kind == "crop":
                    vm = meta.get("views", {}).get(view, {})
                    box = vm.get("crop_box")
                    rec["crop_box"] = box
                    rec["jaw"] = vm.get("jaw")
                    # A crop touching a sensor boundary is not proof that the part itself is clipped.
                    web = folder / f"web_{view}.jpg"
                    web_dims = None
                    if web in stamps:
                        try:
                            from PIL import Image
                            with Image.open(web) as full:
                                web_dims = full.size
                        except OSError:
                            pass
                    rec["sensor_edge_known"] = bool(box and web_dims)
                    rec["sensor_edge"] = bool(box and web_dims and (box[0] <= 0 or box[1] <= 0 or box[2] >= web_dims[0] or box[3] >= web_dims[1]))
                images.append(rec)
                row["images"].append(rec)
            good_images = [im for im in row["images"] if im["readable"]]
            row["top_count"] = sum(im["kind"] == "top" for im in good_images)
            row["crop_views"] = [im["view"] for im in good_images if im["kind"] == "crop"]
            row["web_views"] = [im["view"] for im in good_images if im["kind"] == "web"]
            expected = set(VIEWS[4:] if row["pose"] == "upright" else VIEWS[:4])
            row["expected_views_known"] = row["pose"] != "unknown"
            row["missing_views"] = sorted(expected - set(row["crop_views"])) if row["expected_views_known"] else []
            row["paired_views"] = sorted(set(row["crop_views"]) & set(row["web_views"]))
            row["readable_multiview"] = complete and row["top_count"] > 0 and len(row["paired_views"]) >= 4
            if complete and row["missing_views"]:
                flags.append("missing expected crop views: " + ", ".join(row["missing_views"]))
            picks.append(row)
    for p in background_meta:
        meta = read_json(p, issues)
        records = meta.get("records", [])
        background.append({"run": p.parent.parent.name, "background": meta.get("background", p.parent.name),
                           "frames": len(records), "detected": sum(r.get("pipeline_target_detected") is True for r in records),
                           "hands": sum(r.get("preview_hand") is True for r in records),
                           "motion_commanded": meta.get("motion_commanded"), "path": str(p.relative_to(runs.parent))})
    changed = [str(p.relative_to(runs.parent)) for p, stamp in stamps.items()
               if not p.exists() or (p.stat().st_size, p.stat().st_mtime_ns) != stamp]
    return {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "scope": "*_collect/item_* plus background* metadata; excludes dry runs, simulations, telemetry frame copies, and reference frames",
            "tape_threshold": tape_threshold(runs.parent / "sort.py"),
            "runs": [r.name for r in run_dirs], "picks": picks, "images": images,
            "issues": issues, "changed_during_scan": changed, "background": background}


def duplicates(images):
    """Only compare the same camera kind/view across different picks."""
    groups = defaultdict(list)
    for im in images:
        if im["readable"] and im["kind"] in ("top", "crop"):
            groups[im["kind"], im["view"], im["type"], im["label"]].append(im)
    exact, near = [], []
    for group in groups.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a["pick"] == b["pick"]:
                    continue
                distance = (int(a["dhash"], 16) ^ int(b["dhash"], 16)).bit_count()
                if a["sha256"] == b["sha256"]:
                    exact.append({"a": a["path"], "b": b["path"]})
                elif distance <= 3:
                    near.append({"a": a["path"], "b": b["path"], "distance": distance})
    return {"exact_pairs": exact, "near_pairs": near}


def make_gallery(data, root, output):
    """Curated, downsampled contact sheets; never publish full raw run folders."""
    from PIL import Image, ImageDraw, ImageOps
    groups = defaultdict(list)
    for p in data["picks"]:
        if any(im["readable"] for im in p["images"]):
            groups[p["type"], p["label"], p["complete"]].append(p)
    gallery = []
    for index, ((typ, label, complete), picks) in enumerate(sorted(groups.items())):
        # Up to 3 evenly spaced picks, with top + up to 4 crops each.
        selected = [picks[i] for i in sorted({0, len(picks) // 2, len(picks) - 1})]
        canvas = Image.new("RGB", (1100, len(selected) * 200), "#f1f5f9")
        draw = ImageDraw.Draw(canvas)
        sources = []
        for r, pick in enumerate(selected):
            ims = [im for im in pick["images"] if im["readable"]]
            tops = [im for im in ims if im["kind"] == "top"]
            crops = [im for im in ims if im["kind"] == "crop"]
            cells = tops[-1:] + crops[:4]
            for c, im in enumerate(cells):
                try:
                    with Image.open(root / im["path"]) as original:
                        original = original.convert("RGB")
                        box = im.get("bbox")
                        if im.get("bbox_valid"):
                            x0, y0, x1, y1 = box
                            box = (max(0, int(x0) - 20), max(0, int(y0) - 20),
                                   min(original.width, int(x1) + 20), min(original.height, int(y1) + 20))
                            original = original.crop(box)
                        tile = ImageOps.contain(original, (210, 155))
                        x, y = c * 220 + (220 - tile.width) // 2, r * 200 + 22
                        canvas.paste(tile, (x, y))
                        title = im["kind"] + ":" + im["view"]
                        if im["kind"] == "top" and not im.get("bbox_valid"):
                            title += " full (no bbox)"
                        draw.text((c * 220 + 5, r * 200 + 4), title, fill="#0f172a")
                except OSError:
                    continue
            sources.append(pick["id"])
            draw.text((5, r * 200 + 182), pick["id"], fill="#334155")
        name = f"eda_gallery_{index:02d}.jpg"
        canvas.save(output / name, quality=85)
        gallery.append({"type": typ, "label": label, "complete": complete, "src": f"img/{name}", "picks": sources})
    return gallery


def write_exports(data, output):
    output.mkdir(parents=True, exist_ok=True)
    for name, rows, fields in (
        ("picks", data["picks"], ["id", "label", "type", "label_source", "pose", "decision", "reason", "complete", "has_meta", "top_count", "crop_views", "missing_views", "readable_multiview", "latency_ms", "cycle_s", "xy", "yaw", "height_mm", "flags"]),
        ("images", data["images"], ["path", "pick", "kind", "view", "label", "type", "complete", "readable", "width", "height", "bytes", "brightness", "dark_pct", "bright_pct", "focus", "sha256", "dhash", "has_top_metadata", "bbox_valid", "camera_z_mm", "sensor_edge_known", "sensor_edge"]),
    ):
        with (output / f"eda_{name}.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items() if k in fields})
    (output / "eda.json").write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def table(headers, rows):
    return '<div class="eda-scroll" tabindex="0" role="region" aria-label="Scrollable data table"><table><thead><tr>' + ''.join(f'<th>{esc(h)}</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{v}</td>' for v in r) + '</tr>' for r in rows) + '</tbody></table></div>'


def num(v, places=1):
    return "—" if v is None else f"{v:.{places}f}"


def bars(title, counts):
    maximum = max(counts.values(), default=1) or 1
    rows = ''.join(f'<div class="eda-bar-row"><span>{esc(str(k))}</span><div><i style="width:{100*v/maximum:.1f}%"></i></div><b>{v}</b></div>' for k, v in counts.items())
    return f'<div class="card"><h3>{esc(title)}</h3>{rows or "No observations"}</div>'


def scatter(title, points, xlabel, ylabel, limits=None):
    """points = (x, y, label, tooltip); SVG stays readable without JS / CDN."""
    points = [p for p in points if isinstance(p[0], (int, float)) and isinstance(p[1], (int, float))]
    if not points:
        return f'<div class="card"><h3>{esc(title)}</h3>No paired observations</div>'
    xmin, xmax, ymin, ymax = limits or (min(p[0] for p in points), max(p[0] for p in points), min(p[1] for p in points), max(p[1] for p in points))
    dx, dy = xmax - xmin or 1, ymax - ymin or 1
    parts = [f'<svg viewBox="0 0 520 290" role="img" aria-label="{esc(title, quote=True)}">', '<path d="M58 15V240H500" fill="none" stroke="#94a3b8"/>']
    for t in range(5):
        frac = t / 4
        x, y = 65 + frac * 425, 230 - frac * 200
        parts.append(f'<text x="{x}" y="258" text-anchor="middle">{xmin + frac*dx:.0f}</text><text x="52" y="{y+4}" text-anchor="end">{ymin+frac*dy:.0f}</text>')
    colors = {"good": "#16a34a", "tape": "#2563eb"}
    for x, y, label, tooltip in points:
        parts.append(f'<circle cx="{65+425*(x-xmin)/dx:.2f}" cy="{230-200*(y-ymin)/dy:.2f}" r="4" fill="{colors.get(label, "#a855f7")}" opacity=".7"><title>{esc(tooltip)}</title></circle>')
    parts.append(f'<text x="280" y="283" text-anchor="middle">{esc(xlabel)}</text><text x="6" y="12">{esc(ylabel)}</text></svg>')
    return f'<div class="card"><h3>{esc(title)}</h3>{"".join(parts)}</div>'


CSS = """
#eda{scroll-margin-top:72px} #eda h3{margin-top:0} #eda h4{margin:22px 0 10px;font-size:18px}
#eda .eda-kpis{grid-template-columns:repeat(auto-fit,minmax(140px,1fr));margin:16px 0}
#eda .eda-kpi b{display:block;font-size:32px;line-height:1.2} #eda .eda-kpi span{font-size:13px;color:var(--mute)}
#eda .eda-bar-row{display:grid;grid-template-columns:minmax(90px,1fr) 1.5fr 32px;gap:8px;align-items:center;font-size:13px;margin:7px 0;overflow-wrap:anywhere}
#eda .eda-bar-row>div{height:12px;background:#e2e8f0;border-radius:9px;overflow:hidden} #eda .eda-bar-row i{display:block;height:100%;background:#2563eb;border-radius:9px}
#eda .eda-scroll{overflow-x:auto;margin:12px 0} #eda table{min-width:600px} #eda td{font-size:13px} #eda small{color:var(--mute)}
#eda svg{width:100%;height:auto} #eda svg text{font-size:12px;fill:#475569} #eda .card{min-width:0}
#eda select,#eda input{font:inherit;padding:6px;border:1px solid #cbd5e1;border-radius:6px;max-width:100%}
#eda .eda-controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:12px 0}
#eda .eda-note{font-size:13px;color:var(--mute)} #eda details{margin:16px 0} #eda summary{font-weight:600;cursor:pointer}
#eda .eda-gallery img{background:#f1f5f9;display:block;min-width:900px} #eda .eda-gallery{margin:12px 0}
#eda .eda-gallery-scroll{overflow-x:auto} #eda .eda-gallery summary{padding:12px 0;font-size:16px}
#eda .eda-overview{margin:16px 0} #eda .eda-overview li{margin:8px 0} #eda .eda-overview h3{font-size:18px}
#eda .eda-note,#eda .eda-kpi span{font-size:14px} #eda .eda-kpis{grid-template-columns:repeat(6,minmax(0,1fr))}
@media(max-width:1000px){#eda .eda-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:600px){#eda .eda-kpis{grid-template-columns:repeat(2,minmax(0,1fr))} #eda .g2,#eda .g3{grid-template-columns:minmax(0,1fr)}}
"""


def gallery(groups):
    """Show one real released example first; retain every group for review."""
    groups = sorted(groups, key=lambda g: not g["complete"])
    out = ['<div id="eda-gallery"><h3>Image examples</h3><p class="eda-note">Top view on the left, webcam crops to the right; up to 3 picks per group. Scroll sideways on a phone or open the full image. Review aids, not approved training labels.</p>']
    if not groups:
        out.append('<p>No image examples in this snapshot.</p>')
    for index, g in enumerate(groups):
        title = f'{g["type"]} · {g["label"]} · {"released" if g["complete"] else "incomplete / failed"}'
        out.append(f'<details class="eda-gallery"{" open" if index == 0 else ""}><summary>{esc(title)}</summary><figure><div class="eda-gallery-scroll" tabindex="0" role="region" aria-label="Scrollable contact sheet"><a href="{esc(g["src"], quote=True)}" target="_blank" rel="noopener"><img loading="lazy" src="{esc(g["src"], quote=True)}" alt="{esc(title, quote=True)} contact sheet"></a></div><figcaption>{esc("; ".join(g["picks"]))} · <a href="{esc(g["src"], quote=True)}" target="_blank" rel="noopener">Open full image</a></figcaption></figure></details>')
    if groups:
        out.append('<details><summary>How to read the contact sheets</summary><p class="eda-note">Up to 3 evenly spaced picks per SKU × label × completion group. Left: last top view (bbox crop + 20 px padding when metadata exists, full frame otherwise). Right: up to 4 webcam crops. Images are downsampled for the report; filenames identify the source. These are review aids, not human-approved labels or masks.</p></details>')
    out.append('</div>')
    return '\n'.join(out)


def section():
    snapshot = HERE / "data" / "eda.json"
    if not snapshot.exists():
        return '<section id="eda"><h2>Collected data · EDA</h2><p id="eda-next">Run <code>python site/eda.py &amp;&amp; python site/build.py</code> to generate the snapshot.</p><p id="eda-gallery">No image examples until a snapshot is generated.</p></section>'
    d = json.loads(snapshot.read_text())
    picks, images = d["picks"], d["images"]
    completed = [p for p in picks if p["complete"]]
    readable = [im for im in images if im["readable"]]
    released_crops = [im for im in readable if im["kind"] == "crop" and im["complete"]]
    good_types = sorted({p["type"] for p in completed if p["label"] == "good" and p["type"] != "unknown"})
    tape_types = {p["type"] for p in completed if p["label"] == "tape" and p["type"] != "unknown"}
    paired_types = sorted(set(good_types) & tape_types)
    bad_top = sum(not im.get("bbox_valid") for im in readable if im["kind"] == "top")
    tops = [im for im in readable if im["kind"] == "top"]
    clipped = sum(im.get("sensor_edge", False) for im in released_crops)
    edge_known = sum(im.get("sensor_edge_known", False) for im in released_crops)
    safety_good = sum(p["label"] == "good" and any('safety review' in f for f in p["flags"]) for p in completed)
    threshold = d.get("tape_threshold")
    scored_tape = [p for p in completed if p["label"] == "tape" and item_tape_max(p) is not None]
    hits = sum(item_tape_max(p) > threshold for p in scored_tape) if threshold is not None else 0
    tape_alert = (f'<li><b>Tape-rule alert:</b> {hits}/{len(scored_tape)} recorded taped cycles exceed the current {threshold:g} cutoff. See the saved-score check below; this was not a live sort test.</li>' if threshold is not None else '')
    kpis = [(len(picks), "attempt directories / logged items"), (len(completed), "released collect cycles"),
            (len(readable), "readable image files (not samples)"), (len(released_crops), "webcam crops in released cycles"),
            (len(good_types), "good SKUs with released cycles"), (sum(p["readable_multiview"] for p in picks), "cycles: top + ≥4 paired views")]
    kpi_html = ''.join(f'<div class="card eda-kpi"><b>{n}</b><span>{esc(label)}</span></div>' for n, label in kpis)
    out = [f'<section id="eda"><h2>Collected data · exploratory analysis</h2><p class="lead">Snapshot {esc(d["generated_at"])}. Read-only analysis of files already on disk; not the live robot dashboard.</p>',
           '<p><a href="data/eda.json" download>Full analysis JSON</a> · <a href="data/eda_picks.csv" download>Per-pick CSV</a> · <a href="data/eda_images.csv" download>Per-image CSV</a></p>',
           f'<div class="grid eda-kpis">{kpi_html}</div>']
    out.append(f'''<div class="grid g2 eda-overview">
<div class="card" id="eda-coverage"><h3>Coverage, not accuracy</h3><ul>
<li><b>{len(good_types)} good SKUs</b> with released cycles; <b>{len(paired_types)}</b> have both good and taped examples.</li>
<li><b>{sum(p['label'].startswith('other:') for p in completed)} other-defect cycles</b>; unseen-defect generalization is not established.</li>
<li>Frames and crops are correlated. Released ≠ training-ready; paired views ≠ full surface coverage.</li></ul>
<a href="#eda-inventory">See SKU counts</a> · <a href="#eda-integrity">View integrity</a></div>
<div class="card" id="eda-next"><h3>Next actions · offline first</h3><ol>
<li>Review safety-flagged captures and crop quality before training.</li>
<li>Audit labels, backfill crop metadata, and split by pick / session.</li>
<li>Plan missing good SKUs and independent validation / defect holdouts.</li></ol>
<a href="#eda-priorities">Collection priorities &amp; caveats</a> · <a href="#eda-ledger">Audit picks</a></div></div>
<p class="eda-note"><b>Safety:</b> safety-flagged captures require review; upright motion is not verified safe. This report does not authorize any robot run.</p>''')
    out.append(gallery(d.get("gallery", [])))
    out.append('<h3>Explore the evidence</h3><p class="eda-note">Expand a topic for tables, charts and source notes. No collection-mode accuracy or AUROC is claimed.</p>')
    out.append(f'''<details class="fold" id="eda-planning"><summary>Planning caveats · safety, sample counts &amp; tape-rule alert</summary><div class="fold-body"><div class="callout warn"><b>What this means for planning</b><ul>
<li><b>Count picks, not frames:</b> {len(picks)} attempts produced {len(completed)} logged released cycles. Full webcam frames and their crops are the same exposure, not two independent samples.</li>
<li><b>Normal-data coverage:</b> completed good data covers {esc(', '.join(good_types)) or 'no known SKUs'}. {safety_good} of those {sum(p['label'] == 'good' for p in completed)} good cycles are in the safety-review session. The kit inventory is only approximate (~7 SKUs). More pictures of one physical part do not add new SKUs or independent objects.</li>
<li><b>Type / label confounding:</b> {len(paired_types)} SKUs have both good and taped released captures. A good-vs-tape comparison may just separate part types; collect matching clean/taped examples before interpreting it as defect discrimination.</li>
<li><b>Crop readiness:</b> {bad_top}/{len(tops)} top frames have no valid saved bounding box (older runs lack metadata too). Those require detection/cropping before training. {clipped}/{edge_known} completed webcam crops with crop metadata touch a sensor boundary ({len(released_crops)-edge_known} cannot be checked); inspect for truncation, not an automatic rejection.</li>
<li><b>Unseen defects:</b> {sum(p['label'].startswith('other:') for p in completed)} released cycles carry an <code>other:</code> label. This cannot establish generalization to an unseen defect.</li>
{tape_alert}
<li><b>Safety review:</b> run <code>20261113_154405_collect</code> contains the upright-grasp E-stop incident documented in AGENT_LOG. Its saved images and completed cycles are included for auditing, <em>not certified as safe or training-ready</em>. No robot commands were issued for this EDA.</li></ul></div></div></details>''')
    out.append('<details class="fold" id="eda-inventory"><summary>Inventory · outcomes &amp; class balance</summary><div class="fold-body"><div class="grid g3">')
    out += [bars("Pick outcomes (all attempts)", Counter(p["decision"] for p in picks)),
            bars("Labels · released cycles only", Counter(p["label"] for p in completed)),
            bars("Readable files by role", Counter(im["kind"] for im in readable)), '</div>']
    types = sorted({p["type"] for p in picks})
    rows = []
    for typ in types:
        ps = [p for p in picks if p["type"] == typ]
        cs = [p for p in ps if p["complete"]]
        rows.append([esc(typ), len(ps), len(cs), sum(p["label"] == "good" for p in cs), sum(p["label"] == "tape" for p in cs),
                     sum(p["label"].startswith("other:") for p in cs), sum(p["pose"] == "upright" for p in cs),
                     sum(len(p["crop_views"]) for p in cs)])
    out.append(table(["Declared SKU", "Attempts", "Released", "Good", "Tape", "Other defect", "Upright released", "Webcam crops"], rows))
    out.append('<p class="eda-note">Labels are operator-entered, not model predictions. Log labels take priority over metadata; conflicts stay visible in the ledger. Missing labels are not inferred from nearby runs. No accuracy/AUROC is claimed from collection-mode decisions.</p>')
    runrows = []
    for run in d["runs"]:
        ps = [p for p in picks if p["run"] == run]
        cs = [p for p in ps if p["complete"]]
        runrows.append([esc(run), len(ps), len(cs), sum(p["has_meta"] for p in ps), sum(len(p["images"]) for p in ps),
                        esc(', '.join(sorted({p['type'] for p in ps}))), num(distribution([p["cycle_s"] for p in cs])["p50"])])
    out.append('<details><summary>Run-by-run collection history</summary>' + table(["Run", "Attempts", "Released", "Metadata", "Files", "SKU", "Cycle p50 s"], runrows) + '</details>')
    out.append('</div></details><details class="fold" id="eda-integrity"><summary>View coverage &amp; file integrity</summary><div class="fold-body">')
    rows = []
    for view in VIEWS:
        ims = [im for im in released_crops if im["view"] == view]
        ps = [p for p in completed if view in p["crop_views"]]
        rows.append([esc(view), len(ims), sum(p["label"] == "good" for p in ps), sum(p["label"] == "tape" for p in ps),
                     esc(', '.join(sorted({im["type"] for im in ims}))) or '—', sum(im.get("sensor_edge", False) for im in ims)])
    out.append(table(["View", "Released-cycle crops", "Good picks", "Tape picks", "SKUs", "Touches sensor edge"], rows))
    dims = Counter(f'{im["kind"]} {im["width"]}×{im["height"]}' for im in readable)
    integrity = [("Missing meta.json", sum(not p["has_meta"] for p in picks)), ("No decision row", sum(not p["has_log"] for p in picks)),
                 ("Unknown label", sum(p["label"] == "unknown" for p in picks)), ("Unreadable images", len(images) - len(readable)),
                 ("Released cycles missing expected crop views (known pose only)", sum(bool(p["missing_views"]) for p in completed)),
                 ("Label / type / pose conflicts", sum(any('conflict' in f for f in p["flags"]) for p in picks))]
    out.append('<div class="grid g2">' + bars("Image shapes", dims) + bars("Integrity flags · all attempts unless noted", dict(integrity)) + '</div>')
    out.append('<details><summary>Top-frame geometry by run (only saved metadata)</summary>' + table(["Run", "Top frames with metadata", "Valid bbox", "Camera world z p50 mm"], [
        [esc(run), len(ts), sum(im.get("bbox_valid", False) for im in ts), num(distribution([im.get("camera_z_mm") for im in ts])["p50"])]
        for run in d["runs"] if (ts := [im for im in tops if im["pick"].startswith(run + '/') and im.get("has_top_metadata")])]) +
        '<p class="eda-note">World z is camera pose, not camera-to-part distance. Run 153239 has no detected top bboxes at the lower camera pose; later button-screw runs have saved bboxes at the higher pose. The contact sheets show the off-frame vs in-frame appearance. This is observational, not a controlled height experiment.</p></details>')
    out.append('</div></details><details class="fold" id="eda-quality"><summary>Image quality · focus, exposure &amp; crops</summary><div class="fold-body"><p class="eda-note">Computed on a grayscale 128×128 resize of each file: mean intensity (0–255), dark ≤5 / bright ≥250 pixels, and variance of a 4-neighbour Laplacian (focus proxy). These include background and gripper, so compare within a view and resolution; they are not part-only quality scores or automatic blur cutoffs.</p>')
    rows = []
    for kind in ("watch", "top", "web", "crop"):
        ims = [im for im in readable if im["kind"] == kind]
        rows.append([kind, len(ims), num(distribution([im["brightness"] for im in ims])["p50"]),
                     num(distribution([im["focus"] for im in ims])["p50"]), num(distribution([im["dark_pct"] for im in ims])["p50"]),
                     num(distribution([im["bright_pct"] for im in ims])["p50"])])
    out.append(table(["File role", "n files", "Intensity p50", "Focus proxy p50", "Dark % p50", "Bright % p50"], rows))
    out.append('<div class="grid g2">' + scatter("Completed webcam crops · brightness vs focus", [(im["brightness"], im["focus"], im["label"], im["path"]) for im in released_crops], "Mean intensity", "Focus proxy")
               + bars("Completed pick poses", Counter(p["pose"] for p in completed)) + '</div>')
    out.append('<p class="eda-note">Chart colors: green = declared good, blue = tape, purple = unknown / other. Hover points for source paths. A cluster can reflect the fixed background, not part diversity.</p>')
    lowest = sorted(released_crops, key=lambda im: im["focus"])[:8]
    out.append('<details><summary>Lowest-focus completed crops to inspect (not automatically bad)</summary>' + table(["Image", "Focus proxy", "Intensity", "Label"], [[esc(im["path"]), im["focus"], im["brightness"], esc(im["label"])] for im in lowest]) + '</details>')
    out.append('</div></details><details class="fold" id="eda-performance"><summary>Collection performance &amp; placement diversity</summary><div class="fold-body">')
    rows = []
    metrics = [("First-motion latency (ms) · all logged attempts", [p["latency_ms"] for p in picks]),
               ("First-motion latency (ms) · released cycles", [p["latency_ms"] for p in completed]),
               ("Cycle (s) · released cycles", [p["cycle_s"] for p in completed]),
               ("Webcam capture (ms) · released view scores", [s.get("frame_ms") for p in completed for s in p["scores"].values()]),
               ("Jaw reading · completed crops with metadata", [im.get("jaw") for im in released_crops])]
    for name, vals in metrics:
        stats = distribution(vals)
        rows.append([esc(name), stats["n"], *[num(stats[k]) for k in ("min", "p50", "p95", "max")]])
    out.append(table(["Metric / denominator", "n", "min", "p50", "p95", "max"], rows))
    out.append('<div class="grid g2">' + scatter("Pick locations (all recorded attempts)", [(p["xy"][0], p["xy"][1], p["label"], p["id"]) for p in picks if p.get("xy") and len(p["xy"]) == 2], "World x (mm)", "World y (mm)")
               + scatter("Completed cycles · latency vs duration", [(p["latency_ms"], p["cycle_s"], p["label"], p["id"]) for p in completed], "First-motion latency (ms)", "Cycle (s)") + '</div>')
    headings = Counter(f'{int((p["yaw"] % 180) // 30)*30}–{int((p["yaw"] % 180) // 30)*30+30}°' for p in completed if isinstance(p.get("yaw"), (float, int)))
    out.append('<div class="grid g2">' + bars("Initial part heading · released cycles (modulo 180°)", dict(sorted(headings.items(), key=lambda x: int(x[0].split('–')[0])))) + bars("How the next placement was made (metadata only)", Counter((p.get("placed_next") or {}).get("how", "unknown") for p in completed)) + '</div>')
    out.append('<p class="eda-note">Cycle duration includes movement and collection, not a defect model. This is not a judged throughput benchmark. Initial pick coordinates/headings come from the watch-stage log, not final grasp pose. Repeated placements of one object remain correlated.</p>')
    out.append('</div></details><details class="fold" id="eda-tape"><summary>Tape-rule scores · saved-score check, not model accuracy</summary><div class="fold-body">')
    rows = []
    for label in sorted({p["label"] for p in completed}):
        for camera in ("top", "webcam"):
            scores = [p["top_tape"] for p in completed if p["label"] == label] if camera == "top" else [s.get("tape") for p in completed if p["label"] == label for s in p["scores"].values()]
            stats = distribution(scores)
            rows.append([esc(label), camera, stats["n"], *[num(stats[k], 4) for k in ("min", "p50", "p95", "max")]])
    out.append(table(["Declared label", "Channel", "n scored frames", "min", "p50", "p95", "max"], rows))
    out.append('<p class="eda-note">Fractions are the runtime blue-pixel rule, not PatchCore anomaly scores. No accuracy estimate is possible from these collection decisions. Denominators differ (top detected bbox vs large webcam crop); do not compare them directly. No labels, thresholds or held-out data were changed. Tape visibility in every view is not guaranteed, and these scores cannot assess unseen defects.</p>')
    if threshold is not None:
        out.append(f'<div class="callout warn"><b>Recorded-score sanity check: {hits}/{len(scored_tape)} taped cycles exceed the current tape cutoff ({threshold:g}).</b><p>For each released taped pick, take max(top tape fraction, all webcam tape fractions) and compare using the same strict &gt; as sort.py. The largest recorded taped-item fraction is {num(max((item_tape_max(p) for p in scored_tape), default=None), 4)}. This is a check of saved scores against the literal <code>TAPE_FRAC</code> read from sort.py at analysis time, not a live sort run or an independent accuracy estimate. Review visible tape, labels, hue mask and crop denominators before relying on this channel. No cutoff was changed or tuned.</p></div>')
    dup = d.get("duplicates", {})
    out.append(f'</div></details><details class="fold" id="eda-duplicates"><summary>Duplication &amp; split leakage</summary><div class="fold-body"><div class="callout"><b>{len(dup.get("exact_pairs", []))} byte-identical pairs; {len(dup.get("near_pairs", []))} low-distance perceptual-hash pairs.</b><p>Compared top/crop images across different picks only, within the same role, view, declared SKU and label. Exact = SHA-256 match; similar = 64-bit difference-hash distance ≤3. Fixed backgrounds can make distinct parts look similar; this is a review list, not automatic deduplication.</p><p><b>Split by pick at minimum, preferably by collection session / physical object.</b> Keep every top image, webcam frame and crop of one pick in the same split. Dataset manifests are not present in these capture folders, so train/validation separation cannot be verified here. The tiny number of objects means no reliable independent test score yet.</p></div>')
    pairs = dup.get("exact_pairs", []) + dup.get("near_pairs", [])
    out.append('<details><summary>Duplicate / similar-pair source list</summary>' + table(["Image A", "Image B", "Hash distance"], [[esc(p["a"]), esc(p["b"]), p.get("distance", "exact bytes")] for p in pairs[:100]]) + f'<p class="eda-note">First 100 pairs shown; full list in JSON ({len(pairs)} total).</p></details>')
    out.append('</div></details><details class="fold" id="eda-background"><summary>Background comparison · separate experiment</summary><div class="fold-body">')
    out.append(table(["Experiment", "Background", "Frames", "Target detected", "Hand flagged", "Motion commanded"], [[esc(b["run"]), esc(b["background"]), b["frames"], b["detected"], b["hands"], esc(str(b["motion_commanded"]))] for b in d["background"]]))
    out.append('<p class="eda-note">Counts are recorded detector outputs, not independent trials or hand-labelled ground truth. Consecutive frames of a static scene do not establish robustness or a causal improvement. Kept separate from pick counts and anomaly-training data.</p>')
    out.append('</div></details><details class="fold" id="eda-priorities"><summary>Full collection priorities &amp; offline work lanes</summary><div class="fold-body"><ol><li><b>Review the safety-flagged session and crop quality before promoting any images to training.</b> Upright motion is not verified safe; no suggestion here authorizes another arm run.</li><li><b>Fill good-SKU gaps</b> rather than repeating the two available good types. Get independently repositioned, visually reviewed top and checkpoint images; explicit physical-part IDs will make the split defensible.</li><li><b>Backfill / repair metadata offline:</b> legacy top crops lack bboxes; retain failure examples for detector debugging, not normal-model training.</li><li><b>Reserve separate good validation sessions</b> before filling PatchCore banks, then collect a protected unseen-defect holdout with staff permission. Do not tune thresholds on it.</li><li><b>Offline agents can parallelize now:</b> one builds masks/canonical crops; one audits labels and contact sheets; one makes group-wise split manifests. None needs control of the arm.</li></ol></div></details>')
    out.append('<details class="fold"><summary>All picks · searchable audit ledger</summary><div class="fold-body"><div class="eda-controls"><label>Filter <input id="eda-search" type="search" placeholder="SKU, label, run, failure…"></label><label>Status <select id="eda-status"><option value="all">All attempts</option><option value="yes">Released cycles</option><option value="no">Incomplete / failed</option></select></label><output id="eda-count"></output></div>')
    rows = []
    for p in picks:
        rows.append([esc(p["id"]), esc(p["type"]), esc(p["label"]) + f'<br><small>from {esc(p["label_source"])}</small>',
                     f'<span data-complete="{"yes" if p["complete"] else "no"}">{esc(p["decision"])}</span>', esc(p["pose"]),
                     p["top_count"], len(p["crop_views"]), num(p["cycle_s"]), esc('; '.join(p["flags"]) or p["reason"] or '—')])
    out.append('<div id="eda-ledger">' + table(["Pick", "SKU", "Label", "Outcome", "Pose", "Top files", "Crop views", "Cycle s", "Review notes"], rows) + '</div></div></details>')
    out.append('<details class="fold" id="eda-method"><summary>Method, scope and snapshot warnings</summary><div class="fold-body"><p>' + esc(d["scope"]) + '</p><p>Released = decision log says <code>collect</code> and has <code>t_released</code>. This proves the software recorded release, not successful grasp, physical release or data quality. Complete multiview = released + readable top + ≥4 matching web/crop names, not surface-coverage certification. Empty item directories are retained as attempts. Percentiles are linear interpolation; missing fields are excluded and every summary shows its own n.</p><p>Source files are never edited; only downsampled contact sheets and analysis exports are generated. Capture may continue during analysis. Rebuild the snapshot explicitly with <code>python site/eda.py &amp;&amp; python site/build.py</code> (Pillow required for analysis). The project-progress percentages are a separately dated planning estimate, not recomputed from these capture counts.</p>')
    out.append(f'<p>Parse issues: {len(d["issues"])}. Source files changed while scanning: {len(d["changed_during_scan"])}.</p>')
    if d["issues"]:
        out.append(table(["Source", "Issue"], [[esc(i["path"]), esc(i["issue"])] for i in d["issues"]]))
    if d["changed_during_scan"]:
        out.append('<p>Re-run once capture is idle for a stable snapshot: ' + esc(', '.join(d["changed_during_scan"])) + '</p>')
    out.append('</div></details><script>(()=>{const q=document.getElementById("eda-search"),s=document.getElementById("eda-status"),rows=[...document.querySelectorAll("#eda-ledger tbody tr")];function filter(){let n=0;for(const r of rows){const ok=r.textContent.toLowerCase().includes(q.value.toLowerCase())&&(s.value==="all"||r.querySelector("[data-complete]").dataset.complete===s.value);r.hidden=!ok;if(ok)n++;}document.getElementById("eda-count").textContent=n+" / "+rows.length+" picks";}q.addEventListener("input",filter);s.addEventListener("change",filter);filter();})();</script></section>')
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=ROOT / "runs")
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    data = analyze(args.runs)
    data["duplicates"] = duplicates(data["images"])
    img = args.output / "img"
    img.mkdir(parents=True, exist_ok=True)
    data["gallery"] = make_gallery(data, args.runs.parent, img)
    write_exports(data, args.output / "data")
    print(json.dumps({"snapshot": data["generated_at"], "runs": len(data["runs"]), "attempts": len(data["picks"]),
                      "released": sum(p["complete"] for p in data["picks"]), "images": len(data["images"]),
                      "parse_issues": len(data["issues"]), "changed_during_scan": len(data["changed_during_scan"])}, indent=2))


if __name__ == "__main__":
    main()
