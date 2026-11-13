"""Offline tests only: python -m unittest discover -s tests -p 'test_anomaly.py'"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vh.anomaly import AnomalyModels, CROP_POLICY, Score, context_crop, group_key, reject_reason
from vh.anomaly_data import build_dataset, split_picks


class AnomalyTests(unittest.TestCase):
    def test_context_preserves_part_and_shifts_inside_frame(self):
        im = Image.new('RGB', (1920, 1080), 'white')
        crop, box = context_crop(im, [560, 430, 1080, 1080])
        self.assertEqual(crop.width, crop.height)
        self.assertLessEqual(box[0], 560)
        self.assertLessEqual(box[1], 430)
        self.assertGreaterEqual(box[2], 1080)
        self.assertEqual(box[3], 1080)
        with self.assertRaises(ValueError):
            context_crop(im, [50, 20, 2000, 80])

    def test_split_is_stable_and_by_pick(self):
        picks = [f'run/item_{n}' for n in range(9)]
        split = split_picks(picks)
        self.assertEqual(split, split_picks(picks[::-1] + picks))
        self.assertEqual(set(split.values()), {'train', 'calibration', 'test'})
        with self.assertRaises(ValueError):
            split_picks(picks[:4])

    def test_dataset_uses_only_completed_curated_picks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run = root / 'clean_run';run.mkdir()
            rows = []
            for n in range(9):
                d = run / f'item_{n:03d}';d.mkdir()
                for name in ('top_1.jpg', 'web_front.jpg'):
                    im = Image.new('RGB', (100, 100), 'white')
                    ImageDraw.Draw(im).rectangle((30, 20, 45, 65), fill='gray')
                    im.save(d / name)
                (d / 'meta.json').write_text(json.dumps({'pose': 'lying', 'top': {'top_1': {'bbox': [30,20,45,65]}},
                    'views': {'front': {'crop_box': [20,10,70,80]}}}))
                rows.append({'item': n, 'decision': 'collect' if n != 8 else 'none', 'type': 'screw',
                             'label': 'good' if n < 7 else 'tape', 'pose': 'lying'})
            (run / 'decisions.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
            dataset = build_dataset([run], root/'dataset', 'screw', 'white')
            samples = dataset['samples']
            self.assertEqual(len(samples),16)
            split_by_pick = {}
            for s in samples:
                split_by_pick.setdefault(s['pick_id'],set()).add(s['split'])
                if s['label'] != 'good':
                    self.assertEqual(s['split'],'test')
            self.assertTrue(all(len(s)==1 for s in split_by_pick.values()))
            self.assertFalse(any(s['pick_id'].endswith('item_008') for s in samples))
            with self.assertRaises(FileExistsError):
                build_dataset([run], root/'dataset','screw','white')

    def test_missing_or_failed_view_never_passes(self):
        ok = Score('ok',0.2,0.5).fields()
        bad = Score('ok',0.6,0.5).fields()
        self.assertIsNone(reject_reason({'top':ok,'front':ok},['top','front']))
        self.assertIn('unavailable',reject_reason({'top':ok},['top','front']))
        self.assertIn('unavailable',reject_reason({'top':Score('error').fields()},['top']))
        self.assertIn('anomaly',reject_reason({'top':bad},['top']))
        self.assertIn('anomaly',reject_reason({'top':Score('ok',0.5,0.5).fields()},['top']))

    def test_heatmap_has_fixed_threshold_scale(self):
        a=np.array([[0,0.5,1.0]],dtype=np.float32)
        raw=Score('ok',1.0,0.5,anomaly_map=a).heatmap_bytes()
        m=np.frombuffer(raw,np.uint8).reshape(64,64)
        self.assertEqual(len(raw),4096)
        self.assertEqual(m[0,0],0)
        self.assertEqual(m[0,-1],255)
        self.assertLessEqual(abs(int(m[32,32])-128),4)
        self.assertIsNone(Score('missing').heatmap_bytes())

    def make_ir(self, folder, nan=False):
        import openvino as ov
        from openvino import opset13 as op
        p=op.parameter([1,3,32,32],np.float32,name='image')
        m=op.reduce_mean(p,op.constant([1],np.int64),True)
        if nan:
            m=op.multiply(m,op.constant(np.float32(np.nan)))
        score=op.reduce_max(m,op.constant([1,2,3],np.int64),False)
        model=ov.Model([score,m],[p])
        model.outputs[0].get_tensor().set_names({'pred_score'})
        model.outputs[1].get_tensor().set_names({'001_numeric_alias', 'anomaly_map'})
        ov.save_model(model,folder/'model.xml',compress_to_fp16=False)
        entry={'part_type':'screw','pose':'lying','view':'top','background':'white','xml':'model.xml','threshold':0.5}
        (folder/'bundle.json').write_text(json.dumps({'schema':1,'crop_policy':CROP_POLICY,
            'models':{group_key('screw','lying','top','white'):entry}}))
        return folder/'bundle.json'

    def test_openvino_rgb_contract_and_model_selection(self):
        with tempfile.TemporaryDirectory() as td:
            bundle=self.make_ir(Path(td))
            m=AnomalyModels(bundle,'CPU');self.assertEqual(len(m.warm('screw','white')),1)
            s=m.score(Image.new('RGB',(50,80),'white'),'screw','lying','top','white')
            self.assertEqual(s.status,'ok');self.assertAlmostEqual(s.score,1.0,places=5)
            self.assertEqual(s.anomaly_map.shape,(32,32));self.assertTrue(s.fields()['anomalous'])
            self.assertFalse(m.score(Image.new('RGB',(32,32),'black'),'screw','lying','top','white').fields()['anomalous'])
            self.assertEqual(m.score(Image.new('RGB',(32,32)),'screw','upright','top','white').status,'missing')
            self.assertEqual(m.score(Image.new('RGB',(32,32)),'screw','lying','top','cardboard').status,'missing')
            with self.assertRaises(ValueError): AnomalyModels(bundle,'AUTO')

    def test_dynamic_export_is_pinned_to_declared_input_size(self):
        import openvino as ov
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);bundle=self.make_ir(folder)
            model=ov.Core().read_model(folder/'model.xml')
            model.reshape({model.input(0):[-1,3,-1,-1]})
            ov.save_model(model,folder/'dynamic.xml',compress_to_fp16=False)
            data=json.loads(bundle.read_text())
            entry=next(iter(data['models'].values()))
            entry.update(xml='dynamic.xml',image_size=[32,32])
            bundle.write_text(json.dumps(data))
            m=AnomalyModels(bundle,'CPU');m.warm('screw','white')
            self.assertEqual(m.score(Image.new('RGB',(40,40),'white'),'screw','lying','top','white').status,'ok')

    def test_nonfinite_outputs_do_not_pass(self):
        with tempfile.TemporaryDirectory() as td:
            m=AnomalyModels(self.make_ir(Path(td),nan=True),'CPU');m.warm('screw','white')
            self.assertEqual(m.score(Image.new('RGB',(32,32),'white'),'screw','lying','top','white').status,'invalid')

    def test_sort_inspection_rejects_without_model_and_never_releases_without_checkpoint(self):
        import asyncio
        import io
        from types import SimpleNamespace
        import sort as loop
        from vh.telemetry import Telemetry
        with tempfile.TemporaryDirectory() as td:
            s=loop.Sorter.__new__(loop.Sorter)
            s.args=SimpleNamespace(mode='sort',type='screw',background='white',label='good')
            s.upright=0;s.pose='lying';s.n=1;s.top_tape=0;s.anomaly=None;s.meta={};s.idir=Path(td)
            s.tel=Telemetry(enabled=False);s.state=lambda *a,**kw: None
            b=io.BytesIO();Image.new('RGB',(1920,1080),'white').save(b,format='JPEG');jpg=b.getvalue()
            s.top_image=jpg;s.top_bbox=[100,100,200,200]
            async def web(): return jpg
            async def jaw(): return 100
            async def move(*a,**kw): pass
            s.web_jpeg=web;s.jmove=move;s.mv=SimpleNamespace(finger_pos=jaw)
            decision,reason,_,_=asyncio.run(s.inspect())
            self.assertEqual(decision,'reject');self.assertIn('unavailable',reason)
            async def blocked(*a,**kw): raise RuntimeError('blocked path')
            s.jmove=blocked
            with self.assertRaisesRegex(RuntimeError,'No inspection checkpoint reached'):
                asyncio.run(s.inspect())

    def test_preview_uses_pipeline_detector_not_cardboard_as_hand(self):
        import io
        from vh.live_detect import wrist
        im=Image.new('RGB',(640,480),(180,180,180));d=ImageDraw.Draw(im)
        d.rectangle((50,0,570,365),fill=(95,65,35))
        d.ellipse((300,190,326,216),fill=(220,220,220));d.ellipse((307,197,319,209),fill=(30,30,30))
        b=io.BytesIO();im.save(b,format='JPEG')
        result=wrist(b.getvalue())
        self.assertEqual(result['detector'],'screws.detect')
        self.assertIsNone(result['hand'])
        self.assertEqual(result['hand_status'],'not_evaluated')
        self.assertTrue(any(295<i['c'][0]<330 and 185<i['c'][1]<220 for i in result['items']))


if __name__=='__main__':
    unittest.main()
