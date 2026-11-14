"""Read-only run/capture history for the unified dashboard. No robot or model imports.

[codex/unknown · op Ali (git: Ali, github: Armib20) · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]
"""
import hashlib
import json
import math
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

IMAGES = {'.jpg', '.jpeg', '.png', '.webp'}
VIEWS = ['front', 'yaw-20', 'yaw+35', 'pitch-25']


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def read_rows(path):
    rows = []
    try:
        with path.open() as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        rows.append(row)
                except ValueError:
                    pass                         # an active writer may not have finished its last line
    except OSError:
        pass
    return rows


def finite_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: finite_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_json(v) for v in value]
    return value


def view_of(name):
    stem = Path(name).stem
    return 'top' if stem.startswith('top_') else stem.removeprefix('web_')


def image_order(path):
    name = path.name
    if name.startswith('watch'):
        return (0, 0, name)
    if name.startswith('top_'):
        n = re.search(r'top_(\d+)', name)
        return (1, int(n[1]) if n else 0, name)
    view = view_of(name)
    return (2, VIEWS.index(view) if view in VIEWS else 20, name)


def trigger_detector(record):
    reason = record.get('reason', '').lower()
    if record.get('decision') != 'reject':
        return None
    if reason.startswith('known: tape'):
        return 'tape'
    if reason.startswith('anomaly:'):
        return 'anomalib'
    return None                              # uncertainty/recovery is not proof of a defect


class History:
    def __init__(self, root, notes=None):
        self.root = Path(root).resolve()
        self.notes_path = Path(notes) if notes else None
        self.lock = threading.RLock()
        self.cached = None
        self.checked = 0

    def path(self, relative, directory=False):
        p = Path(relative)
        if p.is_absolute() or '..' in p.parts or any(x.startswith('.') for x in p.parts):
            raise FileNotFoundError('Invalid history path')
        resolved = (self.root / p).resolve()
        if not resolved.is_relative_to(self.root) or not resolved.exists():
            raise FileNotFoundError('History file unavailable')
        if directory and not resolved.is_dir():
            raise FileNotFoundError('Not a directory')
        return resolved

    def media_url(self, path):
        return '/api/history/image?' + urlencode({'path': str(path.relative_to(self.root))})

    def _read(self, path):
        return read_json(path) if path.resolve().is_relative_to(self.root) else {}

    def _rows(self, path):
        return read_rows(path) if path.resolve().is_relative_to(self.root) else []

    def image(self, relative):
        p = self.path(relative)
        if p.suffix.lower() in IMAGES:
            mime = {'.png': 'image/png', '.webp': 'image/webp'}.get(p.suffix.lower(), 'image/jpeg')
            return p.read_bytes(), mime
        # Telemetry JPEGs have .bin names. Never expose arbitrary files via this endpoint.
        if p.suffix == '.bin' and p.parent.name == 'frames' and p.parent.parent.name == 'dash':
            data = p.read_bytes()
            if data.startswith(b'\xff\xd8'):
                return data, 'image/jpeg'
            if data.startswith(b'\x89PNG\r\n\x1a\n'):
                return data, 'image/png'
        raise FileNotFoundError('Not an image')

    def _images(self, directory, recursive=False):
        paths = directory.rglob('*') if recursive else directory.iterdir()
        return sorted((p for p in paths if p.is_file() and p.suffix.lower() in IMAGES
                       and p.resolve().is_relative_to(self.root) and 'dash' not in p.relative_to(directory).parts), key=image_order)

    def _notes(self):
        notes = read_json(self.notes_path) if self.notes_path else {}
        return notes.get('runs', {}) if isinstance(notes, dict) else {}

    def _run_info(self, path):
        rows = self._rows(path / 'decisions.jsonl')
        by_item = {str(r['item']): r for r in rows if isinstance(r.get('item'), int)}
        numbers = {int(p.name[5:]) for p in path.glob('item_*') if p.is_dir()
                   and p.name[5:].isdigit() and p.resolve().is_relative_to(self.root)}
        numbers.update(int(n) for n in by_item)
        items = []
        exclusions = self._read(path / 'exclude.json')
        if not isinstance(exclusions, dict):
            exclusions = {}
        for n in sorted(numbers):
            item_id = f'item_{n:03d}'
            d = path / item_id
            meta = self._read(d / 'meta.json') if d.exists() else {}
            meta = meta if isinstance(meta, dict) else {}
            record = by_item.get(str(n), {})
            images = self._images(d) if d.is_dir() else []
            items.append(dict(id=item_id, number=n, capture_count=sum(not p.name.startswith(('crop_', 'model_')) for p in images),
                              image_count=len(images), part=record.get('type') or meta.get('type'),
                              label=record.get('label') or (meta.get('label') if record.get('decision') == 'collect' else None),
                              decision=record.get('decision'), excluded=exclusions.get(item_id),
                              reason=record.get('reason'), latency_ms=record.get('latency_ms'), cycle_s=record.get('cycle_s')))
        root_images = self._images(path, recursive=not numbers)
        if numbers:
            root_images = [p for p in root_images if p.parent == path]
        if root_images:
            items.append(dict(id='_run', number=None, capture_count=len(root_images), image_count=len(root_images),
                              part=None, label=None, decision=None, reason='Run-level images', excluded=None))
        has_events = (path / 'dash' / 'events.jsonl').is_file()
        if not numbers and has_events:
            items.append(dict(id='_telemetry', number=None, capture_count=None, image_count=None,
                              part=None, label=None, decision=None, reason='Recorded telemetry', excluded=None))
        kind = next((k for k in ('collect', 'sort', 'dry') if path.name.endswith('_' + k)), 'experiment')
        if path.name.startswith('anomaly_replay'):
            kind = 'replay'
        started = next((r.get('t_seen') for r in rows if r.get('t_seen')), None)
        try:
            sort_time = datetime.fromisoformat(started).timestamp() if started else 0
        except (ValueError, TypeError):
            sort_time = 0
        return dict(id=path.name, kind=kind, started=started, sort_time=sort_time,
                    capture_count=sum(i['capture_count'] or 0 for i in items),
                    image_count=sum(i['image_count'] or 0 for i in items), item_count=len(items), items=items,
                    parts=sorted({i['part'] for i in items if i['part']}), has_events=has_events)

    def runs(self, refresh=False):
        with self.lock:
            if not refresh and self.cached and time.monotonic() - self.checked < 5:
                return self.cached
            notes = self._notes()
            runs, warnings = [], []
            if self.root.is_dir():
                for p in self.root.iterdir():
                    if not p.is_dir() or p.name.startswith(('.', '_')) or not p.resolve().is_relative_to(self.root):
                        continue
                    try:
                        info = self._run_info(p)
                        if not info['items'] and not (p / 'decisions.jsonl').exists() and not (p / 'judge.jsonl').exists():
                            continue
                        info.pop('items')
                        info['note'] = notes.get(p.name, {})
                        runs.append(info)
                    except OSError:
                        warnings.append(f'{p.name}: changed while scanning; refresh to retry')
            else:
                warnings.append('Runs directory unavailable')
            runs.sort(key=lambda r: (r['sort_time'], r['id']), reverse=True)
            self.cached = dict(runs=runs, warnings=warnings, checked=time.time(),
                               totals=dict(runs=len(runs), items=sum(r['item_count'] for r in runs),
                                           captures=sum(r['capture_count'] for r in runs)))
            self.checked = time.monotonic()
            return self.cached

    def run(self, run_id):
        if len(Path(run_id).parts) != 1 or run_id.startswith('_'):
            raise FileNotFoundError('Invalid run')
        p = self.path(run_id, directory=True)
        info = self._run_info(p)
        info['note'] = self._notes().get(run_id, {})
        return info

    def telemetry(self, run_id):
        folder = self.path(run_id, directory=True)
        events = []
        for event in self._rows(folder / 'dash' / 'events.jsonl'):
            # Retain inspection attempts and results; streaming previews aren't inspection captures.
            if event.get('k') in ('preview', 'arm_state', 'telemetry') or (event.get('k') == 'watch' and not event.get('placed')):
                continue
            if event.get('frame'):
                event['frame'] = dict(event['frame'])
                fid = str(event['frame'].get('id', ''))
                f = folder / 'dash' / 'frames' / f'{fid}.bin'
                if fid.isdigit() and f.is_file() and f.resolve().is_relative_to(self.root):
                    event['frame']['url'] = self.media_url(f)
                    event['frame']['ok'] = True
                else:
                    event['frame']['ok'] = False
            events.append(event)
        return events

    def evaluations(self, run_id, item_id, captures):
        results = []
        folder = self.root / '_analysis'
        if not folder.is_dir():
            return results
        for path in sorted(folder.glob('*.json')):
            if not path.resolve().is_relative_to(self.root):
                continue
            report = self._read(path)
            if not isinstance(report, dict) or report.get('schema') != 'dashboard-replay-v1':
                continue
            scores = {}
            for row in report.get('rows', []):
                if not isinstance(row, dict):
                    continue
                if row.get('pick') != f'{run_id}/{item_id}':
                    continue
                capture = next((c for c in captures if c['filename'] == row.get('file')), None)
                if not capture or not capture.get('path'):
                    continue
                p = self.path(capture['path'])
                expected_hash = row.get('image_sha256')
                verified = bool(expected_hash and hashlib.sha256(p.read_bytes()).hexdigest() == expected_hash)
                if not verified:
                    scores[capture['id']] = dict(status='source_mismatch', detail='Replay image identity could not be verified')
                    continue
                scores[capture['id']] = dict(row.get('routed') or {}, selected_type=row.get('selected_type'),
                                             size=row.get('size'), known_type=row.get('type'), known_type_score=row.get('oracle'),
                                             input_verified=True)
            if scores:
                results.append(dict(id=path.stem, label=report.get('label', path.stem), scores=scores,
                                    device=report.get('device'), bundle=report.get('bundle'),
                                    bundle_sha256=report.get('bundle_sha256'), runtime_sha256=report.get('runtime_sha256'),
                                    completed=report.get('completed'), crop_policy=report.get('crop_policy')))
        return results

    def item(self, run_id, item_id):
        run = self.run(run_id)
        entry = next((i for i in run['items'] if i['id'] == item_id), None)
        if entry is None:
            raise FileNotFoundError('Item not found')
        folder = self.path(run_id, directory=True)
        if item_id == '_telemetry':
            return dict(id=item_id, run=run_id, events=self.telemetry(run_id), captures=[], evaluations=[], metadata={})
        if item_id == '_run':
            directory, meta, record = folder, {}, {}
            images = self._images(folder, recursive=not any(i['id'].startswith('item_') for i in run['items']))
        else:
            directory = folder / item_id
            meta = self._read(directory / 'meta.json')
            meta = meta if isinstance(meta, dict) else {}
            record = next((r for r in reversed(self._rows(folder / 'decisions.jsonl')) if r.get('item') == entry['number']), {})
            images = self._images(directory) if directory.is_dir() else []
        top_files = [p.name for p in images if p.name.startswith('top_')]
        captures, unassigned = [], []
        explicit_top = (meta.get('anomaly', {}).get('top') or {}).get('capture_id')
        for p in images:
            if p.name.startswith(('crop_', 'model_')) and item_id != '_run':
                continue                           # these are derivatives, not additional camera exposures
            view = view_of(p.name)
            source_known = view != 'top' or len(top_files) == 1 or explicit_top == p.name
            score = dict((record.get('scores', {}).get(view) or meta.get('anomaly', {}).get(view) or {})) if source_known else {}
            trigger = source_known and record.get('decided_at_view') == view
            capture = dict(id=str(p.relative_to(folder)), filename=str(p.relative_to(directory)), view=view,
                           path=str(p.relative_to(self.root)), url=self.media_url(p), timestamp=None,
                           score=score, tape=score.get('tape'), trigger=trigger, trigger_detector=trigger_detector(record) if trigger else None,
                           bbox=meta.get('top', {}).get(p.stem, {}).get('bbox') if view == 'top' else meta.get('views', {}).get(view, {}).get('crop_box'),
                           source_note=None if source_known else 'Top-view result has no recorded source attempt; not assigned to this image')
            saved_crop = directory / f'crop_{view}.jpg'
            if saved_crop in images:
                capture['crop_url'] = self.media_url(saved_crop)
                capture['crop_label'] = 'Saved inspection crop'
            captures.append(capture)
        if len(top_files) > 1 and not explicit_top and (record.get('scores', {}).get('top') or meta.get('anomaly', {}).get('top')):
            unassigned.append('Top-view result cannot be assigned to an attempt from this legacy record')
        if record.get('decided_at_view') == 'fusion':
            unassigned.append('Decision made after combining views; no single triggering capture was recorded')
        return dict(**entry, run=run_id, captures=captures, metadata=meta, record=record,
                    note=run.get('note'), unassigned=unassigned,
                    evaluations=self.evaluations(run_id, item_id, captures) if item_id != '_run' else [])

    def reconstructed_crop(self, run_id, item_id, capture_id, evaluation_id):
        """Only verified offline results may request this explicitly labeled reconstruction."""
        item = self.item(run_id, item_id)
        capture = next((c for c in item['captures'] if c['id'] == capture_id), None)
        evaluation = next((e for e in item['evaluations'] if e['id'] == evaluation_id), None)
        if not capture or not evaluation or not evaluation['scores'].get(capture_id, {}).get('input_verified'):
            raise FileNotFoundError('No verified replay for this capture')
        if evaluation.get('crop_policy') != 'part-top-v2' or capture['view'] != 'top' or not capture.get('bbox'):
            raise FileNotFoundError('Crop reconstruction unavailable')
        runtime = Path(__file__).resolve().parents[1] / 'vh' / 'anomaly.py'
        if hashlib.sha256(runtime.read_bytes()).hexdigest() != evaluation.get('runtime_sha256'):
            raise FileNotFoundError('Replay preprocessing differs from this runtime')
        import io
        from vh.anomaly import part_crop
        image, _ = part_crop(self.path(capture['path']), capture['bbox'])
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return buffer.getvalue(), 'image/png'
