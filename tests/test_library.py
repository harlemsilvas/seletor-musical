import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import httpx
from backend.app import app
from backend.downloads import DownloadManager
from backend.library import Library

HEADERS={'Origin':'http://localhost:8766','X-Seletor-Client':'1'}

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg/FFprobe necessários')
class LibraryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        self.manager=DownloadManager(root/'data',root/'music')
        await asyncio.to_thread(self.manager._init_db)
        self.library=Library(self.manager)
        await asyncio.to_thread(self.library.initialize)
        self.manager.download_dir.mkdir()
        self.fixture=self.manager.download_dir/'abcdefghijk.mp3'
        await asyncio.to_thread(subprocess.run,['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=2','-metadata','title=Título local','-metadata','artist=Artista local','-c:a','libmp3lame',str(self.fixture)],check=True)
        app.state.library=self.library
        app.state.downloads=self.manager
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost:8766')

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.library.close()
        self.manager.file_lock.close()
        self.temp.cleanup()

    async def scan(self):
        return await asyncio.to_thread(self.library.scan)

    async def listing(self,**kwargs):
        return await asyncio.to_thread(self.library.listing,**kwargs)

    async def test_catalog_cache_search_missing_and_restore(self):
        await self.scan()
        data=await self.listing(search='TÍTULO')
        self.assertEqual(data['total'],1)
        track=data['items'][0]
        self.assertEqual(track['artist'],'Artista local')
        self.assertTrue(track['available'])
        self.assertGreater(track['duration'],1)
        with patch.object(self.library,'probe',side_effect=AssertionError('Cache não utilizado')):
            await self.scan()
        self.assertEqual((await self.listing())['items'][0]['id'],track['id'])
        backup=self.fixture.with_suffix('.backup')
        self.fixture.rename(backup)
        await self.scan()
        self.assertFalse((await self.listing())['items'][0]['available'])
        backup.rename(self.fixture)
        await self.scan()
        self.assertTrue((await self.listing())['items'][0]['available'])

    async def test_history_full_table_partial_invalid_and_symlink(self):
        with self.manager._connect() as conn:
            conn.execute("INSERT INTO downloads(id,video_id,title,url,status,channel) VALUES('old','abcdefghijk','Título do histórico','url','completed','Canal correto')")
        partial=self.manager.download_dir/'.partial'
        partial.mkdir();shutil.copyfile(self.fixture,partial/'hidden.mp3')
        (self.manager.download_dir/'bad.mp3').write_bytes(b'not audio')
        external=Path(self.temp.name)/'outside.mp3';shutil.copyfile(self.fixture,external)
        (self.manager.download_dir/'escape.mp3').symlink_to(external)
        await self.scan()
        data=await self.listing()
        self.assertEqual(data['total'],2)
        good=next(t for t in data['items'] if t['available'])
        self.assertEqual(good['title'],'Título do histórico')
        self.assertEqual(good['channel'],'Canal correto')
        self.assertEqual(len((await self.listing(search='CANAL CORRETO'))['items']),1)
        self.assertFalse(next(t for t in data['items'] if t['title']=='bad')['available'])
        self.assertIsNone(self.library.safe_file('../outside.mp3'))
        self.assertIsNone(self.library.safe_file('escape.mp3'))
        # Replacing a catalogued file with an external symlink blocks streaming too.
        self.fixture.unlink();self.fixture.symlink_to(external)
        self.assertIsNone(self.library.audio_file(good['id']))

    async def test_audio_range_head_missing_origin_and_pagination(self):
        await self.scan()
        track=(await self.listing())['items'][0]
        url=f"/api/library/{track['id']}/audio"
        response=await self.client.get(url,headers={'Range':'bytes=0-15'})
        self.assertEqual(response.status_code,206)
        self.assertEqual(len(response.content),16)
        self.assertEqual(response.headers['content-type'],'audio/mpeg')
        self.assertEqual(response.headers['accept-ranges'],'bytes')
        self.assertEqual((await self.client.head(url)).content,b'')
        self.assertEqual((await self.client.get(url,headers={'Range':'bytes=99999999-'})).status_code,416)
        self.assertEqual((await self.client.get(url,headers={'Origin':'https://evil.example'})).status_code,403)
        self.assertEqual((await self.client.get(url,headers={'Sec-Fetch-Site':'cross-site'})).status_code,403)
        self.assertEqual((await self.client.get('/api/library/invalid/audio')).status_code,404)
        self.assertEqual((await self.client.get('/api/library?limit=101')).status_code,422)
        self.assertEqual((await self.client.get('/api/library?offset=1')).json()['items'],[])
        self.assertEqual((await self.client.post('/api/library/sync')).status_code,403)
        self.assertEqual((await self.client.post('/api/library/sync',headers=HEADERS)).status_code,202)
        self.fixture.unlink()
        self.assertEqual((await self.client.get(url)).status_code,404)

    async def test_completion_triggers_background_catalog_and_migration_preserves_history(self):
        await self.library.start()
        self.manager.on_completed=self.library.request_refresh
        # A published download uses the same callback as the production queue.
        work=self.manager.download_dir/'.partial'/'test';work.mkdir(parents=True)
        shutil.copyfile(self.fixture,work/'lmnopqrstuv.mp3')
        job={'id':'job','video_id':'lmnopqrstuv'}
        with self.manager._connect() as conn:
            conn.execute("INSERT INTO downloads(id,video_id,title,url,status,channel) VALUES('job','lmnopqrstuv','Novo MP3','url','converting','Canal novo')")
        await asyncio.to_thread(self.manager._publish,job,work)
        for _ in range(200):
            if (await self.listing(search='Novo MP3'))['total']: break
            await asyncio.sleep(.03)
        self.assertEqual((await self.listing(search='Novo MP3'))['total'],1)
        await asyncio.to_thread(self.library.initialize)
        with self.manager._connect() as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertEqual(conn.execute("SELECT status FROM downloads WHERE id='job'").fetchone()[0],'completed')
