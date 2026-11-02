"""Artista e faixa a partir do título "Artista - Título" (padrão do YouTube) ou do canal.

Vídeos oficiais quase nunca trazem `artist`/`album` no yt-dlp; por isso inferimos e
registramos a origem (`source`) para que dados melhores possam substituir os inferidos.
"""
import re

NOISE_WORDS = re.compile(r'official|lyric|video|audio|visuali[sz]er|\bhd\b|\b4k\b|clip|m/v|\bmv\b', re.I)
BRACKETS = re.compile(r'\s*[\(\[]([^\(\)\[\]]*)[\)\]]')
FEATURING = re.compile(r'\s*[\(\[]?\s*\b(?:ft\.?|feat\.?|featuring)\s+([^\(\)\[\]]+?)\s*[\)\]]?\s*$', re.I)
DASH = re.compile(r'^(?P<artist>.+?)\s+[-–—]\s+(?P<track>.+)$')
PRIMARY_SPLIT = re.compile(r'\s*[,;]\s*|\s+(?:ft\.?|feat\.?|featuring)\s+|\s+x\s+', re.I)
CHANNEL_NOISE = re.compile(r'\s*(?:-\s*topic|vevo|official(?:\s+channel)?)\s*$', re.I)


def clean_track(track):
    """Remove (Official Video), [Lyric Video] etc.; mantém (Remix), (Ao Vivo)…"""
    def keep(match):
        return '' if NOISE_WORDS.search(match.group(1)) else match.group(0)
    return re.sub(r'\s{2,}', ' ', BRACKETS.sub(keep, track)).strip(' -–—')


def primary(artist):
    return PRIMARY_SPLIT.split(artist.strip(), maxsplit=1)[0].strip()


def infer(title, channel='', artist='', source=''):
    """Retorna {artist, artist_primary, track, source}; artist vazio se nada confiável."""
    title = (title or '').strip()
    artist = (artist or '').strip()
    track = title
    if artist:
        # Remove "Artista - " do começo do título se repetir o artista conhecido.
        match = DASH.match(title)
        if match and match['artist'].strip().casefold() == artist.casefold():
            track = match['track']
    else:
        match = DASH.match(title)
        if match:
            artist, track, source = match['artist'].strip(), match['track'].strip(), 'title'
        else:
            name = CHANNEL_NOISE.sub('', channel or '').strip()
            if name:
                artist, source = name, 'channel'
    track = clean_track(track)
    featured = FEATURING.search(track)
    if featured and artist:
        track = track[:featured.start()].strip(' -–—') or track
        if featured[1].strip().casefold() not in artist.casefold():
            artist = f'{artist} ft. {featured[1].strip()}'
    return {'artist': artist, 'artist_primary': primary(artist) if artist else '',
            'track': track or title, 'source': source if artist else ''}
