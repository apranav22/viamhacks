"""Offline regression tests for our shell/file framing, not a claim about the remote RDK implementation."""
import asyncio
import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import station_shell as S


class Stream:
    def __init__(self, shell=False, ack=True):
        self.sent=[];self.ended=False;self.shell=shell;self.ack=ack
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    async def send_message(self,request):self.sent.append(request)
    async def end(self):self.ended=True
    def __aiter__(self):
        async def responses():
            if self.shell:
                marker=re.search(r'(SORTER_[0-9a-f]+)_BEGIN',self.sent[0].data_in).group(1)
                yield SimpleNamespace(data_out=f'prompt noise\n{marker}_BEGIN\nowned result\n{marker}_END:7\nlogout\n',data_err='',eof=True)
            elif self.ack:yield SimpleNamespace(ack_last_file=True)
        return responses()


class StationShellTests(unittest.TestCase):
    def test_execution_markers_and_exit_code(self):
        stream=Stream(shell=True)
        stub=SimpleNamespace(Shell=SimpleNamespace(open=lambda **kw:stream))
        with patch.object(S,'ShellServiceStub',return_value=stub):
            rc,text=asyncio.run(S.execute(SimpleNamespace(_channel=object()),'false'))
        self.assertEqual(rc,7);self.assertEqual(text,'owned result');self.assertTrue(stream.ended)
        self.assertEqual(len(stream.sent),1)  # no automatic re-execution

    def test_copy_name_only_first_and_empty_eof(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'payload';data=b'abc123'*7000;p.write_bytes(data)
            stream=Stream();stub=SimpleNamespace(CopyFilesToMachine=SimpleNamespace(open=lambda **kw:stream))
            verify=AsyncMock(return_value=(0,json.dumps({'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})))
            with patch.object(S,'ShellServiceStub',return_value=stub),patch.object(S,'execute',verify):
                asyncio.run(S.upload(SimpleNamespace(_channel=object()),p,'/owned/payload'))
            packets=[r.file_data for r in stream.sent if r.HasField('file_data')]
            self.assertEqual(packets[0].name,'payload')
            self.assertTrue(all(not q.name for q in packets[1:]))
            self.assertTrue(packets[-1].eof);self.assertEqual(packets[-1].data,b'')
            self.assertTrue(all(not q.eof for q in packets[:-1]))
            self.assertEqual(b''.join(q.data for q in packets),data)
            self.assertTrue(stream.ended);self.assertEqual(verify.await_count,1)

    def test_unacknowledged_upload_is_not_retried(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'payload';p.write_bytes(b'abc')
            stream=Stream(ack=False);stub=SimpleNamespace(CopyFilesToMachine=SimpleNamespace(open=lambda **kw:stream))
            with patch.object(S,'ShellServiceStub',return_value=stub):
                with self.assertRaisesRegex(RuntimeError,'not acknowledged'):
                    asyncio.run(S.upload(SimpleNamespace(_channel=object()),p,'/owned/payload'))
            self.assertEqual(len([r for r in stream.sent if r.HasField('metadata')]),1)

    def test_large_upload_fails_before_remote_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'large';p.write_bytes(b'0'*(2*1024*1024+1))
            with patch.object(S,'ShellServiceStub') as stub:
                with self.assertRaisesRegex(ValueError,'capped'):
                    asyncio.run(S.upload(SimpleNamespace(_channel=object()),p,'/owned/large'))
                stub.assert_not_called()


if __name__=='__main__':unittest.main()
