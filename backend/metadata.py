"""Metadados do yt-dlp (info.json), capas locais e tabela video_meta."""
import json
from pathlib import Path
import re
import shutil

from . import artist as artists, tagging

MAX_INFO = 20 * 1024 * 1024
CONTROL = re.compile(r'[\x00-\x1f\x7f]')


def clean(value, limit=300):
    return CONTROL.sub(' ', value).strip()[:limit] if isinstance(value, str) else ''


def read_info(path):
    """Lista branca de campos do .info.json; None se ausente, grande demais ou inválido."""
    path = Path(path)
    try:
        if not path.is_file() or path.stat().st_size > MAX_INFO:
            return None
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    performers = data.get('artists')
    credit = ', '.join(clean(a, 100) for a in performers if isinstance(a, str)) if isinstance(performers, list) else ''
    return {'title': clean(data.get('title')), 'channel': clean(data.get('channel') or data.get('uploader')),
            'artist': credit or clean(data.get('artist')), 'track': clean(data.get('track')),
            'album': clean(data.get('album')),
            'release_date': clean(str(data.get('release_date') or data.get('release_year') or ''), 8),
            'upload_date': clean(str(data.get('upload_date') or ''), 8)}


def build_meta(video_id, info, fallback_title='', fallback_channel=''):
    """Metadados finais: campo `artist` do YouTube tem prioridade; senão, inferência pelo título."""
    title = info.get('title') or fallback_title
    guess = artists.infer(title, info.get('channel') or fallback_channel, info.get('artist', ''),
                          'youtube' if info.get('artist') else '')
    track = info.get('track') or guess['track']
    year = (info.get('release_date') or info.get('upload_date') or '')[:4]
    return {'video_id': video_id, 'artist': guess['artist'], 'artist_primary': guess['artist_primary'],
            'track': track, 'album': info.get('album', ''), 'release_date': info.get('release_date', ''),
            'upload_date': info.get('upload_date', ''), 'source': guess['source'] or 'youtube', 'year': year,
            'title': title}


def tag_values(meta):
    return {'title': meta['track'] or meta['title'], 'artist': meta['artist'], 'album': meta['album'],
            'year': meta['year'], 'youtube_id': meta['video_id']}


def cover_path(covers_dir, video_id):
    return Path(covers_dir) / f'{video_id}.jpg'


def store_cover(source, covers_dir, video_id):
    """Guarda a miniatura (JPEG) em dados do app, fora da pasta de músicas."""
    source = Path(source)
    if not source.is_file() or source.stat().st_size > 5_000_000 or not source.read_bytes()[:2] == b'\xff\xd8':
        return False
    Path(covers_dir).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, cover_path(covers_dir, video_id))
    return True


def save_meta(conn, meta, has_cover):
    conn.execute('''INSERT INTO video_meta(video_id,artist,artist_primary,track,album,release_date,upload_date,source,has_cover)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(video_id) DO UPDATE SET artist=excluded.artist,
        artist_primary=excluded.artist_primary,track=excluded.track,album=excluded.album,
        release_date=excluded.release_date,upload_date=excluded.upload_date,source=excluded.source,
        has_cover=excluded.has_cover,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')''',
                 (meta['video_id'], meta['artist'], meta['artist_primary'], meta['track'], meta['album'],
                  meta['release_date'], meta['upload_date'], meta['source'], int(has_cover)))


def apply(connect, covers_dir, video_id, work, target, fallback_title='', fallback_channel=''):
    """Lê o info.json/miniatura de `work`, grava tags+capa em `target` e registra video_meta.

    Retorna (meta, gravou_tags) ou None se não houver info.json válido. `connect` abre o SQLite.
    """
    work = Path(work)
    info = read_info(work / f'{video_id}.info.json')
    if info is None:
        return None
    meta = build_meta(video_id, info, fallback_title, fallback_channel)
    cover, has_cover = None, False
    thumb = work / f'{video_id}.jpg'
    if thumb.is_file():
        try:
            cover = tagging.make_cover(thumb, work / 'cover-square.jpg')
            has_cover = store_cover(thumb, covers_dir, video_id)
        except Exception as error:
            tagging.log.warning('Capa não processada para %s: %s', video_id, type(error).__name__)
    tagged = tagging.tag_file(target, tag_values(meta), cover, work)
    with connect() as conn:
        save_meta(conn, meta, has_cover)
    return meta, tagged
