"""Catalog of everything under runs/: one static page to browse captures with their metadata, and a text table for git.

    python3 catalog.py              # scan runs/ -> runs/index.html, runs/catalog.json, docs/RUN_CATALOG.md
    python3 catalog.py --refresh    # first re-download the shared index + model manifests (public HF repo, no login)
    open runs/index.html            # no server needed; images load from the run folders next to it

To have every run on disk first: `python sync_data.py pull` (DATA_PLAN.md, "Sharing the data").

What it joins, per pick: item_NNN/meta.json, the pick's row in decisions.jsonl, the run's exclude.json, the image files,
which model bundles list the pick (train / calibration / test), and the curated note for the run in docs/run_notes.json.
Run names carry the clock of the machine that made them (laptop EST, station MST); the catalog orders by real time.

Reads only. Writes runs/index.html, runs/catalog.json, runs/_shared/ (downloaded manifests) and docs/RUN_CATALOG.md.
Stdlib only; never imports the robot SDK and never talks to the machine.
"""

import argparse
import json
import re
import statistics
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EST, MST = timezone(timedelta(hours=-5)), timezone(timedelta(hours=-7))
STATION = "armfarm04b"
IMG = (".jpg", ".jpeg", ".png")
CURRENT_RECIPE = "cardboard 1280x720"
FLAGS = {"ok": "usable as logged", "partial": "usable except excluded items", "caution": "review before using",
         "exclude": "do not train from it", "probe": "grasp / diagnostic probe", "live": "sort run, no ground truth in data",
         "empty": "nothing captured"}
OUTCOMES = {"captured": "captured", "good": "sorted GOOD", "reject": "sorted REJECT", "dropped": "dropped",
            "no_pick": "no pick", "no_record": "no decision row"}


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def read_jsonl(path):
    rows = []
    try:
        for line in Path(path).read_text().splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


# ---------- shared repo manifests (optional) ----------

def refresh_shared(runs: Path):
    """Download index.json and every shared model's bundle*.json (a few hundred kB) into runs/_shared/."""
    repo = (read_json(ROOT / "config" / "data_repo.json") or {}).get("repo_id")
    if not repo:
        raise SystemExit("config/data_repo.json has no repo_id")
    base, out = f"https://huggingface.co/datasets/{repo}/resolve/main/", runs / "_shared"
    api = f"https://huggingface.co/api/datasets/{repo}"

    def get(url):
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "viamhacks-catalog"}),
                                    timeout=60) as r:
            return r.read()

    out.mkdir(exist_ok=True)
    index = json.loads(get(base + "index.json"))
    info = json.loads(get(api))
    index["_snapshot"] = {"repo": repo, "commit": info.get("sha"), "last_modified": info.get("lastModified"),
                          "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (out / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True))
    for name in sorted(index.get("models", {})):
        for entry in json.loads(get(f"{api}/tree/main/models/{name}")):
            leaf = entry["path"].split("/")[-1]
            if entry.get("type") == "file" and leaf.startswith("bundle") and leaf.endswith(".json"):
                (out / "models" / name).mkdir(parents=True, exist_ok=True)
                (out / "models" / name / leaf).write_bytes(get(base + entry["path"]))
    print(f"shared manifests -> {out.relative_to(ROOT)} (repo commit {str(info.get('sha'))[:8]})")


# ---------- models: which picks each bundle used ----------

def load_models(runs: Path):
    """-> (models: [dict], usage: {'run/item_NNN': {model: split}}). Local bundles win over downloaded manifests."""
    found = {}
    for where, root in (("shared manifest (weights not on this machine)", runs / "_shared" / "models"),
                        ("on this machine", ROOT / "models")):
        if root.is_dir():
            for d in sorted(p for p in root.iterdir() if p.is_dir()):
                files = sorted(d.glob("bundle*.json"))
                if files:
                    found[d.name] = (where, files)
    shared = set((read_json(runs / "_shared" / "index.json") or {}).get("models", {}))
    models, usage = [], defaultdict(dict)
    for name, (where, files) in sorted(found.items()):
        splits = {"train": set(), "calibration": set(), "test": set()}
        banks, margins, backbones, policy, notes, variants = set(), set(), set(), None, [], []
        for f in files:
            b = read_json(f) or {}
            policy = b.get("crop_policy", policy)
            if b.get("note"):
                notes.append(b["note"])
            ms = {m.get("margin") for m in b.get("models", {}).values()}
            variants.append(f"{f.name} (margin {', '.join(str(m) for m in sorted(x for x in ms if x is not None)) or '?'})")
            for key, m in b.get("models", {}).items():
                banks.add(key)
                margins.add(m.get("margin"))
                backbones.add(m.get("backbone"))
                for s in splits:
                    splits[s].update(m.get(f"{s}_pick_ids", []))
        for s, ids in splits.items():
            for pid in ids:
                usage[pid][name] = s
        used_runs = Counter(pid.split("/")[0] for ids in splits.values() for pid in ids)
        models.append(dict(
            name=name, where=where, shared=name in shared, files=variants, crop_policy=policy, notes=notes,
            backbones=sorted(x for x in backbones if x), types=sorted({k.split("|")[0] for k in banks}),
            views=sorted({k.split("|")[2] for k in banks if k.count("|") >= 3}),
            backgrounds=sorted({k.split("|")[3] for k in banks if k.count("|") >= 3}), banks=len(banks),
            picks={s: len(ids) for s, ids in splits.items()}, runs=dict(sorted(used_runs.items()))))
    return models, usage


# ---------- runs ----------

def run_clock(name, host):
    """Start time from the run name, read on the clock of the machine that made it."""
    m = re.search(r"(\d{8})_(\d{6})", name)
    if m:
        t = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    else:
        m = re.search(r"(\d{6})", name)
        if not m:
            return None
        t = datetime.strptime("20261113" + m.group(1), "%Y%m%d%H%M%S")
    return t.replace(tzinfo=MST if host == "station" else EST)


def image_order(name):
    stem = name.rsplit(".", 1)[0]
    for i, prefix in enumerate(("watch", "top_", "web_", "crop_")):
        if stem.startswith(prefix):
            return (i, stem)
    return (9, stem)


def outcome_of(row):
    if row is None:
        return "no_record"
    d = row.get("decision")
    return "captured" if d == "collect" else d if d in ("good", "reject", "dropped") else "no_pick"


def scan_run(run: Path, kind, shared_index, usage, notes):
    rows = read_jsonl(run / "decisions.jsonl")
    by_item = {}
    for r in rows:
        try:
            by_item[int(r["item"])] = r
        except (KeyError, TypeError, ValueError):
            pass
    shared = shared_index.get(run.name)
    offsets = [r["t_seen"][-6:] for r in rows if isinstance(r.get("t_seen"), str)]
    host = "station" if (shared or {}).get("host") == STATION or "-07:00" in offsets else "laptop"
    start = run_clock(run.name, host)
    exclude = read_json(run / "exclude.json", {}) or {}
    note = notes.get(run.name, {})
    numbers = sorted({int(p.name[5:]) for p in run.glob("item_*") if p.is_dir() and p.name[5:].isdigit()} | set(by_item))
    items = []
    for n in numbers:
        d, row = run / f"item_{n:03d}", by_item.get(n)
        meta = read_json(d / "meta.json")
        m, r = meta or {}, row or {}
        images = sorted((p.name for p in d.iterdir() if p.suffix.lower() in IMG), key=image_order) if d.is_dir() else []
        cam = m.get("camera") or {}
        background = m.get("background")
        res = f"{cam['width_px']}x{cam['height_px']}" if cam.get("width_px") else None
        scores = {}
        for view, s in (r.get("scores") or {}).items():
            if isinstance(s, dict):
                scores[view] = {k: s.get(k) for k in ("score", "threshold", "ratio", "anomalous", "tape", "detail", "status")}
        out = outcome_of(row)
        items.append(dict(
            n=n, id=f"{run.name}/item_{n:03d}", outcome=out, reason=r.get("reason"),
            type=r.get("type") or m.get("type"), label=r.get("label") or m.get("label"),
            intended=out not in ("captured",) and bool(m.get("label")) and m.get("label") != "unlabeled",
            pose=r.get("pose") or m.get("pose"), background=background, resolution=res,
            recipe=f"{background} {res}" if background and res else "legacy (not recorded, wrist 640x480)",
            t_seen=r.get("t_seen"), cycle_s=r.get("cycle_s"), latency_ms=r.get("latency_ms"),
            excluded=exclude.get(f"item_{n:03d}"), relabel=r.get("relabel"), scores=scores,
            truth=(note.get("truth") or {}).get(str(n)), used_by=usage.get(f"{run.name}/item_{n:03d}", {}),
            images=images, has_meta=meta is not None, meta=meta, decision=row))
    oc = Counter(i["outcome"] for i in items)
    captured = [i for i in items if i["outcome"] == "captured"]
    counted = captured if kind == "collect" else [i for i in items if i["outcome"] in ("good", "reject", "dropped")]
    pool = counted or items
    extras = sorted(p.name for p in run.iterdir() if p.is_file() and p.name not in ("decisions.jsonl", "judge.jsonl"))
    judge = read_jsonl(run / "judge.jsonl")
    flag = note.get("flag") or (None if kind == "dry" else "empty" if not counted else "live" if kind == "sort" else None)
    return dict(
        name=run.name, kind=kind, host=host, start=start.astimezone(timezone.utc).isoformat() if start else None,
        est=start.astimezone(EST).strftime("%H:%M") if start else "", mst=start.astimezone(MST).strftime("%H:%M") if start else "",
        types=dict(Counter(str(i["type"]) for i in pool if i["type"])), labels=dict(Counter(str(i["label"]) for i in pool if i["label"])),
        recipes=dict(Counter(i["recipe"] for i in pool)), outcomes=dict(oc), attempts=len(items),
        captured=len(captured), usable=sum(1 for i in captured if not i["excluded"]),
        excluded=sum(1 for i in items if i["excluded"]), images=sum(len(i["images"]) for i in items),
        cycle_s=round(statistics.median(c), 1) if (c := [i["cycle_s"] for i in counted if i["cycle_s"]]) else None,
        latency_ms=round(statistics.median(c)) if (c := [i["latency_ms"] for i in items if i["latency_ms"]]) else None,
        shared="shared" if shared else "local only" if kind in ("collect", "sort") else "not shared (by design)",
        flag=flag, what=note.get("what"), note=note.get("note"), truth_source=note.get("truth_source"),
        exclude=exclude, extras=extras, judge_rows=len(judge),
        judge_results=dict(Counter(str(j.get("result")) for j in judge)), items=items)


def scan_experiment(d: Path):
    start = run_clock(d.name, "laptop")
    images = sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.suffix.lower() in IMG and "dash" not in p.parts)
    reports = {}
    for p in sorted(d.glob("*.json")):
        text = p.read_text(errors="replace")
        reports[p.name] = text if len(text) <= 6000 else text[:6000] + "\n... (truncated; open the file)"
    return dict(name=d.name, est=start.astimezone(EST).strftime("%H:%M") if start else "",
                start=start.astimezone(timezone.utc).isoformat() if start else None, images=images, reports=reports)


def scan(runs: Path):
    shared_file = read_json(runs / "_shared" / "index.json") or {}
    shared_index = shared_file.get("runs", {})
    notes_file = read_json(ROOT / "docs" / "run_notes.json") or {}
    notes = notes_file.get("runs", {})
    models, usage = load_models(runs)
    data, experiments, loose = [], [], []
    for p in sorted(runs.iterdir()):
        if p.name.startswith(("_", ".")) or p.name in ("index.html", "catalog.json"):
            continue
        if p.is_file():
            loose.append(p.name)
            continue
        kind = next((k for k in ("collect", "sort", "dry") if p.name.endswith("_" + k)), None)
        if (p / "decisions.jsonl").exists() and kind in ("collect", "sort"):
            data.append(scan_run(p, kind, shared_index, usage, notes))
        elif kind == "dry" or (p / "judge.jsonl").exists():
            data.append(scan_run(p, "dry", shared_index, usage, notes))
        elif any(q.suffix.lower() in IMG or q.suffix == ".json" for q in p.iterdir() if q.is_file()) or \
                any(q.is_dir() and q.name != "dash" for q in p.iterdir()):
            experiments.append(scan_experiment(p))
        else:
            data.append(scan_run(p, "dry", shared_index, usage, notes))     # dashboard cache only
    data.sort(key=lambda r: (r["start"] or "", r["name"]))
    experiments.sort(key=lambda e: (e["start"] or "", e["name"]))
    missing = sorted(set(shared_index) - {r["name"] for r in data})
    return dict(generated=datetime.now(EST).isoformat(timespec="seconds"), snapshot=shared_file.get("_snapshot"),
                runs=data, experiments=experiments, loose=loose, models=models, flags=FLAGS, outcomes=OUTCOMES,
                not_in_data=notes_file.get("not_in_data", []), shared_not_here=missing, summary=summarize(data))


def summarize(data):
    """Usable captures per part x label (current recipe / legacy), and what the sort runs did."""
    cells = {"current": Counter(), "caution": Counter(), "legacy": Counter()}
    sort = Counter()
    for r in data:
        if r["kind"] == "sort":
            for i in r["items"]:
                sort[i["outcome"]] += 1
            continue
        if r["kind"] != "collect" or r["flag"] in ("exclude", "empty"):
            continue
        for i in r["items"]:
            if i["outcome"] != "captured" or i["excluded"]:
                continue
            key = f"{i['type'] or 'unknown'}|{i['label'] or 'unknown'}"
            if i["recipe"] != CURRENT_RECIPE:
                cells["legacy"][key] += 1
            elif r["flag"] in ("caution", "probe"):
                cells["caution"][key] += 1
            else:
                cells["current"][key] += 1
    kinds = Counter(r["kind"] for r in data)
    return dict(cells={k: dict(v) for k, v in cells.items()}, sort=dict(sort), kinds=dict(kinds),
                attempts=sum(r["attempts"] for r in data if r["kind"] in ("collect", "sort")),
                captured=sum(r["captured"] for r in data), images=sum(r["images"] for r in data))


# ---------- markdown ----------

def matrix_md(cells, title):
    if not cells:
        return []
    types = sorted({k.split("|")[0] for k in cells})
    labels = sorted({k.split("|")[1] for k in cells}, key=lambda x: (x != "good", x))
    out = [f"**{title}**", "", "| Part | " + " | ".join(labels) + " | Total |", "|---|" + "---:|" * (len(labels) + 1)]
    for t in types:
        vals = [cells.get(f"{t}|{lab}", 0) for lab in labels]
        out.append(f"| `{t}` | " + " | ".join(str(v) if v else "·" for v in vals) + f" | {sum(vals)} |")
    tot = [sum(cells.get(f"{t}|{lab}", 0) for t in types) for lab in labels]
    out += ["| **Total** | " + " | ".join(str(v) for v in tot) + f" | **{sum(tot)}** |", ""]
    return out


def counts(d):
    return ", ".join(f"{k} {v}" if len(d) > 1 else k for k, v in sorted(d.items(), key=lambda kv: -kv[1])) or "-"


def markdown(cat):
    s, snap = cat["summary"], cat["snapshot"] or {}
    L = ["# Run catalog: day 1 (2026-11-13)", "",
         "Generated by `python3 catalog.py` from the files under `runs/` and the notes in `docs/run_notes.json`. Do not edit by",
         "hand: fix the note or the data and regenerate. Browse the pictures with `open runs/index.html` (same data, with",
         "every image, `meta.json` and decision row per pick).", "",
         f"Generated {cat['generated']}. Shared repo snapshot: `{str(snap.get('commit'))[:8]}`"
         f" (last modified {snap.get('last_modified')})." if snap else f"Generated {cat['generated']}.", "",
         f"{s['kinds'].get('collect', 0)} collect runs, {s['kinds'].get('sort', 0)} sort runs, {s['kinds'].get('dry', 0)} dry runs, "
         f"{len(cat['experiments'])} camera / calibration experiments. {s['attempts']} pick attempts, "
         f"{s['captured']} captured in collect mode, {s['images']} images.", "",
         "## What is usable", "",
         "A **captured** pick = the part was grasped, held in front of the webcam and logged (`decision: collect`). Counts",
         "below leave out items listed in a run's `exclude.json` and runs flagged `exclude` or `empty`. Repeated picks of",
         "one physical part are not independent samples: most cells below are a single specimen picked many times.", ""]
    L += matrix_md(s["cells"]["current"], "Current recipe (cardboard pad, wrist 1280x720, lamp LED): runs flagged ok / partial")
    L += matrix_md(s["cells"]["caution"], "Current recipe, but flagged caution / probe: look at the images before using")
    L += matrix_md(s["cells"]["legacy"], "Legacy recipe (before 17:07: wrist 640x480, background not recorded)")
    so = s["sort"]
    L += ["Sort runs (6): " + ", ".join(f"{OUTCOMES[k]} {v}" for k, v in sorted(so.items(), key=lambda kv: -kv[1]))
          + ". Their parts carry no ground-truth label in the data; where the log recorded it, the note says so.", "",
          "## Runs in real time order", "",
          "Clock: EST = laptop and `AGENT_LOG.md`; station run names are MST (2 h earlier). `cap/att` = captured (or, for a sort",
          "run, picked and decided) / attempts. Flags: " + "; ".join(f"`{k}` {v}" for k, v in FLAGS.items()) + ".", "",
          "| EST | Run | Host | Part · label | cap/att | Flag | What happened |", "|---|---|---|---|---:|---|---|"]
    for r in cat["runs"]:
        if r["kind"] == "dry":
            continue
        done = r["captured"] if r["kind"] == "collect" else sum(r["outcomes"].get(k, 0) for k in ("good", "reject", "dropped"))
        part = f"{counts(r['types'])} · {counts(r['labels'])}" if r["types"] or r["labels"] else "-"
        if r["kind"] == "sort":
            part = "mixed · " + ", ".join(f"{OUTCOMES[k]} {v}" for k, v in r["outcomes"].items())
        text = " ".join(x for x in (r["what"] and r["what"].rstrip(".") + ".", r["note"]) if x)
        if r["excluded"]:
            text += f" ({r['excluded']} in exclude.json)"
        L.append(f"| {r['est']} | `{r['name']}` | {r['host']} | {part} | {done}/{r['attempts']} | {r['flag'] or ''} | {text} |")
    L += ["", "## Models", "", "| Bundle | Where | Crop policy | Banks (types) | Picks train / cal / test | Built from |", "|---|---|---|---|---|---|"]
    for m in cat["models"]:
        where = m["where"] + ("" if m["shared"] else "; NOT in the shared repo")
        L.append(f"| `{m['name']}`: {'; '.join(m['files'])} | {where} | {m['crop_policy']} | {m['banks']} ({', '.join(m['types'])}; "
                 f"{', '.join(m['backgrounds'])}) | {m['picks']['train']} / {m['picks']['calibration']} / {m['picks']['test']} | "
                 + ", ".join(f"`{k[9:]}` {v}" for k, v in m["runs"].items()) + " |")
    L += ["", "Pick counts are unions over a bundle's views. Per-pick membership (train / calibration / test) is on each pick's",
          "card in `runs/index.html`.", "", "## Recorded only in the log, not in this data", ""]
    for n in cat["not_in_data"]:
        L.append(f"- **{n['name']}** ({n['when']}): {n['what']}. {n['note']}")
    if cat["shared_not_here"]:
        L += ["", "Shared runs missing on this machine (`python sync_data.py pull`): " + ", ".join(f"`{n}`" for n in cat["shared_not_here"])]
    dry = [r for r in cat["runs"] if r["kind"] == "dry"]
    L += ["", "## Camera and calibration experiments (laptop, `runs/<name>/`)", "", "| EST | Folder | Images | Reports |", "|---|---|---:|---|"]
    for e in cat["experiments"]:
        L.append(f"| {e['est']} | `{e['name']}` | {len(e['images'])} | {', '.join(e['reports']) or '-'} |")
    L += ["", f"Loose review images and files in `runs/`: {', '.join(f'`{n}`' for n in cat['loose'])}.", "",
          f"## Dry runs ({len(dry)})", "",
          "No motion and no images; `judge.jsonl` and the dashboard cache only (each run of `tests/test_pipeline.py` adds "
          "one). " +
          ", ".join(f"`{r['name']}` ({r['judge_rows']})" for r in dry) + ". Number = rows in `judge.jsonl`.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", type=Path, default=ROOT / "runs")
    ap.add_argument("--refresh", action="store_true", help="re-download the shared index and model manifests first")
    ap.add_argument("--no-md", action="store_true", help="do not rewrite docs/RUN_CATALOG.md")
    args = ap.parse_args()
    runs = args.runs.resolve()
    if args.refresh:
        refresh_shared(runs)
    cat = scan(runs)
    (runs / "catalog.json").write_text(json.dumps(cat, indent=1))
    page = (ROOT / "catalog.html").read_text().replace(
        "__CATALOG_JSON__", json.dumps(cat, separators=(",", ":")).replace("</", "<\\/"))
    (runs / "index.html").write_text(page)
    if not args.no_md:
        slim = dict(cat, runs=[{k: v for k, v in r.items() if k != "items"} for r in cat["runs"]])
        (ROOT / "docs" / "RUN_CATALOG.md").write_text(markdown(slim))
    s = cat["summary"]
    print(f"{len(cat['runs'])} runs ({s['kinds']}), {len(cat['experiments'])} experiments, {s['attempts']} attempts, "
          f"{s['captured']} captured, {s['images']} images, {len(cat['models'])} model manifests")
    print(f"open {(runs / 'index.html').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
