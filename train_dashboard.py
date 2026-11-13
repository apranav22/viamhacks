"""Training dashboard: runs ON THE INTEL STATION next to the data and models. Stdlib HTTP, no robot connection.

    cd /opt/viam/sorter-ali/current && ../../.venv/bin/python3.12 train_dashboard.py      # http://172.16.0.182:8770
    python train_dashboard.py --port 8770                                                  # local dev (laptop)

What it shows (refreshes every 3 s):
  Data     every collect run in runs/: picks by part type / label / pose, wrist frame size, camera settings,
           and how many picks each model view can train on (same rules as vh/anomaly_data.py)
  Models   every bundle in models/: per view the train/calibration/test picks, threshold, held-out scores as a strip
           (good = green, defect = red, threshold = line), false rejects, defects caught, margin, fit device;
           device benchmarks (CPU/GPU/NPU p50/p90); which bundle is ACTIVE for sort.py --anomaly-bundle active
  Jobs     training / benchmark jobs started here: live log tail, duration, exit code
Actions:   train a new bundle (PatchCore features on the Arc GPU via XPU, then a CPU/GPU/NPU benchmark),
           benchmark an existing bundle, make a bundle ACTIVE.
Guard:     refuses to start a job while a judged run (sort.py --mode sort) is running, and runs one job at a time.
"""

import argparse
import html
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent                  # the release (or the repo on a laptop)
RUNS, MODELS = ROOT / "runs", ROOT / "models"
SHARED = RUNS.resolve().parent                          # /opt/viam/sorter-ali on the station
JOBS = SHARED / "jobs"
TRAIN_PY = SHARED / ".train-venv" / "bin" / "python3.12"
RUNTIME_PY = SHARED / ".venv" / "bin" / "python3.12"
TRAIN_PY = str(TRAIN_PY) if TRAIN_PY.exists() else sys.executable
RUNTIME_PY = str(RUNTIME_PY) if RUNTIME_PY.exists() else sys.executable
NAME_OK = re.compile(r"^[A-Za-z0-9_.-]{1,60}$")


# ---------------------------------------------------------------------------------------------------- data
def scan_data():
    runs, totals, eligible = [], Counter(), Counter()
    for d in sorted(RUNS.glob("*_collect")):
        f = d / "decisions.jsonl"
        if not f.exists():
            continue
        rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        picks = [r for r in rows if r.get("decision") == "collect"]
        kinds = Counter((r.get("type"), r.get("label"), r.get("pose")) for r in picks)
        sizes, cams, with_meta = Counter(), set(), 0
        for r in picks:
            m = d / f"item_{r['item']:03d}" / "meta.json"
            if not m.exists():
                continue
            with_meta += 1
            meta = json.loads(m.read_text())
            for k, v in (meta.get("top") or {}).items():
                if v.get("bbox"):
                    sizes[_jpeg_size(d / f"item_{r['item']:03d}" / f"{k}.jpg")] += 1
            if meta.get("camera"):
                cams.add(json.dumps(meta["camera"], sort_keys=True)[:120])
            if meta.get("background"):
                cams.add("background " + meta["background"])
            for view in (meta.get("views") or {}):
                eligible[(r.get("label"), r.get("pose"), view)] += 1
            if any(v.get("bbox") for v in (meta.get("top") or {}).values()):
                eligible[(r.get("label"), r.get("pose"), "top")] += 1
        for k, n in kinds.items():
            totals[k] += n
        runs.append({"run": d.name, "picks": len(picks), "with_meta": with_meta, "attempts": len(rows),
                     "kinds": [[*k, n] for k, n in kinds.most_common()],
                     "top_sizes": [f"{w}x{h}: {n}" for (w, h), n in sizes.items()], "camera": sorted(cams),
                     "mtime": d.stat().st_mtime})
    return {"runs": runs[::-1], "totals": [[*k, n] for k, n in totals.most_common()],
            "eligible": [[*k, n] for k, n in sorted(eligible.items(), key=lambda kv: (str(kv[0]), -kv[1]))]}


def _jpeg_size(p):
    try:
        from PIL import Image
        with Image.open(p) as im:
            return im.size
    except Exception:
        return (0, 0)


# -------------------------------------------------------------------------------------------------- models
def scan_models():
    active = (MODELS / "ACTIVE").read_text().strip() if (MODELS / "ACTIVE").exists() else ""
    out = []
    for b in sorted(MODELS.glob("*/bundle.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            bundle = json.loads(b.read_text())
        except ValueError:
            continue
        groups = []
        for key, e in sorted(bundle.get("models", {}).items()):
            tr = e.get("test_results") or []
            thr = e.get("threshold") or 0
            good = [t["score"] for t in tr if t.get("label") == "good"]
            bad = [t["score"] for t in tr if t.get("label") not in (None, "good")]
            groups.append({
                "key": key, "view": e.get("view"), "pose": e.get("pose"), "type": e.get("part_type"),
                "background": e.get("background"), "threshold": thr, "bank": e.get("bank_size"),
                "n_train": len(e.get("train_pick_ids", [])), "n_cal": len(e.get("calibration_pick_ids", [])),
                "n_test_good": len(good), "n_test_bad": len(bad),
                "false_rejects": sum(s >= thr for s in good), "caught": sum(s >= thr for s in bad),
                "margin": (thr - max(good)) / thr if good and thr else None,
                "good": good, "bad": bad, "fit": (e.get("fit_execution") or {}).get("feature_device"),
                "ov_vs_torch": e.get("max_torch_openvino_score_difference")})
        devices = {}
        for rep in sorted(b.parent.glob("*report*.json")):
            try:
                r = json.loads(rep.read_text())
            except ValueError:
                continue
            for dev, d in (r.get("devices") or {}).items():
                if d.get("status") == "ok":
                    devices[dev] = {"p50": d.get("p50_ms"), "p90": d.get("p90_ms"), "name": d.get("full_device_name"),
                                    "agree": (d.get("vs_cpu") or {}).get("decision_agreement"), "file": rep.name}
                else:
                    devices.setdefault(dev, {"error": (d.get("error") or "")[:160], "file": rep.name})
        skipped = Counter(s.get("reason", "?")[:70] for s in bundle.get("skipped", []))
        out.append({"name": b.parent.name, "path": str(b.relative_to(ROOT)), "active": str(b.relative_to(ROOT)) == active,
                    "mtime": b.stat().st_mtime, "groups": groups, "devices": devices,
                    "skipped": skipped.most_common(6), "limitations": bundle.get("limitations", [])})
    return out, active


# ---------------------------------------------------------------------------------------------------- jobs
def jobs():
    JOBS.mkdir(parents=True, exist_ok=True)
    out = []
    for j in sorted(JOBS.glob("*.json"), reverse=True)[:12]:
        job = json.loads(j.read_text())
        log = JOBS / f"{job['id']}.log"
        ex = JOBS / f"{job['id']}.exit"
        job["exit"] = ex.read_text().strip() if ex.exists() else None
        job["running"] = job["exit"] is None and _alive(job.get("pid"))
        if job["exit"] is None and not job["running"]:
            job["exit"] = "lost"
        job["elapsed"] = round((float(ex.stat().st_mtime) if ex.exists() else time.time()) - job["started"], 1)
        tail = log.read_text(errors="replace").splitlines()[-400:] if log.exists() else []
        job["log"] = [l for l in tail if not re.search(r"Warning|warn\(|warnings\.|^\s*$|it/s\]$", l)][-40:]
        out.append(job)
    return out


def _alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def judged_run_active():
    try:
        ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return False
    return any("sort.py" in l and "--mode sort" in l for l in ps.splitlines())


def start_job(kind, cmd, label):
    if any(j["running"] for j in jobs()):
        raise ValueError("a job is already running (one at a time: they share the GPU)")
    if judged_run_active():
        raise ValueError("a judged run (sort.py --mode sort) is running: not competing with it for the GPU")
    jid = time.strftime("%Y%m%d_%H%M%S") + "_" + kind
    log, ex = JOBS / f"{jid}.log", JOBS / f"{jid}.exit"
    shell = f"cd {shlex.quote(str(ROOT))} && ( {cmd} ) > {shlex.quote(str(log))} 2>&1; echo $? > {shlex.quote(str(ex))}"
    p = subprocess.Popen(["bash", "-c", shell], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (JOBS / f"{jid}.json").write_text(json.dumps({"id": jid, "kind": kind, "label": label, "cmd": cmd, "pid": p.pid,
                                                  "started": time.time()}))
    return jid


def bench_cmd(name):
    q = shlex.quote
    return (f"{q(RUNTIME_PY)} benchmark_anomaly.py --bundle models/{q(name)}/bundle.json --dataset models/{q(name)}/dataset/"
            f"dataset.json --devices CPU GPU NPU --repeat 5 --out models/{q(name)}/device_report.json")


def action(body):
    a = body.get("action")
    if a == "train":
        name = body.get("name", "")
        if not NAME_OK.match(name) or (MODELS / name).exists():
            raise ValueError("model name: letters/digits/_-. only, and must be new")
        typ, bg, dev = body.get("type") or "any", body.get("background") or "white", body.get("device") or "xpu"
        if bg not in ("white", "cardboard") or dev not in ("xpu", "cpu") or not NAME_OK.match(typ):
            raise ValueError("bad type/background/device")
        runs = body.get("runs") or [r.name for r in sorted(RUNS.glob("*_collect"))]
        if not runs or any(not NAME_OK.match(r) or not (RUNS / r).is_dir() for r in runs):
            raise ValueError("bad run list")
        q = shlex.quote
        cmd = (f"{q(TRAIN_PY)} train_anomaly.py --runs {' '.join('runs/' + q(r) for r in runs)} --type {q(typ)} "
               f"--background {bg} --train-device {dev} --out models/{q(name)} && {bench_cmd(name)}")
        return {"job": start_job("train", cmd, f"train {name}: type {typ}, {bg}, {len(runs)} runs, features on {dev}")}
    if a == "bench":
        name = body.get("name", "")
        if not NAME_OK.match(name) or not (MODELS / name / "bundle.json").exists():
            raise ValueError("no such bundle")
        return {"job": start_job("bench", bench_cmd(name), f"benchmark {name} on CPU/GPU/NPU")}
    if a == "activate":
        name = body.get("name", "")
        if not NAME_OK.match(name) or not (MODELS / name / "bundle.json").exists():
            raise ValueError("no such bundle")
        (MODELS / "ACTIVE").write_text(f"models/{name}/bundle.json\n")
        return {"active": f"models/{name}/bundle.json"}
    raise ValueError("unknown action")


# ------------------------------------------------------------------------------------------------------ http
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            return self.send(200, PAGE, "text/html; charset=utf-8")
        if self.path == "/api/state":
            models, active = scan_models()
            return self.send(200, json.dumps({"host": os.uname().nodename, "now": time.time(), "data": scan_data(),
                                              "models": models, "active": active, "jobs": jobs(),
                                              "judged_run": judged_run_active(), "train_py": TRAIN_PY}))
        self.send(404, "{}")

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            self.send(200, json.dumps(action(body)))
        except ValueError as e:
            self.send(400, json.dumps({"error": str(e)}))


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Training · Spot it, sort it</title><style>
:root{--bg:#0a0f1e;--pan:#111a30;--line:#1f2b48;--ink:#e6ecff;--mute:#8090b8;--gr:#22c55e;--rd:#ef4444;--am:#f59e0b;--cy:#22d3ee}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.45 -apple-system,Segoe UI,Inter,sans-serif}
header{display:flex;gap:16px;align-items:center;padding:10px 18px;background:#0d1730;border-bottom:1px solid var(--line);position:sticky;top:0}
h1{font-size:16px;margin:0}h2{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--mute);margin:0 0 8px}
main{padding:12px 18px;display:grid;gap:12px;grid-template-columns:1fr 1fr}.p{background:var(--pan);border:1px solid var(--line);border-radius:10px;padding:12px}
.w{grid-column:span 2}table{border-collapse:collapse;width:100%}td,th{padding:4px 7px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mute);font-size:11px;text-transform:uppercase}.ok{color:var(--gr)}.bad{color:var(--rd)}.warn{color:var(--am)}.mute{color:var(--mute)}
pre{background:#060a15;padding:8px;border-radius:6px;max-height:260px;overflow:auto;font-size:11px;margin:6px 0 0}
button,input,select{background:#1a2442;color:var(--ink);border:1px solid #2b3a63;border-radius:6px;padding:4px 9px;font:inherit}
button{cursor:pointer}button.on{background:#14532d;border-color:var(--gr)}.tag{padding:1px 7px;border-radius:9px;background:#1e293b;font-size:11px}
.model{border-top:1px solid var(--line);padding-top:10px;margin-top:10px}</style></head><body>
<header><h1>Training · Intel station</h1><span id="host" class="mute"></span><span id="active" class="tag"></span><span id="judged"></span><span style="flex:1"></span><span id="ts" class="mute"></span></header>
<main>
<section class="p"><h2>Train a new bundle</h2>
 name <input id="nm" size="18"> type <input id="ty" value="any" size="10"> background <select id="bg"><option>white</option><option>cardboard</option></select>
 features on <select id="dv"><option value="xpu">Arc GPU (xpu)</option><option value="cpu">CPU</option></select>
 <button onclick="train()">Train + benchmark</button>
 <div class="mute" style="margin-top:6px">Uses every collect run checked below (default: all). PatchCore: frozen ResNet18 features on the chosen device, coreset + OpenVINO export on CPU, threshold from calibration picks (good only), held-out test scores, then CPU/GPU/NPU benchmark.</div>
 <div id="msg" class="warn"></div></section>
<section class="p"><h2>Data the models can learn from</h2><div id="elig"></div></section>
<section class="p w"><h2>Models</h2><div id="models"></div></section>
<section class="p w"><h2>Jobs</h2><div id="jobs"></div></section>
<section class="p w"><h2>Collect runs</h2><div id="runs"></div></section>
</main><script>
const $=id=>document.getElementById(id), e=s=>String(s??"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const t=s=>new Date(s*1000).toLocaleTimeString([], {hour12:false}); let S=null, sel=null;
async function post(b){const r=await fetch("/api",{method:"POST",body:JSON.stringify(b)});const j=await r.json();$("msg").textContent=j.error||"";load();return j;}
function train(){post({action:"train",name:$("nm").value.trim(),type:$("ty").value.trim(),background:$("bg").value,device:$("dv").value,runs:sel?[...sel]:null});}
function strip(g){const all=[...g.good,...g.bad,g.threshold],mx=Math.max(...all)*1.08||1,mn=Math.min(...all)*0.85,X=v=>8+(v-mn)/(mx-mn)*284;
 let s=`<svg width="300" height="26"><line x1="8" y1="13" x2="292" y2="13" stroke="#1f2b48"/><line x1="${X(g.threshold)}" y1="2" x2="${X(g.threshold)}" y2="24" stroke="#f59e0b" stroke-width="2"/>`;
 g.good.forEach(v=>s+=`<circle cx="${X(v)}" cy="9" r="4" fill="${v>=g.threshold?"#ef4444":"#22c55e"}"><title>good ${v.toFixed(2)}</title></circle>`);
 g.bad.forEach(v=>s+=`<rect x="${X(v)-4}" y="13" width="8" height="8" fill="${v>=g.threshold?"#ef4444":"#64748b"}"><title>defect ${v.toFixed(2)}</title></rect>`);
 return s+"</svg>";}
function render(){const s=S; $("host").textContent=s.host+" · trainer "+s.train_py; $("active").textContent="ACTIVE: "+(s.active||"none");
 $("judged").innerHTML=s.judged_run?'<b class="bad">JUDGED RUN IN PROGRESS: jobs blocked</b>':""; $("ts").textContent="updated "+t(s.now);
 const el=s.data.eligible; $("elig").innerHTML=`<table><tr><th>label</th><th>pose</th><th>view</th><th>picks</th></tr>`+el.map(r=>`<tr><td class="${r[0]=="good"?"ok":"bad"}">${e(r[0])}</td><td>${e(r[1])}</td><td>${e(r[2])}</td><td>${r[3]}${r[3]<8?' <span class="warn">(few)</span>':""}</td></tr>`).join("")+"</table>"+
  `<div class="mute" style="margin-top:6px">Counts picks with meta.json. A view needs ≥ ~4 good picks to get train/calibration/test; thresholds from 2 calibration picks are noisy. Defect picks only go to test (recall).</div>`;
 $("models").innerHTML=s.models.map(m=>{const fr=m.groups.reduce((a,g)=>a+g.false_rejects,0), ng=m.groups.reduce((a,g)=>a+g.n_test_good,0), nb=m.groups.reduce((a,g)=>a+g.n_test_bad,0), ca=m.groups.reduce((a,g)=>a+g.caught,0);
  const dev=Object.entries(m.devices).map(([d,v])=>v.error?`${d} <span class="bad">failed</span>`:`${d} <b>${v.p50.toFixed(1)}</b>/${v.p90.toFixed(1)} ms${v.agree!=null?` <span class="mute">(agrees with CPU ${Math.round(100*v.agree)}%)</span>`:""}`).join(" · ")||'<span class="mute">not benchmarked</span>';
  return `<div class="model"><b style="font-size:14px">${e(m.name)}</b> ${m.active?'<span class="tag ok">ACTIVE</span>':`<button onclick="post({action:'activate',name:'${e(m.name)}'})">make active</button>`} <button onclick="post({action:'bench',name:'${e(m.name)}'})">benchmark</button>
  <span class="mute">${t(m.mtime)}</span> · held-out good views: <b class="${fr?"bad":"ok"}">${ng-fr}/${ng} pass</b> · defects caught: <b class="${nb?(ca==nb?"ok":"warn"):"mute"}">${nb?ca+"/"+nb:"no defect test data"}</b><br>inference p50/p90: ${dev}
  <table style="margin-top:6px"><tr><th>view</th><th>pose</th><th>type · bg</th><th>train/cal/test</th><th>bank</th><th>threshold</th><th>held-out scores (● good ■ defect | threshold)</th><th>margin</th><th>fit on</th></tr>`+
  m.groups.map(g=>`<tr><td><b>${e(g.view)}</b></td><td>${e(g.pose)}</td><td>${e(g.type)} · ${e(g.background)}</td><td>${g.n_train}/${g.n_cal}/${g.n_test_good+g.n_test_bad}</td><td>${g.bank??"–"}</td><td>${g.threshold.toFixed(2)}</td><td>${strip(g)}</td>
  <td class="${g.margin==null?"mute":g.margin<0?"bad":g.margin<0.05?"warn":"ok"}">${g.margin==null?"–":(100*g.margin).toFixed(1)+"%"}</td><td>${e(g.fit)}</td></tr>`).join("")+`</table>`+
  (m.skipped.length?`<div class="mute">skipped: ${m.skipped.map(([r,n])=>e(r)+" ×"+n).join(" · ")}</div>`:"")+`</div>`;}).join("")||'<span class="mute">no bundles yet</span>';
 $("jobs").innerHTML=s.jobs.map(j=>`<div style="margin-bottom:10px"><b>${e(j.label)}</b> <span class="${j.running?"warn":j.exit=="0"?"ok":"bad"}">${j.running?"running":"exit "+e(j.exit)}</span> <span class="mute">${t(j.started)} · ${j.elapsed}s</span><pre>${e(j.log.join("\n"))}</pre></div>`).join("")||'<span class="mute">no jobs yet</span>';
 if(sel===null) sel=new Set(s.data.runs.map(r=>r.run));
 $("runs").innerHTML=`<table><tr><th>use</th><th>run</th><th>picks (meta)</th><th>type · label · pose</th><th>wrist frame</th><th>camera / background</th></tr>`+s.data.runs.map(r=>`<tr><td><input type="checkbox" ${sel.has(r.run)?"checked":""} onchange="this.checked?sel.add('${e(r.run)}'):sel.delete('${e(r.run)}')"></td><td>${e(r.run)}</td><td>${r.picks} (${r.with_meta})</td><td>${r.kinds.map(k=>`${e(k[0])} · <span class="${k[1]=="good"?"ok":"bad"}">${e(k[1])}</span> · ${e(k[2])} ×${k[3]}`).join("<br>")}</td><td>${e(r.top_sizes.join(", "))}</td><td class="mute">${e(r.camera.join(" | "))}</td></tr>`).join("")+"</table>";}
async function load(){try{S=await (await fetch("/api/state")).json(); render();}catch(err){$("ts").textContent="dashboard unreachable";}}
load(); setInterval(load,3000);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8770)
    a = ap.parse_args()
    JOBS.mkdir(parents=True, exist_ok=True)
    print(f"training dashboard: http://{a.host}:{a.port}  (runs {RUNS.resolve()}, models {MODELS.resolve()}, jobs {JOBS})", flush=True)
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()


if __name__ == "__main__":
    main()
