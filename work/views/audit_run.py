import asyncio, sys; sys.path.insert(0, '.')
from station import connect
from station_shell import execute
PY = r'''
import json,glob,os,collections
d=sorted(glob.glob("/opt/viam/sorter-ali/runs/*_collect"))[-1]; print(d)
V=["top_1","oblique+45","oblique-45","under","end_a","end_b"]
miss=collections.Counter(); n=0
for f in sorted(glob.glob(d+"/item_*/meta.json")):
    m=json.load(open(f)); n+=1; sh=m.get("sharpness",{})
    got=[v for v in V if v in sh]
    for v in V:
        if v not in sh: miss[v]+=1
    print(os.path.basename(os.path.dirname(f)), "skipped",m.get("skipped"), " ".join(f"{v}:{sh.get(v)}" for v in got))
print("items",n,"missing",dict(miss))
sp=collections.Counter()
ev=d+"/dash/events.jsonl"
if os.path.exists(ev):
    for l in open(ev):
        e=json.loads(l)
        if e.get("k")=="move": sp[e.get("joint_speed")]+=1
print("joint_speed counts", dict(sp))
for l in open(d+"/decisions.jsonl"):
    e=json.loads(l); print("POS", e["item"], e.get("pick_xy"), e.get("yaw"))
'''
async def m():
    async with await connect() as r:
        import base64; b=base64.b64encode(PY.encode()).decode()
        print((await execute(r, f"echo {b} | base64 -d > /tmp/audit_run.py && /opt/viam/sorter-ali/.venv/bin/python3.12 /tmp/audit_run.py", 60))[1])
asyncio.run(m())
