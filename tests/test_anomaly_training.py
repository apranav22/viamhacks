"""Optional REAL trainer/export smoke test (CPU, pretrained weights required).

RUN_ANOMALY_TRAINING_TESTS=1 python -m unittest discover -s tests -p test_anomaly_training.py -v

Opt-in because Anomalib/torch are training-only dependencies and pretrained weights may need downloading.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image,ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))


@unittest.skipUnless(os.environ.get('RUN_ANOMALY_TRAINING_TESTS')=='1','training integration test is opt-in')
class TrainingTests(unittest.TestCase):
    def test_fit_calibrate_export_and_infer(self):
        from train_anomaly import fit_group
        from vh.anomaly import AnomalyModels,CROP_POLICY,group_key
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);samples=[]
            for n in range(6):
                im=Image.new('RGB',(64,64),(180,180,180));d=ImageDraw.Draw(im)
                d.rectangle((28+n%2,12,35+n%2,52),fill=(90,90,90));im.save(root/f'{n}.png')
                samples.append({'image':f'{n}.png','pick_id':f'pick{n}','label':'good',
                    'split':'train' if n<3 else 'calibration' if n<5 else 'test',
                    'part_type':'test_part','pose':'lying','view':'top','background':'white'})
            entry=fit_group(samples,root,root/'model',SimpleNamespace(size=64,coreset_ratio=0.1,margin=1.1,train_device='cpu'))
            self.assertGreater(entry['threshold'],0)
            self.assertEqual(entry['fit_execution']['feature_device'],'cpu')
            self.assertEqual(len(entry['test_results']),1)
            entry['xml']='model/model.xml'
            bundle=root/'bundle.json';bundle.write_text(json.dumps({'schema':1,'crop_policy':CROP_POLICY,
                'models':{group_key('test_part','lying','top','white'):entry}}))
            runtime=AnomalyModels(bundle,'CPU');runtime.warm('test_part','white')
            self.assertEqual(runtime.score(root/'5.png','test_part','lying','top','white').status,'ok')


if __name__=='__main__':unittest.main()
