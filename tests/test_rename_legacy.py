import asyncio
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from backend.downloads import DownloadManager
from backend.library import Library
from backend.rename_legacy import apply, plan


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/FFprobe necessários')
class RenameLegacyTests(unittest.TestCase):
    def test_plan_apply_preserves_catalog_history_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = DownloadManager(root / 'data', root / 'music')
            manager._init_db()
            try:
                manager.download_dir.mkdir()
                old = manager.download_dir / 'abcdefghijk.mp3'
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=1', '-c:a', 'libmp3lame', str(old)], check=True)
                no_title = manager.download_dir / 'lmnopqrstuv.mp3'
                shutil.copyfile(old, no_title)
                blocked = manager.download_dir / 'zzzzzzzzzzz.mp3'
                shutil.copyfile(old, blocked)
                (manager.download_dir / 'Mesmo-Nome_zzzzzzzzzzz.mp3').write_bytes(b'ocupado')
                with manager._connect() as conn:
                    conn.execute("INSERT INTO downloads(id,video_id,title,url,status,filename) VALUES('h','abcdefghijk','Música: Ação (Ao Vivo)','u','completed','abcdefghijk.mp3')")
                    conn.execute("INSERT INTO downloads(id,video_id,title,url,status) VALUES('b','zzzzzzzzzzz','Mesmo Nome','u','completed')")
                library = Library(manager)
                library.initialize()
                library.scan()
                steps = plan(manager)
                self.assertEqual({o.name for o, _, _ in steps}, {'abcdefghijk.mp3', 'zzzzzzzzzzz.mp3'})
                self.assertTrue(old.exists())  # plano não altera nada
                done = apply(manager, steps)
                self.assertEqual([(o.name, n.name) for o, n in done], [('abcdefghijk.mp3', 'Musica-Acao-Ao-Vivo_abcdefghijk.mp3')])
                self.assertFalse(old.exists())
                self.assertTrue(no_title.exists() and blocked.exists())
                self.assertEqual((manager.download_dir / 'Mesmo-Nome_zzzzzzzzzzz.mp3').read_bytes(), b'ocupado')
                with manager._connect() as conn:
                    row = conn.execute("SELECT filename,original_filename,available FROM library_tracks WHERE video_id='abcdefghijk'").fetchone()
                    self.assertEqual(tuple(row), ('Musica-Acao-Ao-Vivo_abcdefghijk.mp3', 'abcdefghijk.mp3', 1))
                    self.assertEqual(conn.execute("SELECT filename FROM downloads WHERE id='h'").fetchone()[0], 'Musica-Acao-Ao-Vivo_abcdefghijk.mp3')
                library.scan()
                with manager._connect() as conn:
                    self.assertEqual(conn.execute("SELECT count(*) FROM library_tracks WHERE video_id='abcdefghijk'").fetchone()[0], 1)
                    self.assertEqual(conn.execute("SELECT original_filename FROM library_tracks WHERE video_id='abcdefghijk'").fetchone()[0], 'abcdefghijk.mp3')
            finally:
                manager.file_lock.close()


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg/FFprobe necessários')
class ImportTests(unittest.TestCase):
    def test_import_copies_records_original_and_skips_duplicates_and_invalid(self):
        from backend.rename_legacy import import_files, import_plan, record_import, main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = DownloadManager(root / 'data', root / 'music')
            manager._init_db()
            try:
                source = root / 'Musicas'
                source.mkdir()
                good = source / 'Adele - Send My Love (To Your New Lover) [fk4BbF7B29w].mp3'
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=1', '-c:a', 'libmp3lame', str(good)], check=True)
                (source / 'Quebrado [AAAAAAAAAAA].mp3').write_bytes(b'lixo')
                shutil.copyfile(good, source / 'Sem id.mp3')
                shutil.copyfile(good, source / 'Copia [fk4BbF7B29w].mp3')
                shutil.copyfile(good, source / 'Já existe [bbbbbbbbbbb].mp3')
                (source / 'video [ccccccccccc].mp4').write_bytes(b'x')
                manager.download_dir.mkdir()
                shutil.copyfile(good, manager.download_dir / 'bbbbbbbbbbb.mp3')
                library = Library(manager)
                library.initialize()
                steps, skipped = import_plan(manager, source)
                self.assertEqual([s[1].name for s in steps], ['Adele-Send-My-Love-To-Your-New-Lover_fk4BbF7B29w.mp3'])
                self.assertEqual(len(skipped), 4)
                self.assertTrue(good.exists())
                done = import_files(manager, steps)
                library.scan()
                record_import(manager, done)
                self.assertTrue(good.exists())  # copiado, original intacto
                with manager._connect() as conn:
                    row = conn.execute("SELECT title,original_filename,original_title,available FROM library_tracks WHERE video_id='fk4BbF7B29w'").fetchone()
                self.assertEqual(tuple(row), ('Adele - Send My Love (To Your New Lover)', good.name, 'Adele - Send My Love (To Your New Lover)', 1))
                # Nova varredura não perde o título nem o nome original.
                library.scan()
                with manager._connect() as conn:
                    self.assertEqual(conn.execute("SELECT original_filename FROM library_tracks WHERE video_id='fk4BbF7B29w'").fetchone()[0], good.name)
                # Segunda importação não encontra nada novo.
                self.assertEqual(import_plan(manager, source)[0], [])
                # --mover remove da origem somente o arquivo importado.
                extra = source / 'Outra [dddddddddd1].mp3'
                shutil.copyfile(good.parent / 'Sem id.mp3', extra)
                steps, _ = import_plan(manager, source)
                done = import_files(manager, steps, move=True)
                self.assertEqual(len(done), 1)
                self.assertFalse(extra.exists())
                self.assertTrue((source / 'Sem id.mp3').exists() and good.exists())
            finally:
                manager.file_lock.close()
