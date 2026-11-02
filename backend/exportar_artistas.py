"""Copia para um destino externo (ex.: /mnt/midia) as músicas de artistas com várias faixas.

Uso:
    .venv/bin/python -m backend.exportar_artistas                  # simula
    .venv/bin/python -m backend.exportar_artistas --apply          # copia
    .venv/bin/python -m backend.exportar_artistas --minimo 5 --destino /mnt/midia --pasta Favoritos --apply

Copia apenas MP3s disponíveis do catálogo de artistas com pelo menos --minimo faixas (padrão 3,
ou seja, mais de 2), em DESTINO/PASTA/<Artista>/. Os originais não são alterados e arquivos
já copiados não são sobrescritos. O destino precisa existir (ponto de montagem não é criado).
"""
import argparse
from pathlib import Path
import os
import shutil
import sys

from .downloads import DownloadManager
from .media import slugify


def plan(manager, minimo):
    """Lista (artista, pasta, [arquivos]) dos artistas com pelo menos `minimo` faixas disponíveis."""
    groups = {}
    with manager._connect() as conn:
        for row in conn.execute("SELECT filename,artist_primary FROM library_tracks WHERE available=1 AND artist_primary!='' ORDER BY filename"):
            path = manager.download_dir / row['filename']
            if path.is_symlink() or not path.is_file():
                continue
            entry = groups.setdefault(row['artist_primary'].casefold(), [row['artist_primary'], []])
            entry[1].append(path)
    result = [(name, slugify(name), files) for name, files in groups.values() if len(files) >= minimo]
    return sorted(result, key=lambda item: item[1].casefold())


def copy(files, folder):
    """Copia sem sobrescrever; devolve (copiados, existentes)."""
    folder.mkdir(parents=True, exist_ok=True)
    copied = existing = 0
    for source in files:
        target = folder / source.name
        if target.exists():
            existing += 1
            continue
        temp = folder / f'.{source.name}.partial'
        try:
            shutil.copyfile(source, temp)
            os.replace(temp, target)
            copied += 1
        finally:
            temp.unlink(missing_ok=True)
    return copied, existing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--destino', default='/mnt/midia', help='pasta de destino já existente (padrão: /mnt/midia)')
    parser.add_argument('--pasta', default='SeletorMusical', help='subpasta separada dentro do destino (padrão: SeletorMusical)')
    parser.add_argument('--minimo', type=int, default=3, help='mínimo de faixas por artista (padrão: 3, isto é, mais de 2)')
    parser.add_argument('--apply', action='store_true', help='copia de fato; sem isso apenas simula')
    args = parser.parse_args(argv)
    if args.minimo < 1 or Path(args.pasta).name != args.pasta or args.pasta in ('', '.', '..'):
        sys.exit('Opções inválidas: --minimo >= 1 e --pasta deve ser um nome simples.')
    destino = Path(args.destino)
    if not destino.is_dir():
        sys.exit(f'Destino não encontrado: {destino}. Monte o dispositivo antes.')
    manager = DownloadManager()
    steps = plan(manager, args.minimo)
    total = sum(len(files) for _, _, files in steps)
    print(f'{len(steps)} artistas com {args.minimo}+ faixas, {total} arquivos -> {destino / args.pasta}')
    for name, slug, files in steps:
        if not args.apply:
            print(f'  {slug}/  ({name}: {len(files)} faixas)')
            continue
        copied, existing = copy(files, destino / args.pasta / slug)
        print(f'  {slug}/  {copied} copiadas, {existing} já existiam')
    if not args.apply:
        print('Simulação. Use --apply para copiar.')


if __name__ == '__main__':
    main()
