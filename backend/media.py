"""Nomes de arquivo seguros e validação de MP3 na pasta de músicas."""
import json
import math
from pathlib import Path
import re
import subprocess
import unicodedata

VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}')


def slugify(title, limit=80):
    """ASCII simples: sem acentos, espaços, aspas, parênteses ou símbolos de shell."""
    folded = unicodedata.normalize('NFKD', title or '').encode('ascii', 'ignore').decode()
    slug = re.sub(r'[^A-Za-z0-9]+', '-', re.sub(r"['’`]", '', folded)).strip('-')[:limit].strip('-')
    return slug or 'musica'


def final_name(video_id, title=''):
    return f'{slugify(title)}_{video_id}.mp3'


def video_id_from_stem(stem):
    """Aceita `ID` (formato antigo) e `titulo_ID`."""
    if VIDEO_ID.fullmatch(stem):
        return stem
    if len(stem) > 12 and stem[-12] == '_' and VIDEO_ID.fullmatch(stem[-11:]):
        return stem[-11:]
    return None


def display_title(stem):
    """Título legível para arquivos sem histórico nem tags."""
    video_id = video_id_from_stem(stem)
    if video_id and video_id != stem:
        return stem[:-12].replace('-', ' ')
    return stem


def find_files(root, video_id):
    """MP3s diretos da pasta para o vídeo; ignora symlinks e subpastas."""
    found = []
    for path in sorted(Path(root).glob(f'*{video_id}.mp3')):
        if video_id_from_stem(path.stem) == video_id and path.is_file() and not path.is_symlink():
            found.append(path)
    return found


def probe_mp3(path):
    """Retorna (duração, tags); levanta exceção se o arquivo não for MP3 legível."""
    result = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                             '-show_entries', 'format=duration:format_tags=title,artist,album:stream=codec_name,codec_type',
                             '-of', 'json', str(path)], stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, timeout=8, check=True)
    data = json.loads(result.stdout)
    if not any(s.get('codec_type') == 'audio' and s.get('codec_name') == 'mp3' for s in data.get('streams', [])):
        raise ValueError('Not MP3 audio')
    fmt = data.get('format', {})
    duration = float(fmt.get('duration', 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid duration')
    tags = {k.lower(): v for k, v in fmt.get('tags', {}).items() if isinstance(v, str)}
    return duration, tags


def is_valid_mp3(path):
    try:
        probe_mp3(path)
        return True
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return False
