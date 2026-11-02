import sqlite3
import tempfile
import unittest
from pathlib import Path
from backend.media import display_title, final_name, find_files, slugify, video_id_from_stem
from backend.migrations import MIGRATIONS, migrate


class MediaNameTests(unittest.TestCase):
    def test_slug_removes_accents_symbols_and_path_characters(self):
        self.assertEqual(slugify('Mágica: "Coração" (Ao Vivo) / 2024 *?<>|'), 'Magica-Coracao-Ao-Vivo-2024')
        self.assertEqual(slugify('../../etc/passwd'), 'etc-passwd')
        self.assertEqual(slugify("Don't Leave Me"), 'Dont-Leave-Me')
        self.assertEqual(slugify('日本語'), 'musica')
        self.assertEqual(slugify(''), 'musica')
        self.assertLessEqual(len(slugify('a' * 500)), 80)

    def test_final_name_round_trips_video_id(self):
        for vid in ('abcdefghijk', '-_-_-_-_-_-', 'D0_GWTy9FEM'):
            name = final_name(vid, 'Título (ao vivo)')
            self.assertRegex(name, r'^[A-Za-z0-9_.-]+$')
            self.assertEqual(video_id_from_stem(Path(name).stem), vid)
        self.assertEqual(video_id_from_stem('abcdefghijk'), 'abcdefghijk')
        self.assertIsNone(video_id_from_stem('musica qualquer'))
        self.assertEqual(display_title('Meu-Titulo_abcdefghijk'), 'Meu Titulo')
        self.assertEqual(display_title('arquivo antigo'), 'arquivo antigo')

    def test_find_files_ignores_other_videos_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'abcdefghijk.mp3').write_bytes(b'x')
            (root / 'Titulo_abcdefghijk.mp3').write_bytes(b'x')
            (root / 'Titulo_zzzzzzzzzzz.mp3').write_bytes(b'x')
            (root / 'Outro_abcdefghijk.mp3').symlink_to(root / 'abcdefghijk.mp3')
            names = sorted(p.name for p in find_files(root, 'abcdefghijk'))
            self.assertEqual(names, ['Titulo_abcdefghijk.mp3', 'abcdefghijk.mp3'])


class MigrationTests(unittest.TestCase):
    def test_old_database_keeps_history_and_gains_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = sqlite3.connect(Path(tmp) / 'h.sqlite3')
            conn.execute('''CREATE TABLE downloads (id TEXT PRIMARY KEY, video_id TEXT NOT NULL, title TEXT NOT NULL,
                url TEXT NOT NULL, status TEXT NOT NULL, progress REAL, downloaded REAL, total REAL, speed REAL, eta REAL,
                message TEXT NOT NULL DEFAULT '', filename TEXT, created_at TEXT, updated_at TEXT)''')
            conn.execute("INSERT INTO downloads(id,video_id,title,url,status) VALUES('a','abcdefghijk','Antigo','u','completed')")
            migrate(conn)
            migrate(conn)
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], len(MIGRATIONS))
            self.assertEqual(conn.execute("SELECT title,channel FROM downloads").fetchone(), ('Antigo', ''))
            conn.execute('SELECT * FROM library_tracks')
            conn.execute(f'PRAGMA user_version={len(MIGRATIONS) + 1}')
            with self.assertRaises(RuntimeError):
                migrate(conn)
