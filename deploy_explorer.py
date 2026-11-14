"""Deploy the read-only explorer beside the existing station services, without robot motion.

python deploy_explorer.py --connection-script ../viam-analytics/viam_connect.py
Uses the existing authenticated Viam shell. Never copies credentials. Port 8771.
"""
import argparse
import asyncio
import importlib.util
import json
import shlex
import sys
import time
from pathlib import Path


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-script', type=Path)
    args = parser.parse_args()
    if args.connection_script:
        spec = importlib.util.spec_from_file_location('_authorized_station', args.connection_script.resolve())
        connection = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(connection)
    else:
        import station as connection
    # station_shell only needs connect for its CLI; reuse the existing connection module.
    sys.modules['station'] = connection
    from station_shell import execute, upload
    root = Path(__file__).resolve().parent
    target = '/opt/viam/sorter-vedant-explorer/' + time.strftime('%Y%m%d_%H%M%S')
    async with await connection.connect() as machine:
        rc, output = await execute(machine, "python3 -c " + shlex.quote(
            "import socket;s=socket.socket();s.bind(('0.0.0.0',8771));s.close();print('port free')"))
        if rc:
            raise RuntimeError('Port 8771 is already occupied; existing service left untouched.')
        rc, output = await execute(machine, 'mkdir -p ' + shlex.quote(target))
        if rc:
            raise RuntimeError(output)
        for name in ('train_dashboard.py', 'data_explorer.py', 'data_explorer.html'):
            await upload(machine, root / name, target + '/' + name)
            print('Verified upload:', name)
        setup = '''from pathlib import Path
import subprocess,json,time,urllib.request
target=Path(TARGET)
for name in ('runs','models'):
 source=Path('/opt/viam/sorter-ali')/name
 if not source.is_dir(): raise RuntimeError('Shared '+name+' directory unavailable')
 (target/name).symlink_to(source)
for name in ('train_dashboard.py','data_explorer.py'):
 compile((target/name).read_text(),name,'exec')
with (target/'server.log').open('ab') as log:
 process=subprocess.Popen(['/opt/viam/sorter-ali/.venv/bin/python3.12','-u',str(target/'train_dashboard.py'),'--host','0.0.0.0','--port','8771'],cwd=target,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
(target/'server.pid').write_text(str(process.pid))
for attempt in range(20):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8771/api/explore',timeout=2) as response: state=json.load(response)
  print(json.dumps({'host':state['host'],'images':len(state['records']),'activity':state['activity'],'url':'http://172.16.0.182:8771/explore','pid':process.pid}));break
 except OSError: time.sleep(.5)
else: raise RuntimeError('Explorer did not become healthy; inspect '+str(target/'server.log')+' before retrying')
'''.replace('TARGET', repr(target))
        rc, output = await execute(machine, 'python3 -c ' + shlex.quote(setup), timeout=30)
        print(output)
        if rc:
            raise RuntimeError('Deployment outcome above; do not retry blindly.')


if __name__ == '__main__':
    asyncio.run(main())
