"""Renomeia MP3s no formato antigo (`ID.mp3`) para `titulo_ID.mp3` e importa pastas externas.

Uso, com o servidor parado:
    .venv/bin/python -m backend.rename_legacy                          # plano de renomeação
    .venv/bin/python -m backend.rename_legacy --apply                  # renomeia
    .venv/bin/python -m backend.rename_legacy --origem PASTA           # plano de importação
    .venv/bin/python -m backend.rename_legacy --origem PASTA --apply   # copia (use --mover para mover)

A importação lê arquivos `Título [ID].mp3` diretamente da PASTA. O nome anterior fica em
library_tracks.original_filename. Nunca sobrescreve arquivos.
"""
import argparse
from pathlib import Path
import os
import re
import shutil
import sys

from .downloads import DownloadManager
from .library import Library
from .media import VIDEO_ID, final_name, find_files, is_valid_mp3


def plan(manager):
    """Lista (antigo, novo, título) para arquivos `ID.mp3` com título conhecido."""
    with manager._connect() as conn:
        titles = {}
        for row in conn.execute("SELECT video_id,title FROM downloads WHERE status='completed' ORDER BY rowid DESC"):
            titles.setdefault(row['video_id'], row['title'])
        for row in conn.execute("SELECT video_id,title,original_title FROM library_tracks WHERE video_id IS NOT NULL"):
            titles.setdefault(row['video_id'], row['original_title'] or row['title'])
    result = []
    for path in sorted(manager.download_dir.glob('*.mp3')):
        if not VIDEO_ID.fullmatch(path.stem) or path.is_symlink() or not path.is_file():
            continue
        title = titles.get(path.stem, '')
        # Sem título conhecido (nem tags/histórico) o nome ficaria sem informação: mantém como está.
        if not title or title == path.stem or title == f'Vídeo {path.stem}':
            continue
        result.append((path, manager.download_dir / final_name(path.stem, title), title))
    return result


def apply(manager, steps):
    done = []
    for old, new, _ in steps:
        if new.exists():
            continue
        # link() falha se o destino existir; assim nada é sobrescrito.
        try:
            os.link(old, new)
        except OSError:
            continue
        with manager._connect() as conn:
            conn.execute('UPDATE library_tracks SET filename=?,original_filename=? WHERE filename=?', (new.name, old.name, old.name))
            conn.execute('UPDATE downloads SET filename=? WHERE filename=?', (new.name, old.name))
        old.unlink()
        done.append((old, new))
    return done


BRACKET_ID = re.compile(r'^(?P<title>.*?)\s*\[(?P<id>[A-Za-z0-9_-]{11})\]$')


def import_plan(manager, source):
    """Retorna (passos, ignorados): passos = (arquivo, destino, título, id); ignorados = (nome, motivo)."""
    steps, skipped, seen = [], [], set()
    for path in sorted(Path(source).glob('*.mp3')):
        if path.is_symlink() or not path.is_file():
            skipped.append((path.name, 'não é um arquivo comum'))
            continue
        match = BRACKET_ID.match(path.stem)
        vid = match['id'] if match else (path.stem if VIDEO_ID.fullmatch(path.stem) else None)
        if not vid:
            skipped.append((path.name, 'sem ID de vídeo no nome (formato "Título [ID].mp3")'))
        elif vid in seen:
            skipped.append((path.name, 'ID repetido na pasta de origem'))
        elif find_files(manager.download_dir, vid):
            skipped.append((path.name, 'vídeo já existe na pasta do app'))
        elif not is_valid_mp3(path):
            skipped.append((path.name, 'MP3 ilegível ou danificado'))
        else:
            title = (match['title'] if match else '').strip()
            seen.add(vid)
            steps.append((path, manager.download_dir / final_name(vid, title), title, vid))
    return steps, skipped


def import_files(manager, steps, move=False):
    manager.download_dir.mkdir(parents=True, exist_ok=True)
    temp = manager.download_dir / '.partial'
    temp.mkdir(exist_ok=True)
    done = []
    for source, target, title, vid in steps:
        if target.exists():
            continue
        staging = temp / f'import-{vid}.mp3'
        try:
            shutil.copy2(source, staging)
            if staging.stat().st_size != source.stat().st_size:
                continue
            os.link(staging, target)  # falha se o destino existir; nunca sobrescreve
        except OSError:
            continue
        finally:
            staging.unlink(missing_ok=True)
        if move:
            source.unlink()
        done.append((source, target, title))
    return done


def record_import(manager, done):
    with manager._connect() as conn:
        for source, target, title in done:
            conn.execute("UPDATE library_tracks SET original_filename=?, original_title=?, title=CASE WHEN ?!='' THEN ? ELSE title END WHERE filename=?",
                         (source.name, title, title, title, target.name))


def run_import(manager, library, args):
    if not args.origem.is_dir():
        print(f'Pasta de origem não encontrada: {args.origem}', file=sys.stderr)
        return 1
    if args.origem.resolve() == manager.download_dir.resolve():
        print('A origem é a própria pasta do app; use o modo sem --origem.', file=sys.stderr)
        return 1
    steps, skipped = import_plan(manager, args.origem)
    for source, target, _, _ in steps:
        print(f'{source.name} -> {target.name}')
    for name, reason in skipped:
        print(f'IGNORADO {name}: {reason}')
    if not steps:
        print('Nada para importar.')
    elif args.apply:
        done = import_files(manager, steps, args.mover)
        library.scan()
        record_import(manager, done)
        print(f'{len(done)} arquivo(s) {"movido(s)" if args.mover else "copiado(s)"} para {manager.download_dir}.')
    else:
        print(f'{len(steps)} arquivo(s) seriam importados, {len(skipped)} ignorado(s). Use --apply para executar.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--apply', action='store_true', help='executa (padrão: apenas simula)')
    parser.add_argument('--origem', type=Path, help='pasta com MP3s "Título [ID].mp3" a importar')
    parser.add_argument('--mover', action='store_true', help='com --origem: move em vez de copiar')
    args = parser.parse_args(argv)
    manager = DownloadManager()
    try:
        manager._init_db()
    except RuntimeError as error:
        print(f'{error} Pare o servidor antes de renomear.', file=sys.stderr)
        return 1
    try:
        library = Library(manager)
        library.initialize()
        if args.origem:
            return run_import(manager, library, args)
        library.scan()  # garante uma linha no catálogo para registrar o nome original
        steps = plan(manager)
        for old, new, _ in steps:
            print(f'{old.name} -> {new.name}')
        if not steps:
            print('Nada para renomear.')
        elif args.apply:
            done = apply(manager, steps)
            library.scan()
            print(f'{len(done)} arquivo(s) renomeado(s).')
        else:
            print(f'{len(steps)} arquivo(s) seriam renomeados. Use --apply para executar.')
        return 0
    finally:
        manager.file_lock.close()


if __name__ == '__main__':
    sys.exit(main())
