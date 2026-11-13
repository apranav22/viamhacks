"""Fit frozen-feature PatchCore banks on explicitly curated normal picks; export full inference to OpenVINO.

python train_anomaly.py --runs runs/<clean-run> --type button_ss_long --background white --out models/screw-v1

No robot connection, motion, cloud training or data upload. Each group is (type, held pose, view, background).
Only train/good builds the bank; only disjoint calibration/good sets its threshold. Test picks never tune it.
Threshold = max calibration good score * margin: an explicitly provisional small-data rule, NOT a measured FPR.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from vh.anomaly import CROP_POLICY
from vh.anomaly_data import build_dataset, groups


def tensor(image, size):
    image = Image.open(image).convert('RGB').resize((size, size), Image.Resampling.BILINEAR)
    return np.ascontiguousarray(np.asarray(image, dtype=np.float32).transpose(2, 0, 1)[None] / 255)


def fit_group(samples, dataset_dir, out_dir, args):
    import torch
    import openvino as ov
    from anomalib.models.image.patchcore.torch_model import PatchcoreModel

    train = [s for s in samples if s['split'] == 'train' and s['label'] == 'good']
    cal = [s for s in samples if s['split'] == 'calibration' and s['label'] == 'good']
    test = [s for s in samples if s['split'] == 'test']
    if len(train) < 3 or not cal or not test:
        raise ValueError(f'Need >=3 train, >=1 calibration and >=1 test images; got {len(train)}, {len(cal)}, {len(test)}')
    torch.manual_seed(17)
    np.random.seed(17)
    torch.set_num_threads(2)
    model = PatchcoreModel(layers=['layer2', 'layer3'], backbone='resnet18', pre_trained=True, num_neighbors=1)
    for p in model.parameters():
        p.requires_grad_(False)
    mean = torch.tensor([0.485, 0.456, 0.406]).reshape(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225]).reshape(1, 3, 1, 1)
    model.train()
    model.feature_extractor.eval()  # frozen BatchNorm too: no updates on our tiny dataset
    with torch.no_grad():
        for sample in train:
            x = torch.from_numpy(tensor(dataset_dir / sample['image'], args.size))
            model((x - mean) / std)
    model.subsample_embedding(sampling_ratio=args.coreset_ratio)
    model.eval()

    class Export(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.patchcore = model
            self.register_buffer('mean', mean)
            self.register_buffer('std', std)

        def forward(self, image):
            result = self.patchcore((image - self.mean) / self.std)
            return result.pred_score, result.anomaly_map

    wrapper = Export().eval()
    dummy = torch.zeros(1, 3, args.size, args.size)
    converted = ov.convert_model(wrapper, example_input=dummy)
    converted.reshape({converted.input(0): [1, 3, args.size, args.size]})
    converted.outputs[0].get_tensor().set_names({'pred_score'})
    converted.outputs[1].get_tensor().set_names({'anomaly_map'})
    out_dir.mkdir(parents=True)
    ov.save_model(converted, out_dir / 'model.xml', compress_to_fp16=False)
    compiled = ov.Core().compile_model(converted, 'CPU', {'INFERENCE_PRECISION_HINT': 'f32', 'PERFORMANCE_HINT': 'LATENCY'})
    request = compiled.create_infer_request()
    score_output = next(o for o in compiled.outputs if 'pred_score' in o.get_names())
    for _ in range(2):
        request.infer({0: np.zeros((1, 3, args.size, args.size), np.float32)})

    def score(sample):
        x = tensor(dataset_dir / sample['image'], args.size)
        start = time.perf_counter()
        request.infer({0: x})
        value = float(request.get_tensor(score_output).data.reshape(-1)[0])
        if not np.isfinite(value):
            raise ValueError('Export produced nonfinite score')
        return value, (time.perf_counter() - start) * 1000, x

    cal_scores = [score(s)[0] for s in cal]
    threshold = max(max(cal_scores) * args.margin, 1e-6)
    results = []
    max_difference = 0.0
    for sample in test:
        value, ms, x = score(sample)
        with torch.no_grad():
            reference = float(wrapper(torch.from_numpy(x))[0].reshape(-1)[0])
        difference = abs(value - reference)
        max_difference = max(difference, max_difference)
        if difference > max(0.01, 0.01 * abs(reference)):
            raise ValueError(f'OpenVINO/Torch score mismatch: {value} vs {reference}')
        results.append({'pick_id': sample['pick_id'], 'label': sample['label'], 'score': value,
                        'anomalous': value >= threshold, 'infer_ms': round(ms, 2), 'torch_score': reference})
    first = samples[0]
    entry = {k: first[k] for k in ('part_type', 'pose', 'view', 'background')}
    entry.update(threshold=threshold, image_size=[args.size, args.size],
                 train_pick_ids=sorted({s['pick_id'] for s in train}),
                 calibration_pick_ids=sorted({s['pick_id'] for s in cal}),
                 test_pick_ids=sorted({s['pick_id'] for s in test}),
                 calibration='prototype-good-max-margin', margin=args.margin,
                 bank_size=int(model.memory_bank.shape[0]), backbone='resnet18', num_neighbors=1,
                 max_torch_openvino_score_difference=max_difference, test_results=results)
    return entry


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--runs', nargs='+', required=True, type=Path)
    p.add_argument('--type', required=True)
    p.add_argument('--background', required=True, choices=['white', 'cardboard'])
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--size', default=256, type=int)
    p.add_argument('--coreset-ratio', default=0.01, type=float)
    p.add_argument('--margin', default=1.10, type=float)
    a = p.parse_args()
    if a.out.exists():
        p.error('Choose a new output folder; existing bundles are never overwritten')
    if not 0 < a.coreset_ratio <= 1 or a.margin < 1 or a.size < 64:
        p.error('Invalid coreset ratio, calibration margin or image size')
    a.out.mkdir(parents=True)
    dataset = build_dataset(a.runs, a.out / 'dataset', a.type, a.background)
    bundle = {'schema': 1, 'crop_policy': CROP_POLICY, 'models': {}, 'skipped': [],
              'limitations': dataset['limitations'] + ['Prototype threshold; physical item and defect holdouts still required.']}
    for n, (key, samples) in enumerate(sorted(groups(dataset).items())):
        print(f'FIT {key} ({len(samples)} samples)', flush=True)
        model_dir = a.out / f'model_{n:02d}'
        try:
            entry = fit_group(samples, a.out / 'dataset', model_dir, a)
        except ValueError as e:
            bundle['skipped'].append({'group': key, 'reason': str(e)})
            print(f'SKIP {key}: {e}', flush=True)
            continue
        entry['xml'] = f'model_{n:02d}/model.xml'
        bundle['models'][key] = entry
        (a.out / 'bundle.json').write_text(json.dumps(bundle, indent=2))
        print(f'EXPORTED {key}: bank={entry["bank_size"]} threshold={entry["threshold"]:.4f}', flush=True)
    if not bundle['models']:
        raise SystemExit('No models exported; inspect dataset.json and skipped groups')
    (a.out / 'bundle.json').write_text(json.dumps(bundle, indent=2))
    print('BUNDLE', a.out / 'bundle.json', flush=True)


if __name__ == '__main__':
    main()
