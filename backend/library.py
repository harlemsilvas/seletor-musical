"""Catálogo local. A pasta de mídia nunca é exposta como diretório público."""
import asyncio
import logging
from pathlib import Path
import subprocess
import threading
import uuid

from .media import display_title, probe_mp3, video_id_from_stem
from .migrations import migrate

log = logging.getLogger('seletor.library')


class Library:
    def __init__(self, manager):
        self.manager = manager
        self.root = manager.download_dir
        self.wake = asyncio.Event()
        self.stop = threading.Event()
        self.state = {'running': False, 'checked': 0, 'error': ''}
        self.task = None
        self.loop = None

    def initialize(self):
        with self.manager._connect() as conn:
            migrate(conn)

    async def start(self):
        await asyncio.to_thread(self.initialize)
        self.loop = asyncio.get_running_loop()
        self.task = asyncio.create_task(self._worker())
        self.request_refresh()

    def request_refresh(self):
        if self.loop and not self.stop.is_set():
            self.loop.call_soon_threadsafe(self.wake.set)

    async def close(self):
        self.stop.set()
        self.wake.set()
        if self.task:
            await self.task

    async def _worker(self):
        while True:
            await self.wake.wait()
            self.wake.clear()
            if self.stop.is_set():
                return
            self.state = {'running': True, 'checked': 0, 'error': ''}
            try:
                count = await asyncio.to_thread(self.scan)
                self.state = {'running': False, 'checked': count, 'error': ''}
            except Exception:
                log.exception('Falha ao atualizar catálogo local')
                self.state = {'running': False, 'checked': 0, 'error': 'Não foi possível atualizar a biblioteca. Verifique acesso à pasta e espaço livre.'}

    def safe_file(self, filename):
        # Arquivos diretos, sem symlinks e sem caminhos fornecidos pelo navegador.
        path = self.root / filename
        try:
            if Path(filename).name != filename or path.suffix.lower() != '.mp3' or path.is_symlink():
                return None
            if path.resolve().parent != self.root.resolve() or not path.is_file():
                return None
            return path
        except OSError:
            return None

    def probe(self, path):
        return probe_mp3(path)

    def scan(self):
        # Uma conexão por varredura; commit a cada faixa para não bloquear downloads durante o ffprobe.
        conn = self.manager._open()
        try:
            return self._scan(conn)
        finally:
            conn.close()

    def _scan(self, conn):
        history = {}
        for row in conn.execute("SELECT video_id,title,channel FROM downloads WHERE status='completed' ORDER BY rowid DESC"):
            history.setdefault(row['video_id'], dict(row))
        previous = {r['filename']: dict(r) for r in conn.execute('SELECT * FROM library_tracks')}
        conn.rollback()
        seen = set()
        count = 0
        # Apenas arquivos da raiz; nunca entrar em .partial.
        for candidate in self.root.glob('*'):
            if self.stop.is_set():
                return count
            if candidate.suffix.lower() != '.mp3':
                continue
            path = self.safe_file(candidate.name)
            if path is None:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            seen.add(path.name)
            old = previous.get(path.name)
            vid = video_id_from_stem(path.stem)
            record = history.get(vid, {})
            if old and old['available'] and old['size'] == stat.st_size and old['mtime_ns'] == stat.st_mtime_ns:
                # Reaproveitar metadados; um histórico recuperado ainda pode melhorar o título.
                title = record.get('title') or old['title']
                channel = record.get('channel') or old['channel']
                original = record.get('title') or old['original_title']
                if (title, channel, original, old['message']) != (old['title'], old['channel'], old['original_title'], ''):
                    conn.execute("UPDATE library_tracks SET title=?,channel=?,original_title=?,message='' WHERE id=?", (title, channel, original, old['id']))
                    conn.commit()
                count += 1
                continue
            available, message, tags, duration = 1, '', {}, None
            try:
                duration, tags = self.probe(path)
            except (OSError, subprocess.SubprocessError, ValueError, TypeError):
                available, message = 0, 'MP3 inválido ou não foi possível ler o áudio. Verifique FFprobe e atualize a biblioteca.'
            title = record.get('title') or tags.get('title') or display_title(path.stem)
            conn.execute('''INSERT INTO library_tracks(id,filename,video_id,title,channel,artist,album,duration,size,mtime_ns,available,message,original_title)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(filename) DO UPDATE SET
                video_id=excluded.video_id,title=excluded.title,channel=excluded.channel,artist=excluded.artist,
                album=excluded.album,duration=excluded.duration,size=excluded.size,mtime_ns=excluded.mtime_ns,
                available=excluded.available,message=excluded.message,
                original_title=CASE WHEN excluded.original_title!='' THEN excluded.original_title ELSE library_tracks.original_title END''',
                (uuid.uuid4().hex, path.name, vid, title, record.get('channel', ''), tags.get('artist', ''), tags.get('album', ''),
                 duration, stat.st_size, stat.st_mtime_ns, available, message, record.get('title', '')))
            conn.commit()
            count += 1
        if not self.stop.is_set():
            for filename, row in previous.items():
                if filename not in seen and (row['available'] or not row['message']):
                    conn.execute("UPDATE library_tracks SET available=0,message='Arquivo não encontrado na pasta de músicas.' WHERE id=?", (row['id'],))
            conn.commit()
        return count

    def listing(self, search='', sort='newest', offset=0, limit=50):
        with self.manager._connect() as conn:
            conn.create_function('fold', 1, lambda value: value.casefold())
            where = "instr(fold(title || ' ' || channel || ' ' || artist),fold(?))>0"
            total = conn.execute(f'SELECT count(*) FROM library_tracks WHERE {where}', (search,)).fetchone()[0]
            order = 'fold(title), id' if sort == 'title' else 'added_at DESC, id'
            rows = [dict(row) for row in conn.execute(f'SELECT * FROM library_tracks WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?', (search, limit, offset))]
            for row in rows:
                row.pop('filename')
                row.pop('mtime_ns')
                row.pop('original_filename')
                row['available'] = bool(row['available'])
            return {'items': rows, 'total': total, 'offset': offset, 'limit': limit, 'sync': dict(self.state)}

    def audio_file(self, track_id):
        with self.manager._connect() as conn:
            row = conn.execute('SELECT filename,available FROM library_tracks WHERE id=?', (track_id,)).fetchone()
        if not row or not row['available']:
            return None
        return self.safe_file(row['filename'])
