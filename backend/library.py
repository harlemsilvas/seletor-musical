"""Catálogo local. A pasta de mídia nunca é exposta como diretório público."""
import asyncio
import logging
from pathlib import Path
import subprocess
import threading
import uuid

from . import artist as artists, metadata
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
        video_meta = {r['video_id']: dict(r) for r in conn.execute('SELECT * FROM video_meta')}
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
            meta = video_meta.get(vid)
            if old and old['available'] and old['size'] == stat.st_size and old['mtime_ns'] == stat.st_mtime_ns:
                # Reaproveitar metadados; um histórico recuperado ainda pode melhorar o título.
                title = record.get('title') or old['title']
                channel = record.get('channel') or old['channel']
                original = record.get('title') or old['original_title']
                changes = {'title': title, 'channel': channel, 'original_title': original, 'message': ''}
                if meta:
                    changes.update(self._from_meta(meta))
                elif not old['meta_source']:
                    # Primeira classificação (bancos anteriores à migração 3): sem ffprobe, só inferência.
                    guess = artists.infer(original or title, channel, old['artist'], 'tags' if old['artist'] else '')
                    changes.update(artist=guess['artist'], artist_primary=guess['artist_primary'],
                                   track=guess['track'], meta_source=guess['source'])
                if any(old[key] != value for key, value in changes.items()):
                    conn.execute('UPDATE library_tracks SET ' + ','.join(f'{key}=?' for key in changes) + ' WHERE id=?',
                                 (*changes.values(), old['id']))
                    conn.commit()
                count += 1
                continue
            available, message, tags, duration = 1, '', {}, None
            try:
                duration, tags = self.probe(path)
            except (OSError, subprocess.SubprocessError, ValueError, TypeError):
                available, message = 0, 'MP3 inválido ou não foi possível ler o áudio. Verifique FFprobe e atualize a biblioteca.'
            title = record.get('title') or tags.get('title') or display_title(path.stem)
            channel = record.get('channel', '')
            guess = artists.infer(record.get('title') or tags.get('title') or title, channel,
                                  tags.get('artist', ''), 'tags' if tags.get('artist') else '')
            values = {'id': uuid.uuid4().hex, 'filename': path.name, 'video_id': vid, 'title': title, 'channel': channel,
                      'artist': guess['artist'], 'album': tags.get('album', ''), 'duration': duration, 'size': stat.st_size,
                      'mtime_ns': stat.st_mtime_ns, 'available': available, 'message': message,
                      'original_title': record.get('title', ''), 'artist_primary': guess['artist_primary'],
                      'track': guess['track'], 'meta_source': guess['source']}
            if old:  # arquivo reanalisado: não perder datas/capa já conhecidas
                values.update({k: old[k] for k in ('release_date', 'upload_date', 'has_cover', 'meta_status')})
            if meta:
                values.update(self._from_meta(meta))
                if not meta['album']:
                    values['album'] = tags.get('album', '')
            updates = ','.join(f'{k}=excluded.{k}' for k in values if k not in ('id', 'filename', 'original_title'))
            conn.execute(f'''INSERT INTO library_tracks({','.join(values)}) VALUES({','.join('?' * len(values))})
                ON CONFLICT(filename) DO UPDATE SET {updates},
                original_title=CASE WHEN excluded.original_title!='' THEN excluded.original_title ELSE library_tracks.original_title END''',
                tuple(values.values()))
            conn.commit()
            count += 1
        if not self.stop.is_set():
            for filename, row in previous.items():
                if filename not in seen and (row['available'] or not row['message']):
                    conn.execute("UPDATE library_tracks SET available=0,message='Arquivo não encontrado na pasta de músicas.' WHERE id=?", (row['id'],))
            conn.commit()
        return count

    @staticmethod
    def _from_meta(meta):
        """Metadados do yt-dlp (video_meta) têm prioridade sobre a inferência pelo nome."""
        fields = {'artist': meta['artist'], 'artist_primary': meta['artist_primary'], 'track': meta['track'],
                  'release_date': meta['release_date'], 'upload_date': meta['upload_date'],
                  'has_cover': meta['has_cover'], 'meta_source': meta['source'] or 'youtube', 'meta_status': 'done'}
        if meta['album']:
            fields['album'] = meta['album']
        return fields

    def listing(self, search='', sort='newest', offset=0, limit=50, artist=''):
        with self.manager._connect() as conn:
            conn.create_function('fold', 1, lambda value: value.casefold())
            where = "instr(fold(title || ' ' || channel || ' ' || artist),fold(?))>0"
            params = [search]
            if artist:
                where += ' AND fold(artist_primary)=fold(?)'
                params.append(artist)
            total = conn.execute(f'SELECT count(*) FROM library_tracks WHERE {where}', params).fetchone()[0]
            order = {'title': 'fold(title), id', 'artist': "fold(artist_primary), fold(CASE WHEN track!='' THEN track ELSE title END), id"}.get(sort, 'added_at DESC, id')
            rows = [dict(row) for row in conn.execute(f'SELECT * FROM library_tracks WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?', (*params, limit, offset))]
            for row in rows:
                row.pop('filename')
                row.pop('mtime_ns')
                row.pop('original_filename')
                row['available'] = bool(row['available'])
                row['has_cover'] = bool(row['has_cover'])
            return {'items': rows, 'total': total, 'offset': offset, 'limit': limit, 'sync': dict(self.state)}

    def artist_list(self):
        """Artistas distintos sem diferenciar maiúsculas (P!NK e P!nk viram um só)."""
        with self.manager._connect() as conn:
            conn.create_function('fold', 1, lambda value: value.casefold())
            rows = conn.execute("""SELECT max(artist_primary) AS artist, count(*) AS count FROM library_tracks
                WHERE artist_primary!='' GROUP BY fold(artist_primary) ORDER BY fold(max(artist_primary))""")
            return [dict(row) for row in rows]

    def cover_file(self, track_id):
        """Capa local (JPEG em dados do app) do vídeo da faixa, sem aceitar caminhos do navegador."""
        with self.manager._connect() as conn:
            row = conn.execute('SELECT video_id,has_cover FROM library_tracks WHERE id=?', (track_id,)).fetchone()
        if not row or not row['has_cover'] or not row['video_id']:
            return None
        path = metadata.cover_path(self.manager.covers_dir, row['video_id'])
        try:
            if path.is_symlink() or not path.is_file() or path.resolve().parent != self.manager.covers_dir.resolve():
                return None
        except OSError:
            return None
        return path

    def audio_file(self, track_id):
        with self.manager._connect() as conn:
            row = conn.execute('SELECT filename,available FROM library_tracks WHERE id=?', (track_id,)).fetchone()
        if not row or not row['available']:
            return None
        return self.safe_file(row['filename'])
