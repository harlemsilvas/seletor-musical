import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit, urlencode

from fastapi import FastAPI, HTTPException, Request, Query as QueryParam
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from .downloads import DownloadManager, QueueFull
from .processes import terminate
from .library import Library
from .enrich import Enricher


@asynccontextmanager
async def lifespan(app):
    manager = DownloadManager()
    await manager.start()
    app.state.downloads = manager
    library = Library(manager)
    app.state.library = library
    enricher = Enricher(manager, library)
    app.state.enrich = enricher
    try:
        await library.start()
        manager.on_completed = library.request_refresh
        yield
    finally:
        await enricher.close()
        await library.close()
        await manager.close()


app = FastAPI(title='Seletor Musical', lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1'])
log = logging.getLogger('seletor')
LIMIT = max(1, min(200, int(os.getenv('SELETOR_MAX_ITEMS', '50'))))
semaphore = asyncio.Semaphore(1)
ORIGINS = {'http://localhost:8766', 'http://127.0.0.1:8766'}

@app.middleware('http')
async def protect(request: Request, call_next):
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        if request.headers.get('origin') not in ORIGINS or request.headers.get('x-seletor-client') != '1':
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail': 'Origem não permitida.'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' https://i.ytimg.com https://img.youtube.com; style-src 'self'; connect-src 'self'; media-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response


def youtube_url(raw: str) -> str:
    try:
        u = urlsplit(raw.strip())
        if u.scheme not in {'https', 'http'} or u.username or u.password or u.port not in {None, 80, 443}:
            raise ValueError()
        if u.hostname not in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be'}:
            raise ValueError()
        q = parse_qs(u.query)
        video = None
        if u.hostname == 'youtu.be':
            video = u.path.strip('/')
        elif u.path == '/watch':
            video = q.get('v', [''])[0]
        elif re.fullmatch(r'/(shorts|embed|live)/[^/]+', u.path):
            video = u.path.split('/')[-1]
        elif u.path != '/playlist':
            raise ValueError()
        playlist = q.get('list', [None])[0]
        if video is not None and not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
            raise ValueError()
        if playlist and not re.fullmatch(r'[A-Za-z0-9_-]{2,150}', playlist):
            raise ValueError()
        if not video and not playlist:
            raise ValueError()
        params = ({'v': video} if video else {}) | ({'list': playlist} if playlist else {})
        return 'https://www.youtube.com/' + ('watch' if video else 'playlist') + '?' + urlencode(params)
    except ValueError:
        raise HTTPException(422, 'Informe uma URL válida de vídeo, playlist ou Mix do YouTube.')

class Query(BaseModel):
    url: str = Field(max_length=2048)
    limit: int = Field(default=LIMIT, ge=1, le=LIMIT)

async def extract(url, limit):
    args = [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-cache-dir',
            '--js-runtimes', 'node', '--flat-playlist', '--skip-download', '--yes-playlist',
            '--playlist-end', str(limit), '--socket-timeout', '15', '--retries', '1',
            '--dump-single-json', '--', url]
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                               stderr=asyncio.subprocess.PIPE, start_new_session=True)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), 90)
        if proc.returncode:
            log.warning('Consulta yt-dlp falhou: código %s', proc.returncode)
            if b'not a bot' in err.lower() or b'confirm you' in err.lower():
                raise HTTPException(502, {'code': 'youtube_verification', 'message': 'O YouTube solicitou uma verificação no navegador.', 'url': url})
            raise HTTPException(502, 'YouTube não respondeu à consulta. Verifique a URL, a conexão e atualize o yt-dlp. Conteúdo privado ou restrito pode não estar disponível.')
        try:
            return json.loads(out)
        except (ValueError, UnicodeError):
            raise HTTPException(502, 'O yt-dlp retornou metadados inválidos.')
    except asyncio.TimeoutError:
        raise HTTPException(504, 'A consulta excedeu 90 segundos. Tente uma lista menor.')
    finally:
        await terminate(proc)

@app.get('/api/config')
async def config():
    return {'max_items': LIMIT}

@app.post('/api/query')
async def query(body: Query):
    url = youtube_url(body.url)
    if semaphore.locked():
        raise HTTPException(429, 'Já há uma consulta em andamento. Aguarde e tente novamente.')
    async with semaphore:
        data = await extract(url, body.limit)
    items = []
    seen = set()
    for item in (data.get('entries') or [data]):
        if not isinstance(item, dict):
            continue
        vid = item.get('id', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid) or vid in seen:
            continue
        seen.add(vid)
        thumbnail = item.get('thumbnail') or next((t.get('url') for t in reversed(item.get('thumbnails') or []) if t.get('url')), None)
        items.append({'id': vid, 'title': item.get('title') or f'Vídeo {vid}',
                      'channel': item.get('channel') or item.get('uploader') or '',
                      'duration': item.get('duration'), 'thumbnail': thumbnail,
                      'url': f'https://www.youtube.com/watch?v={vid}'})
        if len(items) >= body.limit:
            break
    return {'items': items, 'limit': body.limit}

class DownloadItem(BaseModel):
    model_config = {'extra': 'forbid'}
    url: str = Field(max_length=2048)
    title: str = Field(default='', max_length=500)
    channel: str = Field(default='', max_length=500)


class DownloadBatch(BaseModel):
    model_config = {'extra': 'forbid'}
    items: list[DownloadItem] = Field(min_length=1, max_length=200)


def downloads(request: Request):
    manager = getattr(request.app.state, 'downloads', None)
    if manager is None:
        raise HTTPException(503, 'Fila não inicializada. Reinicie o servidor.')
    return manager


def enricher(request: Request):
    value = getattr(request.app.state, 'enrich', None)
    if value is None:
        raise HTTPException(503, 'Enriquecimento não inicializado. Reinicie o servidor.')
    return value


@app.get('/api/downloads')
async def download_status(request: Request):
    return await downloads(request).snapshot()


@app.post('/api/downloads', status_code=202)
async def enqueue(body: DownloadBatch, request: Request):
    manager = downloads(request)
    items = []
    for item in body.items:
        canonical = youtube_url(item.url)
        video_id = parse_qs(urlsplit(canonical).query).get('v', [None])[0]
        if not video_id:
            raise HTTPException(422, 'Selecione vídeos individuais para baixar; playlists não são aceitas na fila.')
        items.append({'video_id': video_id, 'url': f'https://www.youtube.com/watch?v={video_id}',
                      'title': item.title.strip() or f'Vídeo {video_id}', 'channel': item.channel.strip()})
    # Checagem novamente permite corrigir PATH/dependências sem recriar a fila.
    from .downloads import dependencies
    manager.diagnostics = await asyncio.to_thread(dependencies)
    if not manager.diagnostics['ready']:
        raise HTTPException(503, ' '.join(manager.diagnostics['problems']))
    try:
        return await manager.add(items)
    except QueueFull as error:
        raise HTTPException(409, str(error))
    except RuntimeError as error:
        raise HTTPException(503, str(error))


@app.post('/api/downloads/{job_id}/cancel')
async def cancel_download(job_id: str, request: Request):
    if not re.fullmatch(r'[a-f0-9]{32}', job_id):
        raise HTTPException(404, 'Item não encontrado.')
    result = await downloads(request).cancel(job_id)
    if result == 'missing':
        raise HTTPException(404, 'Item não encontrado.')
    if result == 'finished':
        raise HTTPException(409, 'O item já terminou; arquivos concluídos foram preservados.')
    return {'status': result}


@app.get('/api/library')
async def library_list(request: Request, search: str = QueryParam('', max_length=200),
                       sort: str = QueryParam('newest', pattern='^(newest|title|artist)$'),
                       artist: str = QueryParam('', max_length=200),
                       offset: int = QueryParam(0, ge=0), limit: int = QueryParam(50, ge=1, le=100)):
    result = await asyncio.to_thread(request.app.state.library.listing, search, sort, offset, limit, artist)
    enricher = getattr(request.app.state, 'enrich', None)
    result['enrich'] = dict(enricher.state) if enricher else {'running': False, 'done': 0, 'total': 0, 'failed': 0, 'error': ''}
    return result


@app.post('/api/library/enrich', status_code=202)
async def library_enrich(request: Request):
    manager = downloads(request)
    if not (manager.diagnostics or {}).get('ready'):
        raise HTTPException(503, 'Dependências ausentes: ' + ' '.join((manager.diagnostics or {}).get('problems', [])))
    started = enricher(request).start()
    return {'status': 'started' if started else 'running'}


@app.post('/api/library/enrich/cancel')
async def library_enrich_cancel(request: Request):
    await enricher(request).cancel()
    return {'status': 'cancelled'}


@app.get('/api/library/artists')
async def library_artists(request: Request):
    return {'artists': await asyncio.to_thread(request.app.state.library.artist_list)}


@app.post('/api/library/sync', status_code=202)
async def library_sync(request: Request):
    request.app.state.library.request_refresh()
    return {'status': 'scheduled'}


def local_request_only(request: Request):
    # <audio>/<img> same-origin não enviam Origin nem exigem Sec-Fetch-Site; só recusamos origens declaradas e cross-site.
    origin = request.headers.get('origin')
    if (origin and origin not in ORIGINS) or request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Origem não permitida.')


@app.api_route('/api/library/{track_id}/audio', methods=['GET', 'HEAD'])
async def library_audio(track_id: str, request: Request):
    local_request_only(request)
    if not re.fullmatch(r'[a-f0-9]{32}', track_id):
        raise HTTPException(404, 'Faixa não encontrada.')
    path = await asyncio.to_thread(request.app.state.library.audio_file, track_id)
    if path is None:
        raise HTTPException(404, 'Arquivo ausente ou indisponível. Atualize a biblioteca.')
    return FileResponse(path, media_type='audio/mpeg', headers={'Cross-Origin-Resource-Policy': 'same-origin'})


@app.get('/api/library/{track_id}/cover')
async def library_cover(track_id: str, request: Request):
    local_request_only(request)
    if not re.fullmatch(r'[a-f0-9]{32}', track_id):
        raise HTTPException(404, 'Capa não encontrada.')
    path = await asyncio.to_thread(request.app.state.library.cover_file, track_id)
    if path is None:
        raise HTTPException(404, 'Capa não encontrada.')
    return FileResponse(path, media_type='image/jpeg', headers={'Cross-Origin-Resource-Policy': 'same-origin', 'Cache-Control': 'private, max-age=3600'})


DIST = Path(__file__).resolve().parent.parent / 'frontend' / 'dist'
if DIST.is_dir():
    app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')

@app.get('/')
async def index():
    if not (DIST / 'index.html').exists():
        raise HTTPException(503, 'Compile o frontend: cd frontend && npm ci && npm run build')
    return FileResponse(DIST / 'index.html')
