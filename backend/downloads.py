"""Fila serial, arquivos privados de trabalho e histórico SQLite."""
import asyncio
from contextlib import suppress, contextmanager
import fcntl
from importlib.metadata import version, PackageNotFoundError
import json
import logging
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import uuid

from . import metadata
from .media import final_name, find_files, is_valid_mp3
from .migrations import migrate
from .processes import terminate

log = logging.getLogger('seletor.downloads')
ACTIVE = ('pending', 'downloading', 'converting')


def dependencies():
    problems, versions = [], {}
    for package in ('yt-dlp', 'yt-dlp-ejs'):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            problems.append(f'Instale {package} na .venv.')
    for binary, flag in (('ffmpeg', '-version'), ('ffprobe', '-version'), ('node', '--version')):
        path = shutil.which(binary)
        if not path:
            problems.append(f'{binary} não foi encontrado no PATH.')
            continue
        try:
            result = subprocess.run([path, flag], capture_output=True, timeout=5, text=True, check=True)
            versions[binary] = result.stdout.splitlines()[0][:120]
            if binary == 'node' and int(result.stdout.strip().lstrip('v').split('.')[0]) < 22:
                problems.append('Atualize o Node.js para versão 22 ou superior.')
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            problems.append(f'Não foi possível verificar {binary}.')
    return {'ready': not problems, 'problems': problems, 'versions': versions}


async def io_call(function, *args, **kwargs):
    """Uma operação no disco termina antes de propagar cancelamento."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class QueueFull(Exception):
    pass


class DownloadManager:
    def __init__(self, data_dir=None, download_dir=None):
        self.data_dir = Path(data_dir) if data_dir else Path.home() / '.local/share/seletor-musical'
        self.download_dir = Path(download_dir) if download_dir else Path.home() / 'Música/SeletorMusical'
        self.db = self.data_dir / 'history.sqlite3'
        self.lock = asyncio.Lock()
        self.wake = asyncio.Event()
        self.worker = None
        self.active_task = None
        self.active_id = None
        self.cancel_requested = set()
        self.stopping = False
        self.file_lock = None
        self.diagnostics = None
        self.on_completed = None

    def _open(self):
        """Conexão sem transação automática; quem a usa deve chamar commit()."""
        conn = sqlite3.connect(self.db, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    @property
    def covers_dir(self):
        return self.data_dir / 'covers'

    @contextmanager
    def _connect(self):
        conn = self._open()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file_lock = (self.data_dir / 'queue.lock').open('a')
        try:
            fcntl.flock(self.file_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file_lock.close()
            self.file_lock = None
            raise RuntimeError('Outra instância do Seletor Musical já está usando o histórico.')
        with self._connect() as conn:
            migrate(conn)
            conn.execute("UPDATE downloads SET status='interrupted', message='Servidor encerrado. Adicione novamente à fila para tentar de novo.' WHERE status IN ('pending','downloading','converting')")

    async def start(self):
        try:
            await io_call(self._init_db)
            self.diagnostics = await asyncio.to_thread(dependencies)
            self.worker = asyncio.create_task(self._work(), name='download-queue')
        except BaseException:
            if self.file_lock:
                self.file_lock.close()
                self.file_lock = None
            raise

    async def close(self):
        async with self.lock:
            self.stopping = True
            if self.active_task and self.active_id not in self.cancel_requested:
                self.cancel_requested.add(self.active_id)
                self.active_task.cancel()
            self.wake.set()
        try:
            if self.worker:
                await self.worker
            await asyncio.to_thread(self._interrupt_pending)
        finally:
            if self.file_lock:
                self.file_lock.close()
                self.file_lock = None

    def _interrupt_pending(self):
        with self._connect() as conn:
            conn.execute("UPDATE downloads SET status='interrupted', message='Servidor encerrado antes do início.' WHERE status='pending'")

    def _update(self, job_id, **fields):
        # Somente campos internos, nunca nomes de coluna vindos da API.
        with self._connect() as conn:
            conn.execute('UPDATE downloads SET ' + ', '.join(f'{key}=?' for key in fields) +
                         ", updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                         (*fields.values(), job_id))

    async def update(self, job_id, **fields):
        await io_call(self._update, job_id, **fields)

    @staticmethod
    def _valid(path):
        """MP3 legível; sobrescrito nos testes que usam arquivos sintéticos."""
        return is_valid_mp3(path)

    @staticmethod
    def _complete_file(path):
        try:
            return path.is_file() and path.stat().st_size > 0
        except OSError:
            return False

    def _rows(self):
        with self._connect() as conn:
            # Não ocultar itens ativos por causa do limite do histórico.
            rows = [dict(row) for row in conn.execute("""SELECT * FROM downloads
                WHERE status IN ('pending','downloading','converting') OR id IN
                  (SELECT id FROM downloads WHERE status NOT IN ('pending','downloading','converting') ORDER BY rowid DESC LIMIT 200)
                ORDER BY rowid DESC""")]
            for row in rows:
                if row['status'] == 'completed':
                    path = self.download_dir / (row['filename'] or f"{row['video_id']}.mp3")
                    row['file_exists'] = self._complete_file(path)
            return rows

    async def snapshot(self):
        return {'jobs': await asyncio.to_thread(self._rows), 'dependencies': self.diagnostics,
                'download_dir': str(self.download_dir), 'history_limit': 200}

    @staticmethod
    def _cataloged(conn, path):
        try:
            stat = path.stat()
        except OSError:
            return False
        row = conn.execute('SELECT 1 FROM library_tracks WHERE filename=? AND available=1 AND size=? AND mtime_ns=?',
                           (path.name, stat.st_size, stat.st_mtime_ns)).fetchone()
        return row is not None and stat.st_size > 0

    def _existing_valid(self, video_id):
        """Primeiro MP3 legível do vídeo na pasta, ou None (inclui ffprobe: rodar fora do loop)."""
        return next((p for p in find_files(self.download_dir, video_id) if self._complete_file(p) and self._valid(p)), None)

    def _add(self, items):
        accepted, skipped = [], []
        with self._connect() as conn:
            count = conn.execute("SELECT count(*) FROM downloads WHERE status IN ('pending','downloading','converting')").fetchone()[0]
            if count + len(items) > 500:
                raise QueueFull('A fila aceita até 500 itens ativos. Aguarde antes de adicionar mais.')
            for item in items:
                vid = item['video_id']
                existing = conn.execute("SELECT id,status FROM downloads WHERE video_id=? AND status IN ('pending','downloading','converting') LIMIT 1", (vid,)).fetchone()
                if existing:
                    skipped.append({'video_id': vid, 'reason': 'queued'})
                    continue
                # Atalho sem ffprobe: arquivo que o catálogo já validou e que não mudou desde então.
                # Os demais entram na fila e são verificados, um por vez, antes de qualquer download.
                good = next((p for p in find_files(self.download_dir, vid) if self._cataloged(conn, p)), None)
                if good:
                    done = conn.execute("SELECT id FROM downloads WHERE video_id=? AND status='completed' LIMIT 1", (vid,)).fetchone()
                    if not done:
                        conn.execute("INSERT INTO downloads(id,video_id,title,url,status,progress,filename,message) VALUES(?,?,?,?, 'completed',100,?,'Arquivo MP3 já presente na pasta de destino.')",
                                     (uuid.uuid4().hex, vid, item['title'], item['url'], good.name))
                    skipped.append({'video_id': vid, 'reason': 'completed'})
                    continue
                job_id = uuid.uuid4().hex
                conn.execute("INSERT INTO downloads(id,video_id,title,url,channel,status) VALUES(?,?,?,?,?,'pending')",
                             (job_id, vid, item['title'], item['url'], item.get('channel', '')))
                accepted.append(job_id)
        return {'accepted': accepted, 'skipped': skipped}

    async def add(self, items):
        async with self.lock:
            if self.stopping:
                raise RuntimeError('O servidor está encerrando.')
            try:
                return await io_call(self._add, items)
            finally:
                self.wake.set()

    def _get(self, job_id):
        with self._connect() as conn:
            row = conn.execute('SELECT * FROM downloads WHERE id=?', (job_id,)).fetchone()
            return dict(row) if row else None

    async def cancel(self, job_id):
        task = None
        async with self.lock:
            job = await asyncio.to_thread(self._get, job_id)
            if not job:
                return 'missing'
            if job['status'] == 'pending':
                await self.update(job_id, status='cancelled', message='Removido da fila antes do início.')
            elif job_id == self.active_id and job['status'] in ACTIVE:
                if job_id not in self.cancel_requested:
                    self.cancel_requested.add(job_id)
                    self.active_task.cancel()
                task = self.active_task
            else:
                return 'finished'
        if task:
            with suppress(asyncio.CancelledError):
                await asyncio.shield(task)
        return 'cancelled'

    def _next(self):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM downloads WHERE status='pending' ORDER BY rowid LIMIT 1").fetchone()
            return dict(row) if row else None

    async def _work(self):
        while True:
            await self.wake.wait()
            self.wake.clear()
            while True:
                async with self.lock:
                    if self.stopping:
                        return
                    job = await asyncio.to_thread(self._next)
                    if not job:
                        break
                    self.active_id = job['id']
                    await self.update(job['id'], status='downloading', message='Obtendo áudio do YouTube…')
                    self.active_task = asyncio.create_task(self._run(job))
                    task = self.active_task
                try:
                    await task
                except asyncio.CancelledError:
                    # Inclusive se a tarefa foi cancelada antes de executar seu primeiro comando.
                    current = await asyncio.to_thread(self._get, job['id'])
                    if current['status'] != 'completed':
                        await self.update(job['id'], status='interrupted' if self.stopping else 'cancelled',
                                          message='Servidor encerrado.' if self.stopping else 'Download cancelado.')
                except Exception:
                    log.exception('Falha interna da fila para item %s', job['id'])
                    await self.update(job['id'], status='failed', message='Falha interna. Tente adicionar o vídeo novamente.')
                finally:
                    async with self.lock:
                        self.active_id = None
                        self.active_task = None
                        self.cancel_requested.discard(job['id'])

    def _command(self, job, work):
        return [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-cache-dir',
                '--js-runtimes', 'node', '--no-playlist', '--no-simulate', '--no-overwrites',
                '--format', 'bestaudio/best', '--extract-audio', '--audio-format', 'mp3',
                '--audio-quality', '192K', '--write-info-json', '--write-thumbnail', '--convert-thumbnails', 'jpg',
                '--socket-timeout', '15', '--retries', '2',
                '--fragment-retries', '2', '--extractor-retries', '1', '--concurrent-fragments', '1', '--no-colors',
                '--newline', '--progress', '--progress-delta', '0.5',
                '--progress-template', 'download:SM_PROGRESS {"downloaded":%(progress.downloaded_bytes)j,"total":%(progress.total_bytes)j,"estimate":%(progress.total_bytes_estimate)j,"speed":%(progress.speed)j,"eta":%(progress.eta)j}',
                '--progress-template', 'postprocess:SM_CONVERT',
                '--output', str(work / f"{job['video_id']}.%(ext)s"), '--', job['url']]

    async def _progress(self, job_id, raw):
        if raw.startswith(b'SM_PROGRESS '):
            try:
                data = json.loads(raw[len(b'SM_PROGRESS '):])
            except (ValueError, UnicodeError):
                return
            def number(key):
                value = data.get(key)
                return value if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 else None
            downloaded, total = number('downloaded'), number('total') or number('estimate')
            pct = min(100, downloaded / total * 100) if downloaded is not None and total else None
            await self.update(job_id, progress=pct, downloaded=downloaded, total=total,
                              speed=number('speed'), eta=number('eta'), message='Baixando áudio…')
        elif raw.startswith(b'SM_CONVERT'):
            await self.update(job_id, status='converting', progress=None, speed=None, eta=None,
                              message='Convertendo para MP3 com FFmpeg…')

    async def _discard(self, stream):
        while await stream.read(65536):
            pass

    async def _error_tail(self, stream):
        tail = b''
        while chunk := await stream.read(4096):
            tail = (tail + chunk)[-8192:]
        return tail.lower()

    @staticmethod
    def _failure_message(tail):
        # Somente categorias conhecidas saem do subprocesso; nunca a saída bruta.
        if b'not a bot' in tail or b"confirm you" in tail:
            return 'O YouTube solicitou confirmação de que você não é um robô. Esta versão não usa cookies ou login; tente mais tarde. Nenhum MP3 foi concluído.'
        if any(text in tail for text in (b'private video', b'video unavailable', b'not available', b'has been removed')):
            return 'Vídeo privado, removido ou indisponível nesta região. Nenhum MP3 foi concluído.'
        if b'no space left' in tail:
            return 'Sem espaço livre para concluir o MP3. Libere espaço e tente novamente.'
        if b'age' in tail and b'sign in' in tail:
            return 'O vídeo exige confirmação de idade. Esta versão não usa cookies ou login.'
        if b'postprocessing' in tail or b'ffmpeg' in tail:
            return 'Falha ao converter para MP3. Verifique FFmpeg e espaço livre; depois tente novamente.'
        return 'Não foi possível baixar. Verifique conexão e disponibilidade do vídeo, atualize o yt-dlp e tente novamente.'

    async def _consume(self, proc, job_id):
        while line := await proc.stdout.readline():
            await self._progress(job_id, line.strip())
        return await proc.wait()

    def _tag_source(self, job, work, source):
        """Tags ID3 e capa no MP3 ainda privado; falhas aqui nunca impedem a publicação."""
        try:
            metadata.apply(self._connect, self.covers_dir, job['video_id'], work, source,
                           job.get('title', ''), job.get('channel', ''))
        except Exception as error:
            log.warning('Metadados não gravados para %s: %s', job['video_id'], type(error).__name__)

    def _publish(self, job, work):
        source = work / f"{job['video_id']}.mp3"
        if not source.is_file() or source.stat().st_size == 0:
            return False
        existing = find_files(self.download_dir, job['video_id'])
        keep = next((p for p in existing if self._complete_file(p) and self._valid(p)), None)
        if keep:
            # Um MP3 legível nunca é substituído.
            target = keep
        else:
            target = self.download_dir / final_name(job['video_id'], job.get('title', ''))
            self._tag_source(job, work, source)
            # Somente arquivos já reprovados na validação são trocados.
            os.replace(source, target)
            for stale in existing:
                if stale != target:
                    with suppress(OSError):
                        stale.unlink()
        self._update(job['id'], status='completed', progress=100, speed=None, eta=None,
                     filename=target.name, message='MP3 concluído.')
        if self.on_completed:
            try:
                self.on_completed()
            except Exception:
                log.warning('MP3 concluído; catálogo será atualizado na próxima sincronização.')
        return True

    async def _run(self, job):
        work = self.download_dir / '.partial' / job['id']
        proc = None
        spawn = None
        errors = None
        try:
            if await asyncio.to_thread(find_files, self.download_dir, job['video_id']):
                await self.update(job['id'], message='Verificando arquivo já existente…')
                keep = await io_call(self._existing_valid, job['video_id'])
                if keep:
                    # Já baixado e legível: apenas registra; arquivos danificados seguem para novo download.
                    await self.update(job['id'], status='completed', progress=100, filename=keep.name,
                                      message='MP3 já presente e legível; download não necessário.')
                    if self.on_completed:
                        with suppress(Exception):
                            self.on_completed()
                    return
                await self.update(job['id'], message='Arquivo existente danificado; baixando novamente…')
            await io_call(work.mkdir, parents=True, exist_ok=True)
            # Shield evita perder o processo se cancelarem durante sua criação.
            spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                *self._command(job, work), stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, start_new_session=True))
            proc = await asyncio.shield(spawn)
            errors = asyncio.create_task(self._error_tail(proc.stderr))
            code = await asyncio.wait_for(self._consume(proc, job['id']), 7200)
            if code == 0:
                # Publicação e histórico completam juntos mesmo se chegar cancelamento nesse instante.
                publish = asyncio.create_task(asyncio.to_thread(self._publish, job, work))
                try:
                    completed = await asyncio.shield(publish)
                except asyncio.CancelledError:
                    completed = await publish
                    if not completed:
                        raise
                if completed:
                    return
            tail = await errors
            log.warning('Download %s falhou (código %s)', job['id'], code)
            await self.update(job['id'], status='failed', message=self._failure_message(tail))
        except asyncio.TimeoutError:
            await self.update(job['id'], status='failed', message='Tempo máximo de 2 horas excedido.')
        finally:
            try:
                if proc is None and spawn:
                    proc = await spawn
                if proc:
                    drain = asyncio.create_task(self._discard(proc.stdout))
                    if errors is None:
                        errors = asyncio.create_task(self._error_tail(proc.stderr))
                    await terminate(proc)
                    await drain
                if errors:
                    await errors
            finally:
                # Somente a pasta temporária exclusiva deste item; MP3s finais são preservados.
                await io_call(shutil.rmtree, work, True)
