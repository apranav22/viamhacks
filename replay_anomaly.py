"""Replay REAL OpenVINO scores/heatmaps from a saved dataset into the dashboard. NEVER connects to the robot.

python replay_anomaly.py --bundle models/button_white_v1/bundle.json --dataset models/button_white_v1/dataset/dataset.json

All views are scored in replay, including after a defect, so inspection can diagnose false positives.
This is not a measurement of camera latency or arm response time.
"""
import argparse
import base64
import hashlib
import json
import math
import time
from collections import defaultdict
from pathlib import Path

from vh.anomaly import AnomalyModels, Score, context_crop, reject_reason
from vh.telemetry import Telemetry


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--split',choices=['test','calibration','train'],default='test')
    p.add_argument('--device',choices=['CPU','GPU','NPU'],default='CPU')
    p.add_argument('--dash-host',default='127.0.0.1')
    p.add_argument('--pace',type=float,default=0.3)
    p.add_argument('--score-report',type=Path,help='Display verified remote benchmark scores; no local inference is run')
    p.add_argument('--report-device',choices=['CPU','GPU','NPU'],default='GPU')
    a=p.parse_args()
    data=json.loads(a.dataset.read_text())
    by_pick=defaultdict(list)
    selected=[s for s in data['samples'] if s['split']==a.split]
    remote=None;remote_rows={};models=None
    if a.score_report:
        remote=json.loads(a.score_report.read_text())
        if remote['dataset_sha256']!=hashlib.sha256(a.dataset.read_bytes()).hexdigest() or remote['bundle_sha256']!=hashlib.sha256(a.bundle.read_bytes()).hexdigest():
            raise ValueError('Remote score report does not match this dataset/model bundle')
        device_report=remote['devices'][a.report_device]
        if device_report['status']!='ok':raise ValueError('Requested remote device did not pass inference checks')
        remote_rows={(r['pick_id'],r['group']):r for r in device_report['samples']}
    else:
        models=AnomalyModels(a.bundle,a.device)
        for part_type,background in {(s['part_type'],s['background']) for s in selected}:
            models.warm(part_type,background)
    for sample in selected:
        by_pick[sample['pick_id']].append(sample)
    tel=Telemetry(host=a.dash_host,run_id='anomaly_replay_'+time.strftime('%Y%m%d_%H%M%S'))
    origin=f"{remote['host']} {a.report_device}" if remote else f'local {a.device}'
    tel.emit('run',cmd=f'OFFLINE saved-frame replay · inference {origin} ({a.split}; NO ROBOT MOTION)',live=False,release='replay',
             states=['REPLAY','INSPECT','DECIDE'],views=['front','yaw-20','yaw+35','pitch-25'])
    reports=[]
    for n,(pick,samples) in enumerate(sorted(by_pick.items()),1):
        order=['front','yaw-20','yaw+35','pitch-25'] if samples[0]['pose']=='lying' else ['end','side0','side+120','side-120']
        ranked={k:i for i,k in enumerate(['top',*order])}
        samples.sort(key=lambda s:ranked.get(s['view'],99))
        tel.state('PICK',item=n)  # clears the prior item's UI tiles; NO motion event or robot call
        tel.state('INSPECT',item=n,pose=samples[0]['pose'],views=order)
        scores={};start=time.time()
        for s in samples:
            image=Path(s['source_image']);jpg=image.read_bytes()
            crop,box=context_crop(jpg,s['bbox'])
            if remote:
                r=remote_rows[(s['pick_id'],s['group'])]
                if r['status']!='ok' or not math.isfinite(r['score']) or not math.isfinite(r['threshold']) or r['threshold']<=0:
                    raise ValueError('Invalid remote score/threshold')
                result=Score('ok',r['score'],r['threshold'],r['infer_ms'])
                heatmap=base64.b64decode(r['heatmap_base64'],validate=True)
                if len(heatmap)!=4096:raise ValueError('Invalid remote heatmap size')
            else:
                result=models.score(crop,s['part_type'],s['pose'],s['view'],s['background'])
                heatmap=result.heatmap_bytes()
            scores[s['view']]=result.fields()
            if s['view']=='top':
                meta_path=image.parent/'meta.json'
                top=json.loads(meta_path.read_text()).get('top',{}).get(image.stem,{})
                x,y=top.get('xy') or [None,None];yaw=top.get('yaw_world',0)
                x0,y0,x1,y1=s['bbox'];cx,cy=(x0+x1)/2,(y0+y1)/2
                tel.emit('look',frame=jpg,n=n,label='saved hover image · offline replay',shape=s['part_type'],tape=None,
                         item={'bbox':s['bbox'],'c':[cx,cy],'axis':[cx,y0,cx,y1]},m={'x':x,'y':y,'yaw_long':yaw,'height':None})
            else:
                tel.emit('view',frame=jpg,n=n,view=s['view'],crop=box,tape=None,anomaly=result.score,frame_ms=0,jaw=None)
            tel.emit('anomaly_result',frame=heatmap,mime='application/x-anomaly-map;h=64;w=64',n=n,
                     view=s['view'],model_crop=box,background=s['background'],**result.fields())
            tel.emit('span',name=f'infer {s["view"]}',t0=time.time()-result.ms/1000,ms=result.ms,phase='view',item=n)
            time.sleep(a.pace)
        reason=reject_reason(scores,['top',*order]);decision='reject' if reason else 'good'
        tel.state('DECIDE',item=n)
        tel.emit('decision',n=n,decision=decision,reason=reason or 'all required anomaly views below threshold',at='fusion',
                 scores=scores,ms_from_seen=round((time.time()-start)*1000))
        tel.emit('cycle',item=n,result=decision,decision=f'{decision}: {reason or "all required views passed"}',
                 latency_ms=None,recoveries=0,t_first_motion='',shape=samples[0]['part_type'],scores=scores)
        reports.append({'pick_id':pick,'label':samples[0]['label'],'decision':decision,'reason':reason,'scores':scores})
        print(pick,decision,reason or 'all views passed',flush=True)
    tel.state('IDLE');print('telemetry',tel.report())
    suffix=f"_{remote['host']}_{a.report_device}" if remote else ''
    report_path=a.bundle.parent/f'replay_{a.split}{suffix}.json'
    report_path.write_text(json.dumps(reports,indent=2))
    print('REPORT',report_path)


if __name__=='__main__':
    main()
