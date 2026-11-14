"""Contact sheet of every capture crop for the latest station collect run -> scratch jpg."""
import asyncio, sys, base64; sys.path.insert(0, '.')
from station import connect
from station_shell import execute
OUT = sys.argv[1]; ITEMS = sys.argv[2] if len(sys.argv) > 2 else ""; KIND = sys.argv[3] if len(sys.argv) > 3 else "collect"
PY = r'''
import glob,os,sys,io,base64
from PIL import Image, ImageDraw
d=sorted(glob.glob("/opt/viam/sorter-ali/runs/*_" + (sys.argv[2] if len(sys.argv)>2 else "collect")))[-1]
items=sorted(glob.glob(d+"/item_*"))
want=sys.argv[1].split(",") if len(sys.argv)>1 and sys.argv[1] else None
items=[i for i in items if not want or os.path.basename(i)[-3:] in want][-6:]
V=["top_1","crop_oblique+45","crop_oblique-45","crop_under","crop_end_a","crop_end_b"]
W,H=300,220; sheet=Image.new("RGB",(W*len(V),H*len(items)),(40,40,40)); dr=ImageDraw.Draw(sheet)
for r,it in enumerate(items):
    for c,v in enumerate(V):
        f=f"{it}/{v}.jpg"
        if os.path.exists(f):
            im=Image.open(f).convert("RGB"); im.thumbnail((W-4,H-4)); sheet.paste(im,(c*W+2,r*H+2))
        dr.text((c*W+4,r*H+4),f"{os.path.basename(it)[-3:]} {v.replace('crop_','')}",fill=(255,255,0))
b=io.BytesIO(); sheet.save(b,"JPEG",quality=70); print("B64:"+base64.b64encode(b.getvalue()).decode())
'''
async def m():
    async with await connect() as r:
        b = base64.b64encode(PY.encode()).decode()
        out = (await execute(r, f"echo {b} | base64 -d > /tmp/sheet_run.py && /opt/viam/sorter-ali/.venv/bin/python3.12 /tmp/sheet_run.py '{ITEMS}' {KIND}", 90))[1]
        open(OUT, "wb").write(base64.b64decode(out.split("B64:")[1].strip()))
        print("wrote", OUT)
asyncio.run(m())
