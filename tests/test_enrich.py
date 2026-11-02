import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import httpx
from mutagen.id3 import ID3
from backend.app import app
from backend.downloads import DownloadManager
from backend.enrich import Enricher
from backend.library import Library
from backend.tagging import audio_md5

HEADERS = {'Origin': 'http://localhost:8766', 'X-Seletor-Client': '1'}
OK_SCRIPT = """
import json, pathlib, subprocess, sys
work=pathlib.Path(sys.argv[1]); vid=sys.argv[2]
(work/(vid+'.info.json')).write_text(json.dumps({'title':'Cantor '+vid+' - Faixa '+vid+' (Official Video)','channel':'Canal','upload_date':'20170816'}))
subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=640x360:rate=1','-frames:v','1',str(work/(vid+'.jpg'))],check=True)
"""
BLOCK_SCRIPT = "import sys; sys.stderr.write(\"Sign in to confirm you're not a bot\"); sys.exit(1)"
SLEEP_SCRIPT = """
import pathlib, subprocess, sys, time
work=pathlib.Path(sys.argv[1])
child=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'])
(work/'child.pid').write_text(str(child.pid))
time.sleep(60)
"""


class FakeEnricher(Enricher):
    pause = 0
    poll_interval = 0.02
    script = OK_SCRIPT

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    def _command(self, video_id, work):
        self.calls.append(video_id)
        return [sys.executable, '-c', self.script, str(work), video_id]


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/FFprobe necessários')
class EnrichTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.manager = DownloadManager(root / 'data', root / 'music')
        await asyncio.to_thread(self.manager._init_db)
        self.manager.download_dir.mkdir()
        self.manager.diagnostics = {'ready': True, 'problems': [], 'versions': {}}
        self.library = Library(self.manager)
        await asyncio.to_thread(self.library.initialize)
        base = self.manager.download_dir / 'base.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=1', '-map_metadata', '-1', '-c:a', 'libmp3lame', str(base)], check=True)
        self.ids = ['aaaaaaaaaaa', 'bbbbbbbbbbb']
        for vid in self.ids:
            shutil.copyfile(base, self.manager.download_dir / f'Antigo_{vid}.mp3')
        base.unlink()
        await asyncio.to_thread(self.library.scan)
        self.enricher = FakeEnricher(self.manager, self.library)
        app.state.downloads, app.state.library, app.state.enrich = self.manager, self.library, self.enricher
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost:8766')

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.enricher.close()
        self.manager.file_lock.close()
        self.temp.cleanup()

    def tracks(self):
        with self.manager._connect() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM library_tracks ORDER BY video_id')]

    async def test_success_tags_files_covers_and_catalog(self):
        files = {t['video_id']: self.manager.download_dir / t['filename'] for t in self.tracks()}
        self.assertEqual(sorted(files), self.ids)
        before = {vid: audio_md5(path) for vid, path in files.items()}
        await self.enricher.run()
        self.assertEqual(sorted(self.enricher.calls), self.ids)  # uma consulta por vez, cada vídeo uma vez
        self.assertEqual((self.enricher.state['done'], self.enricher.state['failed'], self.enricher.state['error']), (2, 0, ''))
        for vid, path in files.items():
            tags = ID3(path)
            self.assertEqual((str(tags['TPE1']), str(tags['TXXX:YouTube ID'])), (f'Cantor {vid}', vid))
            self.assertIn('APIC:Capa', tags)
            self.assertEqual(audio_md5(path), before[vid])
            self.assertTrue((self.manager.covers_dir / f'{vid}.jpg').is_file())
        await asyncio.to_thread(self.library.scan)
        for row in self.tracks():
            self.assertEqual((row['meta_status'], row['has_cover'], row['upload_date']), ('done', 1, '20170816'))
            self.assertEqual(row['artist_primary'], f"Cantor {row['video_id']}")
        self.assertEqual(list((self.manager.download_dir / '.partial').iterdir()), [])
        # Segunda passada não consulta quem já está pronto.
        self.enricher.calls.clear()
        await self.enricher.run()
        self.assertEqual(self.enricher.calls, [])

    async def test_antibot_block_stops_whole_queue(self):
        self.enricher.script = BLOCK_SCRIPT
        await self.enricher.run()
        self.assertEqual(len(self.enricher.calls), 1)
        self.assertIn('anti-bot', self.enricher.state['error'])
        self.assertEqual({t['meta_status'] for t in self.tracks()}, {''})

    async def test_cancel_kills_process_group_and_cleans_up(self):
        self.enricher.script = SLEEP_SCRIPT
        self.assertTrue(self.enricher.start())
        self.assertFalse(self.enricher.start())
        partial = self.manager.download_dir / '.partial'
        pid_file = None
        for _ in range(200):
            found = list(partial.glob('enrich-*/child.pid')) if partial.exists() else []
            if found:
                pid_file = found[0]
                break
            await asyncio.sleep(.02)
        self.assertIsNotNone(pid_file)
        child = int(pid_file.read_text())
        await self.enricher.cancel()
        self.assertFalse(self.enricher.state['running'])
        await asyncio.sleep(.1)
        stat = Path(f'/proc/{child}/stat')
        if stat.exists():
            self.assertEqual(stat.read_text().rsplit(')', 1)[1].split()[0], 'Z')
        self.assertEqual(list(partial.iterdir()), [])

    async def test_waits_while_download_is_active(self):
        self.manager.active_id = 'job'
        self.enricher.start()
        await asyncio.sleep(.2)
        self.assertEqual(self.enricher.calls, [])
        self.manager.active_id = None
        for _ in range(200):
            if not self.enricher.state['running']:
                break
            await asyncio.sleep(.02)
        self.assertEqual(sorted(self.enricher.calls), self.ids)

    async def test_api_enrich_cover_and_security(self):
        self.assertEqual((await self.client.post('/api/library/enrich')).status_code, 403)
        self.assertEqual((await self.client.post('/api/library/enrich', headers=HEADERS)).status_code, 202)
        for _ in range(300):
            if not self.enricher.state['running']:
                break
            await asyncio.sleep(.02)
        await asyncio.to_thread(self.library.scan)
        data = (await self.client.get('/api/library')).json()
        self.assertEqual(data['enrich']['done'], 2)
        track = data['items'][0]
        self.assertTrue(track['has_cover'])
        response = await self.client.get(f"/api/library/{track['id']}/cover")
        self.assertEqual((response.status_code, response.headers['content-type']), (200, 'image/jpeg'))
        self.assertTrue(response.content.startswith(b'\xff\xd8'))
        self.assertEqual((await self.client.get('/api/library/invalid/cover')).status_code, 404)
        self.assertEqual((await self.client.get('/api/library/' + '0' * 32 + '/cover')).status_code, 404)
        self.assertEqual((await self.client.get(f"/api/library/{track['id']}/cover", headers={'Origin': 'https://evil.example'})).status_code, 403)
        self.assertEqual((await self.client.post('/api/library/enrich/cancel')).status_code, 403)
        self.assertEqual((await self.client.post('/api/library/enrich/cancel', headers=HEADERS)).status_code, 200)
        # Capa trocada por symlink para fora da pasta não é servida.
        cover = self.manager.covers_dir / f"{track['video_id']}.jpg"
        outside = Path(self.temp.name) / 'fora.jpg'
        shutil.copyfile(cover, outside)
        cover.unlink()
        cover.symlink_to(outside)
        self.assertEqual((await self.client.get(f"/api/library/{track['id']}/cover")).status_code, 404)
        self.manager.diagnostics = {'ready': False, 'problems': ['ffmpeg ausente.'], 'versions': {}}
        self.assertEqual((await self.client.post('/api/library/enrich', headers=HEADERS)).status_code, 503)

    async def test_single_track_enrich_statuses_and_guards(self):
        track = self.tracks()[0]
        url = f"/api/library/{track['id']}/enrich"
        self.assertEqual((await self.client.post(url)).status_code, 403)
        self.assertEqual((await self.client.post('/api/library/invalid/enrich', headers=HEADERS)).status_code, 404)
        self.assertEqual((await self.client.post('/api/library/' + '0' * 32 + '/enrich', headers=HEADERS)).status_code, 404)
        # Download em andamento: recusa sem consultar o YouTube.
        self.manager.active_id = 'job'
        self.assertEqual((await self.client.post(url, headers=HEADERS)).status_code, 409)
        self.assertEqual(self.enricher.calls, [])
        self.manager.active_id = None
        # Só a faixa pedida é consultada e gravada.
        response = await self.client.post(url, headers=HEADERS)
        self.assertEqual((response.status_code, response.json()), (200, {'status': 'ok'}))
        self.assertEqual(self.enricher.calls, [track['video_id']])
        await asyncio.to_thread(self.library.scan)
        rows = {t['video_id']: t for t in self.tracks()}
        self.assertEqual((rows[track['video_id']]['meta_status'], rows[track['video_id']]['has_cover']), ('done', 1))
        other = next(t for v, t in rows.items() if v != track['video_id'])
        self.assertEqual((other['meta_status'], other['has_cover']), ('', 0))
        self.assertIn('TXXX:YouTube ID', ID3(self.manager.download_dir / rows[track['video_id']]['filename']))
        self.assertNotIn('TXXX:YouTube ID', ID3(self.manager.download_dir / other['filename']))
        # Ocupado: lote em andamento (ou outra faixa) bloqueia a ação individual.
        self.enricher.single = True
        self.assertEqual((await self.client.post(url, headers=HEADERS)).status_code, 409)
        self.enricher.single = False
        # Bloqueio anti-bot é informado, sem alterar nada.
        self.enricher.script = BLOCK_SCRIPT
        response = await self.client.post(f"/api/library/{other['id']}/enrich", headers=HEADERS)
        self.assertEqual(response.json(), {'status': 'blocked'})
        self.assertFalse(self.enricher.busy)
        self.manager.diagnostics = {'ready': False, 'problems': ['ffmpeg ausente.'], 'versions': {}}
        self.assertEqual((await self.client.post(url, headers=HEADERS)).status_code, 503)


if __name__ == '__main__':
    unittest.main()
