import asyncio
import os
import signal
import sys
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import HTTPException
from backend.app import app, youtube_url, terminate, extract

HEADERS = {'origin': 'http://localhost:8766', 'x-seletor-client': '1'}
VIDEO = 'https://www.youtube.com/watch?v=D0_GWTy9FEM'

class BackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost:8766')
    async def asyncTearDown(self):
        await self.client.aclose()
    async def test_origin_host_and_validation(self):
        for headers in ({}, {'origin':'https://evil.example','x-seletor-client':'1'}):
            self.assertEqual((await self.client.post('/api/query',json={'url':VIDEO},headers=headers)).status_code,403)
        self.assertEqual((await self.client.get('/api/config',headers={'host':'evil.example'})).status_code,400)
        for url in ('https://youtube.com.evil/watch?v=D0_GWTy9FEM','file:///etc/passwd','https://youtube.com@127.0.0.1/', 'https://youtube.com/redirect?url=http://localhost', 'https://youtu.be/no'):
            self.assertEqual((await self.client.post('/api/query',json={'url':url},headers=HEADERS)).status_code,422)
        self.assertEqual((await self.client.post('/api/query',json={'url':VIDEO,'limit':201},headers=HEADERS)).status_code,422)
    async def test_query_and_errors(self):
        data={'entries':[{'id':'D0_GWTy9FEM','title':'Música','channel':'Canal','duration':123},None,{'id':'D0_GWTy9FEM'},{'id':'bad'}]}
        with patch('backend.app.extract',AsyncMock(return_value=data)):
            r=await self.client.post('/api/query',json={'url':VIDEO+'&list=RDtest'},headers=HEADERS)
            self.assertEqual(r.status_code,200)
            self.assertEqual(len(r.json()['items']),1)
            self.assertEqual(r.json()['items'][0]['url'],VIDEO)
        with patch('backend.app.extract',AsyncMock(side_effect=HTTPException(502,'Falha controlada'))):
            self.assertEqual((await self.client.post('/api/query',json={'url':VIDEO},headers=HEADERS)).status_code,502)
    async def test_concurrent_query(self):
        from backend.app import semaphore
        async with semaphore:
            self.assertEqual((await self.client.post('/api/query',json={'url':VIDEO},headers=HEADERS)).status_code,429)
    async def test_process_group(self):
        # A child ignores TERM: escalation must also kill descendants after parent exits.
        script='import subprocess,time,sys; subprocess.Popen([sys.executable,"-c","import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)"]); time.sleep(60)'
        p=await asyncio.create_subprocess_exec(sys.executable,'-c',script,start_new_session=True)
        await asyncio.sleep(.2)
        await terminate(p)
        self.assertIsNotNone(p.returncode)
        await asyncio.sleep(.1)
        # No live processes may remain in the session (zombies can await OS reaping).
        import pathlib
        for stat in pathlib.Path('/proc').glob('[0-9]*/stat'):
            try:
                fields=stat.read_text().rsplit(')',1)[1].split()
                if int(fields[2])==p.pid:
                    self.assertEqual(fields[0],'Z')
            except (FileNotFoundError, ProcessLookupError): pass
    async def test_extract_failure_and_cancellation_cleanup(self):
        for failure in (asyncio.TimeoutError(), asyncio.CancelledError()):
            proc = AsyncMock()
            proc.communicate.side_effect = failure
            with patch('backend.app.asyncio.create_subprocess_exec', AsyncMock(return_value=proc)) as spawn, patch('backend.app.terminate', AsyncMock()) as cleanup:
                with self.assertRaises((HTTPException, asyncio.CancelledError)):
                    await extract(VIDEO, 1)
                cleanup.assert_awaited_once_with(proc)
                args = spawn.call_args.args
                self.assertIn('--skip-download', args)
                self.assertEqual(args[-1], VIDEO)
                self.assertNotIn('shell', spawn.call_args.kwargs)
    async def test_query_bot_verification_is_structured(self):
        proc=AsyncMock()
        proc.returncode=1
        proc.communicate.return_value=(b'null', b'ERROR: Sign in to confirm you are not a bot')
        with patch('backend.app.asyncio.create_subprocess_exec',AsyncMock(return_value=proc)), patch('backend.app.terminate',AsyncMock()):
            with self.assertRaises(HTTPException) as error:
                await extract(VIDEO,1)
            self.assertEqual(error.exception.detail['code'],'youtube_verification')
            self.assertEqual(error.exception.detail['url'],VIDEO)

    def test_canonical_mix(self):
        self.assertEqual(youtube_url('https://youtu.be/D0_GWTy9FEM?list=RDD0_GWTy9FEM&index=2'),VIDEO+'&list=RDD0_GWTy9FEM')
