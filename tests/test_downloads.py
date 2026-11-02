import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from backend.app import app
from backend.downloads import DownloadManager, QueueFull

READY = {'ready': True, 'problems': [], 'versions': {}}
URL = 'https://www.youtube.com/watch?v='
HEADERS = {'Origin': 'http://localhost:8766', 'X-Seletor-Client': '1'}


class LocalQueue(DownloadManager):
    """Fake extractor, real subprocess tree and real disk/SQLite operations."""
    def _command(self, job, work):
        script = '''
import json, pathlib, subprocess, sys, time
work=pathlib.Path(sys.argv[1]); vid=sys.argv[2]
if vid == 'cancelABCDE':
    child=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'])
    (work/'child.pid').write_text(str(child.pid))
print('SM_PROGRESS '+json.dumps({'downloaded':50,'total':100,'speed':25,'eta':2}), flush=True)
time.sleep(0.3)
if vid == 'cancelABCDE': time.sleep(60)
if vid == 'failureABCD': sys.exit(1)
print('SM_CONVERT',flush=True)
time.sleep(0.2)
(work/(vid+'.mp3')).write_bytes(b'completed fixture')
'''
        return [sys.executable, '-c', script, str(work), job['video_id']]


class DownloadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.manager = LocalQueue(root/'data', root/'music')
        with patch('backend.downloads.dependencies', return_value=READY):
            await self.manager.start()

    async def asyncTearDown(self):
        await self.manager.close()
        self.temp.cleanup()

    def item(self, vid):
        return {'video_id':vid,'url':URL+vid,'title':'Uma música '+vid}

    async def wait_status(self, job_id, statuses, timeout=5):
        async def poll():
            while True:
                row = await asyncio.to_thread(self.manager._get, job_id)
                if row['status'] in statuses:
                    return row
                await asyncio.sleep(.02)
        return await asyncio.wait_for(poll(), timeout)

    async def test_serial_progress_completion_and_deduplication(self):
        result = await self.manager.add([self.item('abcdefghijk'),self.item('lmnopqrstuv')])
        first, second = result['accepted']
        await self.wait_status(first, {'downloading'})
        # Second stays pending while first runs.
        self.assertEqual((await asyncio.to_thread(self.manager._get, second))['status'], 'pending')
        for _ in range(100):
            row=await asyncio.to_thread(self.manager._get, first)
            if row['progress'] == 50:
                break
            await asyncio.sleep(.01)
        self.assertEqual(row['progress'],50)
        self.assertEqual(row['speed'],25)
        await self.wait_status(first, {'converting'})
        await self.wait_status(second, {'completed'})
        self.assertEqual((self.manager.download_dir/'abcdefghijk.mp3').read_bytes(), b'completed fixture')
        again = await self.manager.add([self.item('abcdefghijk')])
        self.assertEqual(again['skipped'][0]['reason'],'completed')
        # A deleted file may be requested again without erasing prior history.
        (self.manager.download_dir/'abcdefghijk.mp3').unlink()
        self.assertEqual(len((await self.manager.add([self.item('abcdefghijk')]))['accepted']),1)

    async def test_cancel_active_descendant_pending_and_preserve_completed(self):
        done=(await self.manager.add([self.item('abcdefghijk')]))['accepted'][0]
        await self.wait_status(done, {'completed'})
        active,pending=(await self.manager.add([self.item('cancelABCDE'),self.item('lmnopqrstuv')]))['accepted']
        await self.wait_status(active, {'downloading'})
        child_file=self.manager.download_dir/'.partial'/active/'child.pid'
        for _ in range(100):
            if child_file.exists(): break
            await asyncio.sleep(.02)
        child_pid=int(child_file.read_text())
        self.assertEqual(await self.manager.cancel(pending),'cancelled')
        self.assertEqual(await self.manager.cancel(active),'cancelled')
        await self.wait_status(active, {'cancelled'})
        self.assertEqual((await asyncio.to_thread(self.manager._get,pending))['status'],'cancelled')
        await asyncio.sleep(.1)
        stat=Path(f'/proc/{child_pid}/stat')
        if stat.exists(): self.assertEqual(stat.read_text().split()[2],'Z')
        self.assertFalse((self.manager.download_dir/'cancelABCDE.mp3').exists())
        self.assertFalse((self.manager.download_dir/'lmnopqrstuv.mp3').exists())
        self.assertFalse(child_file.parent.exists())
        self.assertTrue((self.manager.download_dir/'abcdefghijk.mp3').is_file())

    async def test_failure_continues_and_shutdown_does_not_resume(self):
        failed,next_job=(await self.manager.add([self.item('failureABCD'),self.item('abcdefghijk')]))['accepted']
        await self.wait_status(next_job, {'completed'})
        self.assertEqual((await asyncio.to_thread(self.manager._get,failed))['status'],'failed')
        active,pending=(await self.manager.add([self.item('cancelABCDE'),self.item('lmnopqrstuv')]))['accepted']
        await self.wait_status(active, {'downloading'})
        await self.manager.close()
        self.manager=LocalQueue(self.manager.data_dir,self.manager.download_dir)
        with patch('backend.downloads.dependencies',return_value=READY):
            await self.manager.start()
        rows=(await self.manager.snapshot())['jobs']
        self.assertEqual({r['status'] for r in rows if r['id'] in (active,pending)}, {'interrupted'})
        self.assertEqual((await asyncio.to_thread(self.manager._get,next_job))['status'],'completed')
        self.assertIsNone(self.manager.active_id)

    async def test_api_validation_security_cancellation_and_duplicate(self):
        app.state.downloads=self.manager
        with patch('backend.downloads.dependencies',return_value=READY):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost:8766') as c:
                body={'items':[{'url':URL+'cancelABCDE'+'&list=RDtest','title':'Teste'}]}
                self.assertEqual((await c.post('/api/downloads',json=body)).status_code,403)
                for bad in ({'items':[{'url':'https://youtube.com/playlist?list=PLabc'}]}, {'items':[{'url':'http://127.0.0.1/'}]}, {'items':[{'url':URL+'abcdefghijk','path':'/tmp/arbitrary'}]}):
                    self.assertEqual((await c.post('/api/downloads',json=bad,headers=HEADERS)).status_code,422)
                r=await c.post('/api/downloads',json=body,headers=HEADERS)
                self.assertEqual(r.status_code,202)
                job_id=r.json()['accepted'][0]
                row=await asyncio.to_thread(self.manager._get,job_id)
                self.assertEqual(row['url'],URL+'cancelABCDE')
                again=await c.post('/api/downloads',json=body,headers=HEADERS)
                self.assertEqual(again.json()['skipped'][0]['reason'],'queued')
                self.assertEqual((await c.post(f'/api/downloads/{job_id}/cancel',headers=HEADERS)).status_code,200)
                self.assertEqual((await c.post('/api/downloads/'+'0'*32+'/cancel',headers=HEADERS)).status_code,404)
                self.assertEqual((await c.get('/api/downloads')).status_code,200)
        with patch('backend.downloads.dependencies',return_value={'ready':False,'problems':['FFmpeg ausente'],'versions':{}}):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost:8766') as c:
                self.assertEqual((await c.post('/api/downloads',json=body,headers=HEADERS)).status_code,503)

    async def test_no_overwrite_and_queue_capacity(self):
        self.manager.download_dir.mkdir()
        target=self.manager.download_dir/'abcdefghijk.mp3'
        target.write_bytes(b'keep existing')
        skipped=await self.manager.add([self.item('abcdefghijk')])
        self.assertEqual(skipped['accepted'],[])
        self.assertEqual(target.read_bytes(),b'keep existing')
        with self.assertRaises(QueueFull):
            await self.manager.add([self.item('lmnopqrstuv')]*501)
        # Publishing another job cannot replace an existing MP3.
        work=self.manager.download_dir/'.partial'/'fixture'
        work.mkdir(parents=True)
        (work/'abcdefghijk.mp3').write_bytes(b'new')
        self.assertTrue(await asyncio.to_thread(self.manager._publish, {'id':'unrecorded','video_id':'abcdefghijk'}, work))
        self.assertEqual(target.read_bytes(),b'keep existing')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg necessário')
    async def test_real_ytdlp_ffmpeg_local_fixture(self):
        # Extrator e conversor reais, apenas um áudio sintético local e sem rede.
        fixture=Path(self.temp.name)/'sample.wav'
        await asyncio.to_thread(subprocess.run, ['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=0.5',str(fixture)], check=True)
        manager=self.manager
        def local_command(job, work):
            args=DownloadManager._command(manager,job,work)
            args.insert(3,'--enable-file-urls')
            args[-1]=fixture.as_uri()
            return args
        with patch.object(manager,'_command',side_effect=local_command):
            job_id=(await manager.add([self.item('abcdefghijk')]))['accepted'][0]
            row=await self.wait_status(job_id,{'completed','failed'},timeout=15)
        self.assertEqual(row['status'],'completed',row['message'])
        result=await asyncio.to_thread(subprocess.run, ['ffprobe','-v','error','-show_entries','stream=codec_name','-of','json',str(manager.download_dir/'abcdefghijk.mp3')], capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout)['streams'][0]['codec_name'],'mp3')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg necessário')
    async def test_cancel_during_real_ffmpeg_conversion(self):
        def conversion_command(job,work):
            script="import subprocess,pathlib,sys; w=pathlib.Path(sys.argv[1]); p=subprocess.Popen(['ffmpeg','-v','error','-re','-f','lavfi','-i','anullsrc','-t','60','-c:a','libmp3lame',str(w/'abcdefghijk.mp3')]); (w/'ffmpeg.pid').write_text(str(p.pid)); print('SM_CONVERT',flush=True); p.wait()"
            return [sys.executable,'-c',script,str(work)]
        with patch.object(self.manager,'_command',side_effect=conversion_command):
            job_id=(await self.manager.add([self.item('abcdefghijk')]))['accepted'][0]
            await self.wait_status(job_id,{'converting'})
            work=self.manager.download_dir/'.partial'/job_id
            pid=int((work/'ffmpeg.pid').read_text())
            await self.manager.cancel(job_id)
            await self.wait_status(job_id,{'cancelled'})
        await asyncio.sleep(.1)
        stat=Path(f'/proc/{pid}/stat')
        if stat.exists(): self.assertEqual(stat.read_text().rsplit(')',1)[1].split()[0],'Z')
        self.assertFalse((self.manager.download_dir/'abcdefghijk.mp3').exists())
        self.assertFalse(work.exists())

    async def test_shutdown_preserves_already_published_completion(self):
        published=asyncio.Event()
        async def completed_cleanup(job):
            self.manager.download_dir.mkdir(parents=True,exist_ok=True)
            (self.manager.download_dir/f"{job['video_id']}.mp3").write_bytes(b'completed')
            await self.manager.update(job['id'],status='completed',progress=100,filename=f"{job['video_id']}.mp3")
            published.set()
            await asyncio.sleep(60)
        with patch.object(self.manager,'_run',side_effect=completed_cleanup):
            job_id=(await self.manager.add([self.item('abcdefghijk')]))['accepted'][0]
            await asyncio.wait_for(published.wait(),5)
            await self.manager.close()
        self.assertEqual((await asyncio.to_thread(self.manager._get,job_id))['status'],'completed')
        self.assertTrue((self.manager.download_dir/'abcdefghijk.mp3').exists())

    async def test_single_owner(self):
        other=DownloadManager(self.manager.data_dir,self.manager.download_dir)
        with self.assertRaises(RuntimeError):
            await other.start()

    def test_real_command_is_individual_mp3_without_shell(self):
        command=DownloadManager._command(self.manager,self.item('abcdefghijk'),Path('/tmp/work'))
        self.assertIn('--no-playlist',command)
        self.assertIn('--extract-audio',command)
        self.assertEqual(command[command.index('--audio-format')+1],'mp3')
        self.assertEqual(command[-2: ],['--',URL+'abcdefghijk'])
