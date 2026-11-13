"""Benchmark exported anomaly bundles on explicit OpenVINO devices. Saved images only; NO robot connection.

python benchmark_anomaly.py --bundle models/button_white_v1/bundle.json \
 --dataset models/button_white_v1/dataset/dataset.json --devices CPU GPU --out device_report.json

Reports actual execution devices, scores/threshold decisions, finite map checks and timing distributions.
Never falls back to another device when compilation/scoring fails.
"""
import argparse
import base64
import hashlib
import json
import platform
from pathlib import Path

import numpy as np

from vh.anomaly import AnomalyModels, context_crop


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--devices',nargs='+',choices=['CPU','GPU','NPU'],default=['CPU','GPU'])
    p.add_argument('--repeat',type=int,default=10)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.repeat<1:p.error('--repeat must be positive')
    dataset=json.loads(a.dataset.read_text())
    samples=[s for s in dataset['samples'] if s['split']=='test']
    if not samples:raise SystemExit('No held-out test samples')
    report={'host':platform.node(),'dataset_sha256':hashlib.sha256(a.dataset.read_bytes()).hexdigest(),
            'bundle_sha256':hashlib.sha256(a.bundle.read_bytes()).hexdigest(),'repeat':a.repeat,'devices':{}}
    for device in a.devices:
        print('DEVICE',device,flush=True)
        record={'status':'error','requested_device':device,'samples':[],'execution':{}}
        report['devices'][device]=record
        try:
            m=AnomalyModels(a.bundle,device)
            for typ,bg in {(s['part_type'],s['background']) for s in samples}:m.warm(typ,bg)
            record['openvino_version']=str(m.core.get_versions(device))
            record['full_device_name']=m.core.get_property(device,'FULL_DEVICE_NAME')
            for key,(_,compiled,_,shape,_) in m.models.items():
                record['execution'][key]={'devices':list(compiled.get_property('EXECUTION_DEVICES')),
                    'input_shape':list(shape),'precision_hint':str(compiled.get_property('INFERENCE_PRECISION_HINT'))}
            timings=[]
            for s in samples:
                image,crop=context_crop(s['source_image'],s['bbox'])
                for _ in range(a.repeat):
                    result=m.score(image,s['part_type'],s['pose'],s['view'],s['background'])
                    if result.status!='ok':raise RuntimeError(result.detail or result.status)
                    timings.append(result.ms)
                record['samples'].append({'pick_id':s['pick_id'],'group':s['group'],'view':s['view'],'label':s['label'],
                    'model_crop':crop,**result.fields(),'heatmap_base64':base64.b64encode(result.heatmap_bytes()).decode()})
            record.update(status='ok',mean_ms=float(np.mean(timings)),p50_ms=float(np.percentile(timings,50)),
                          p90_ms=float(np.percentile(timings,90)),p99_ms=float(np.percentile(timings,99)))
            print(device,record['full_device_name'],'p50_ms',round(record['p50_ms'],2),'p90_ms',round(record['p90_ms'],2),flush=True)
        except Exception as e:
            record['error']=f'{type(e).__name__}: {e}'
            print(device,'FAILED',record['error'][:400],flush=True)
        a.out.write_text(json.dumps(report,indent=2))
    if not any(d['status']=='ok' for d in report['devices'].values()):raise SystemExit('No successful device benchmark')
    if 'CPU' in report['devices'] and report['devices']['CPU']['status']=='ok':
        ref={(s['pick_id'],s['view']):s for s in report['devices']['CPU']['samples']}
        for device,d in report['devices'].items():
            if device=='CPU' or d['status']!='ok':continue
            diffs=[abs(s['score']-ref[(s['pick_id'],s['view'])]['score']) for s in d['samples']]
            d['vs_cpu']={'max_score_difference':max(diffs),'decision_agreement':sum(
                s['anomalous']==ref[(s['pick_id'],s['view'])]['anomalous'] for s in d['samples'])/len(d['samples'])}
    a.out.write_text(json.dumps(report,indent=2))
    print('REPORT',a.out,flush=True)


if __name__=='__main__':main()
