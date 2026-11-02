"""Tags ID3v2.3 e capa dentro do MP3 (leitores automotivos), sem tocar no áudio."""
import hashlib
import logging
import os
from pathlib import Path
import shutil
import subprocess

from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TDRC, TIT2, TPE1, TXXX

from .media import probe_mp3

log = logging.getLogger('seletor.tagging')
YOUTUBE_ID_DESC = 'YouTube ID'


def make_cover(source, target):
    """JPEG quadrado 500x500 recortado do centro (miniaturas do YouTube são 16:9)."""
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-vf', 'crop=ih:ih,scale=500:500',
                    '-frames:v', '1', '-q:v', '3', '-pix_fmt', 'yuvj420p', str(target)],
                   stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=True)
    data = Path(target).read_bytes()
    if not data.startswith(b'\xff\xd8') or len(data) > 1_000_000:
        raise ValueError('Capa inválida')
    return data


def audio_md5(path):
    """MD5 apenas dos pacotes de áudio: cabeçalhos ID3 não entram."""
    result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a', '-c', 'copy', '-f', 'md5', '-'],
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120, check=True)
    line = result.stdout.strip()
    if not line.startswith('MD5='):
        raise ValueError('Não foi possível calcular o MD5 do áudio')
    return line


def _encoding(*texts):
    # Latin-1 é o mais compatível; UTF-16 só quando necessário.
    for text in texts:
        try:
            text.encode('latin-1')
        except UnicodeEncodeError:
            return 1
    return 0


def write_tags(path, meta, cover=None):
    """Grava title/artist/album/year/YouTube ID e capa frontal em ID3v2.3."""
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    for key in ('TIT2', 'TPE1', 'TALB', 'TDRC', 'TYER', 'APIC', f'TXXX:{YOUTUBE_ID_DESC}'):
        tags.delall(key)
    texts = [meta.get(k, '') for k in ('title', 'artist', 'album', 'year', 'youtube_id')]
    enc = _encoding(*texts)
    if meta.get('title'):
        tags.add(TIT2(encoding=enc, text=meta['title']))
    if meta.get('artist'):
        tags.add(TPE1(encoding=enc, text=meta['artist']))
    if meta.get('album'):
        tags.add(TALB(encoding=enc, text=meta['album']))
    if meta.get('year'):
        tags.add(TDRC(encoding=enc, text=meta['year']))
    if meta.get('youtube_id'):
        tags.add(TXXX(encoding=enc, desc=YOUTUBE_ID_DESC, text=meta['youtube_id']))
    if cover:
        tags.add(APIC(encoding=0, mime='image/jpeg', type=3, desc='Capa', data=cover))
    tags.update_to_v23()  # TDRC (v2.4) -> TYER; sem isso leitores v2.3 não veem o ano
    tags.save(path, v2_version=3)


def tag_file(path, meta, cover, workdir):
    """Regrava as tags com verificação: duração e MD5 do áudio iguais; troca atômica ou nada.

    Retorna True se o arquivo foi atualizado; em qualquer falha o original permanece intocado.
    """
    path = Path(path)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    temp = workdir / f'tag-{hashlib.sha1(str(path).encode()).hexdigest()[:12]}.mp3'
    try:
        before_duration, _ = probe_mp3(path)
        before_md5 = audio_md5(path)
        shutil.copyfile(path, temp)
        write_tags(temp, meta, cover)
        after_duration, _ = probe_mp3(temp)
        if abs(after_duration - before_duration) > 0.5 or audio_md5(temp) != before_md5:
            raise ValueError('O áudio mudou após gravar as tags')
        os.replace(temp, path)
        return True
    except Exception as error:
        log.warning('Tags não gravadas em %s: %s', path.name, type(error).__name__)
        return False
    finally:
        temp.unlink(missing_ok=True)
