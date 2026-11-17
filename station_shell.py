"""Deployment-only Viam shell/file transfer adapter. Does NOT command robot components.

The installed viam-sdk 0.85.2 exposes shell protobufs but no high-level shell client.
Use only the existing ViamShellDanger service; credentials stay in the normal ignored key file.

python station_shell.py exec 'python3 --version'
python station_shell.py upload small-file /opt/viam/sorter-ali/small-file

Keep uploads <=2 MiB; split larger archives into verified chunks before assembling remotely.

Remote commands are NOT automatically retried: a transport failure may leave a command committed.
"""
import argparse
import asyncio
import hashlib
import json
import re
import shlex
import sys
import uuid
from pathlib import Path

from station import connect
from viam.gen.service.shell.v1.shell_grpc import ShellServiceStub
from viam.proto.service.shell import (CopyFilesToMachineRequest, CopyFilesToMachineRequestMetadata,
                                     FileData, ShellRequest)


async def execute(machine, command, timeout=60):
    marker = 'SORTER_' + uuid.uuid4().hex
    begin, end = marker + '_BEGIN', marker + '_END'
    wrapped = f"printf '\\n{begin}\\n'; ( {command} ); rc=$?; printf '\\n{end}:%s\\n' \"$rc\"; exit\n"
    stub = ShellServiceStub(machine._channel)  # verified SDK channel ownership: RobotClient._with_channel
    data = ''
    async with stub.Shell.open(timeout=timeout) as stream:
        await stream.send_message(ShellRequest(name='ViamShellDanger', data_in=wrapped))
        await stream.end()
        async for response in stream:
            data += response.data_out + response.data_err
            if response.eof:
                break
    clean = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', data).replace('\r', '')
    match = re.search(rf'(?m)^{re.escape(begin)}\n(.*?)^{re.escape(end)}:(\d+)\s*$', clean, re.DOTALL)
    if not match:
        raise RuntimeError('No complete command markers: remote outcome UNKNOWN; not retrying or dumping raw shell output')
    return int(match.group(2)), match.group(1).rstrip()


async def upload(machine, source, destination):
    """Upload exactly one file; await explicit last-file acknowledgment. No shell/base64 payloads."""
    source = Path(source)
    if source.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Upload capped at 2 MiB for the shared WebRTC transport; split into verified chunks')
    stub = ShellServiceStub(machine._channel)
    async with stub.CopyFilesToMachine.open(timeout=300) as stream:
        await stream.send_message(CopyFilesToMachineRequest(metadata=CopyFilesToMachineRequestMetadata(
            name='ViamShellDanger', source_type=1, destination=destination, preserve=True)))
        size = source.stat().st_size
        digest = hashlib.sha256()
        with source.open('rb') as f:
            first = True
            while chunk := f.read(16 * 1024):
                digest.update(chunk)
                # Only the first data message names the file. EOF is a separate EMPTY message:
                # the RDK reader closes on EOF before consuming that message's Data field.
                fields = {'name': source.name, 'size': size, 'mode': 0o600} if first else {}
                await stream.send_message(CopyFilesToMachineRequest(file_data=FileData(data=chunk, **fields)))
                await asyncio.sleep(0.002)  # bounded pressure on the shared WebRTC transport/heartbeat
                first = False
            if first:
                await stream.send_message(CopyFilesToMachineRequest(file_data=FileData(name=source.name,size=0,mode=0o600)))
            await stream.send_message(CopyFilesToMachineRequest(file_data=FileData(eof=True)))
        await stream.end()
        acknowledged = False
        async for response in stream:
            acknowledged = acknowledged or response.ack_last_file
        if not acknowledged:
            raise RuntimeError('Upload not acknowledged; remote file status unknown')
    verify = ('from pathlib import Path;import hashlib,json;'
              f'p=Path({destination!r});print(json.dumps({{"size":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}}))')
    rc, result = await execute(machine, 'python3 -c ' + shlex.quote(verify))
    if rc or json.loads(result) != {'size': size, 'sha256': digest.hexdigest()}:
        raise RuntimeError('Upload size/hash verification failed; do not use this remote file')


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('exec'); run.add_argument('command'); run.add_argument('--timeout', type=float, default=60)
    cp = sub.add_parser('upload'); cp.add_argument('source', type=Path); cp.add_argument('destination')
    args = parser.parse_args()
    async with await connect() as machine:
        if args.action == 'exec':
            rc, text = await execute(machine, args.command, args.timeout)
            print(text)
            return rc
        await upload(machine, args.source, args.destination)
        print('Upload acknowledged:', args.source.name, '->', args.destination)
        return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
