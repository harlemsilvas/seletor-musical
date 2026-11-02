"""Enriquecimento da biblioteca: metadados e capa do YouTube para MP3s já existentes.

Fila serial (uma consulta por vez, com pausa), sem cookies, que para ao detectar bloqueio
anti-bot e espera downloads em andamento. Nunca registra a saída bruta do yt-dlp.
"""
import asyncio
import logging
import shutil
import sys
import uuid

from . import metadata
from .processes import terminate

log = logging.getLogger('seletor.enrich')
BLOCK_MARKERS = (b'not a bot', b'confirm you')


class Enricher:
    pause = 4.0
    poll_interval = 2.0
    timeout = 90

    def __init__(self, manager, library):
        self.manager = manager
        self.library = library
        self.task = None
        self.single = False
        self.state = {'running': False, 'done': 0, 'total': 0, 'failed': 0, 'error': ''}

    def _command(self, video_id, work):
        return [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-cache-dir', '--js-runtimes', 'node',
                '--no-playlist', '--skip-download', '--write-info-json', '--write-thumbnail',
                '--convert-thumbnails', 'jpg', '--socket-timeout', '15', '--retries', '1', '--no-colors',
                '--output', str(work / '%(id)s.%(ext)s'), '--', f'https://www.youtube.com/watch?v={video_id}']

    def start(self):
        """Inicia uma passada; retorna False se já houver uma em andamento."""
        if self.busy:
            return False
        self.state = {'running': True, 'done': 0, 'total': 0, 'failed': 0, 'error': ''}
        self.task = asyncio.create_task(self.run(), name='library-enrich')
        return True

    async def cancel(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.state = {**self.state, 'running': False}

    async def close(self):
        await self.cancel()

    @property
    def busy(self):
        return bool(self.task and not self.task.done()) or self.single

    async def enrich_track(self, track_id):
        """Enriquece uma única faixa (ação manual). Retorna 'ok', 'failed', 'blocked', 'busy', 'download' ou 'missing'."""
        if self.busy:
            return 'busy'
        if self.manager.active_id:
            return 'download'
        with self.manager._connect() as conn:
            row = conn.execute("SELECT filename,video_id,title,channel FROM library_tracks WHERE id=? AND available=1 AND video_id IS NOT NULL",
                               (track_id,)).fetchone()
        if row is None:
            return 'missing'
        self.single = True
        try:
            return await self._one(dict(row))
        finally:
            self.single = False
            self.library.request_refresh()

    def _candidates(self):
        with self.manager._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT filename,video_id,title,channel FROM library_tracks WHERE available=1 AND video_id IS NOT NULL "
                "AND meta_status!='done' ORDER BY added_at, id")]

    async def run(self):
        try:
            rows = await asyncio.to_thread(self._candidates)
            self.state['total'] = len(rows)
            for index, row in enumerate(rows):
                while self.manager.active_id:  # não concorre com downloads
                    await asyncio.sleep(self.poll_interval)
                outcome = await self._one(row)
                if outcome == 'blocked':
                    self.state['error'] = 'O YouTube pediu verificação anti-bot. A fila foi interrompida; tente novamente mais tarde.'
                    break
                self.state['done' if outcome == 'ok' else 'failed'] += 1
                if index + 1 < len(rows):
                    await asyncio.sleep(self.pause)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Falha ao enriquecer a biblioteca')
            self.state['error'] = 'Não foi possível concluir o enriquecimento. Verifique espaço livre e dependências.'
        finally:
            self.state['running'] = False
            self.library.request_refresh()

    async def _tail(self, stream):
        tail = b''
        while chunk := await stream.read(4096):
            tail = (tail + chunk)[-8192:]
        return tail.lower()

    async def _one(self, row):
        """'ok', 'failed' ou 'blocked'."""
        vid = row['video_id']
        target = self.library.safe_file(row['filename'])
        if target is None:
            return 'failed'
        work = self.manager.download_dir / '.partial' / f'enrich-{uuid.uuid4().hex}'
        proc = errors = None
        try:
            await asyncio.to_thread(work.mkdir, parents=True, exist_ok=True)
            proc = await asyncio.create_subprocess_exec(*self._command(vid, work), stdin=asyncio.subprocess.DEVNULL,
                                                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                                                        start_new_session=True)
            errors = asyncio.create_task(self._tail(proc.stderr))
            try:
                code = await asyncio.wait_for(proc.wait(), self.timeout)
            except asyncio.TimeoutError:
                return 'failed'
            tail = await errors
            if code != 0:
                return 'blocked' if any(m in tail for m in BLOCK_MARKERS) else 'failed'
            result = await asyncio.to_thread(metadata.apply, self.manager._connect, self.manager.covers_dir, vid, work,
                                             target, row['title'], row['channel'])
            return 'ok' if result and result[1] else 'failed'
        finally:
            if proc:
                await terminate(proc)
            if errors:
                errors.cancel()
                await asyncio.gather(errors, return_exceptions=True)
            await asyncio.to_thread(shutil.rmtree, work, True)
