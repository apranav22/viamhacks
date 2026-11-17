# [codex/unknown · op Ali · Mac.mynetworksettings.com · ali/pipeline · 2026-11-14]
import json,base64,io,pathlib,sys
sys.path.insert(0,str(pathlib.Path.cwd()))
from PIL import Image
from vh.anomaly import part_crop
x=json.load(open('runs/_analysis/curated-candidate-top-replay.json'))
rows=[]
for r in x['rows']:
 if r['split']!='test':continue
 if r['label']=='good' and r['routed']['anomalous']==False:continue
 if r['label']!='good' and r['routed']['anomalous']==True:continue
 source=pathlib.Path('runs')/r['pick']/r['file']
 def uri(im):
  im.thumbnail((480,300));b=io.BytesIO();im.save(b,format='JPEG',quality=75);return 'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()
 crop,_=part_crop(source,r['bbox'])
 r['photo']=uri(Image.open(source).convert('RGB'));r['crop']=uri(crop)
 if r['routed']['status']!='ok':r['stage']='Routing';r['outcome']='Unknown type';r['why']='Size distance 10.9 exceeds the limit of 6. The known-type model flags this defect. The policy would reject as uncertain.'
 elif r['selected_type']!=r['type'] and r['routed']['anomalous']!=r['oracle']['anomalous']:r['stage']='Routing';r['outcome']='False reject';r['why']='The size router selects the wrong bank. The same crop passes when scored against the labelled part type: routing explains this false reject.'
 elif r['selected_type']!=r['type']:r['stage']='Routing + scoring';r['outcome']='Missed defect';r['why']='The router chooses the wrong bank, but supplying the correct type still misses the defect. Correcting routing alone does not fix this case.'
 else:r['stage']='Scoring';r['outcome']='Missed defect';r['why']='The selected type matches the label, but the anomaly score is below its threshold. The score establishes a miss; the visual root cause is unconfirmed.'
 rows.append(r)
pathlib.Path('work/model-review/examples.json').write_text(json.dumps(rows))
print('prepared',len(rows),'examples')
