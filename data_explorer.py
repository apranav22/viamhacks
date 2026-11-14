"""Read-only collection browser. Integrated at /explore on train_dashboard.py.

Reads saved images/metadata and Linux process state; never imports the robot SDK.
"""
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

_lock = threading.Lock()
_cache = {}


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def classify_process(args):
    """Only classify actual Python script arguments, never shell command text."""
    if not args or not Path(args[0]).name.startswith('python'):
        return None
    scripts = {'train_anomaly.py': 'training', 'benchmark_anomaly.py': 'evaluation',
               'replay_anomaly.py': 'replay', 'sort.py': 'sorting'}
    for i, arg in enumerate(args[1:], 1):
        if arg.startswith('-'):
            continue
        name = Path(arg).name
        if name not in scripts:
            return None
        if name == 'sort.py':
            rest = args[i + 1:]
            mode = next((a.split('=', 1)[1] for a in rest if a.startswith('--mode=')), None)
            if '--mode' in rest:
                j = rest.index('--mode')
                mode = rest[j + 1] if j + 1 < len(rest) else None
            return 'collection' if mode == 'collect' else 'sorting' if mode == 'sort' else None
        return scripts[name]
    return None


def activity():
    states = {k: [] for k in ('collection', 'training', 'evaluation', 'sorting', 'replay')}
    proc = Path('/proc')
    if not proc.is_dir():
        return {'known': False, 'states': states, 'reason': 'Process monitoring requires Linux on the station.'}
    denied = False
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            args = (p / 'cmdline').read_bytes().decode(errors='replace').split('\0')
        except PermissionError:
            denied = True
            continue
        except OSError:
            continue  # exited between directory listing and read
        kind = classify_process(args)
        if kind:
            states[kind].append(int(p.name))
    return {'known': not denied, 'states': states,
            'reason': 'Some processes could not be inspected.' if denied else 'Station Python processes; no robot RPCs.'}


def scan(runs):
    root = Path(runs).resolve()
    records, paths, warnings = [], {}, 0
    if not root.is_dir():
        return records, paths, ['Collection directory unavailable.']
    seen = set()
    for run in sorted(root.iterdir()):
        if not run.is_dir() or not run.resolve().is_relative_to(root):
            continue
        decisions = {}
        try:
            for line in (run / 'decisions.jsonl').read_text().splitlines():
                try:
                    row = json.loads(line)
                    decisions[str(row.get('item'))] = row
                except (ValueError, AttributeError):
                    warnings += 1
        except OSError:
            pass
        for item in sorted(run.glob('item_*')):
            if not item.is_dir() or not item.resolve().is_relative_to(root):
                continue
            meta = read_json(item / 'meta.json')
            if not isinstance(meta, dict):
                meta = {}
            key = item.name.removeprefix('item_').lstrip('0') or '0'
            dec = decisions.get(key, {})
            for f in sorted(item.iterdir()):
                if f.suffix.lower() not in ('.jpg', '.jpeg', '.png'):
                    continue
                try:
                    real = f.resolve()
                    if not real.is_relative_to(root) or real in seen or not real.is_file():
                        continue
                    st = real.stat()
                except OSError:
                    continue
                seen.add(real)
                ident = hashlib.sha256(str(f.relative_to(root)).encode()).hexdigest()[:24]
                paths[ident] = real
                name = f.stem
                camera = 'wrist' if name.startswith(('top_', 'watch')) else 'webcam' if name.startswith(('web_', 'crop_')) else 'unknown'
                view = 'top' if name.startswith('top_') else name.removeprefix('web_').removeprefix('crop_')
                records.append(dict(id=ident, run=run.name, item=item.name, filename=f.name,
                    label=meta.get('label') or dec.get('label') or 'unknown',
                    part=meta.get('type') or dec.get('type') or 'unknown',
                    pose=meta.get('pose') or dec.get('pose') or 'unknown',
                    background=meta.get('background') or 'unknown', camera=camera, view=view,
                    kind='crop' if name.startswith('crop_') else 'frame', modified=st.st_mtime,
                    decision=meta.get('decision') or dec.get('decision') or 'unknown',
                    metadata=meta, decision_record=dec))
    return records, paths, [f'{warnings} incomplete/invalid decision rows skipped.'] if warnings else []


def index(runs):
    key = str(Path(runs).resolve())
    with _lock:
        now = time.monotonic()
        if key not in _cache or now - _cache[key][0] > 2:
            _cache[key] = (now, *scan(runs))
        return _cache[key][1:]


def handle(handler, runs):
    url = urlsplit(handler.path)
    if url.path == '/explore':
        handler.send(200, Path(__file__).with_suffix('.html').read_bytes(), 'text/html; charset=utf-8')
    elif url.path == '/api/explore':
        records, _, warnings = index(runs)
        handler.send(200, json.dumps(dict(host=os.uname().nodename, checked=time.time(),
            records=records, warnings=warnings, activity=activity())))
    elif url.path == '/api/explore/image':
        ident = parse_qs(url.query).get('id', [''])[0]
        _, paths, _ = index(runs)
        f = paths.get(ident)
        root = Path(runs).resolve()
        try:
            if f is None or not f.resolve().is_relative_to(root):
                raise FileNotFoundError
            handler.send(200, f.read_bytes(), 'image/png' if f.suffix.lower() == '.png' else 'image/jpeg')
        except OSError:
            handler.send(404, '{}')
    else:
        return False
    return True
