"""Migrações do SQLite em ordem. A versão do banco é PRAGMA user_version.

Cada migração deve ser idempotente: bancos criados antes deste módulo já têm
user_version 0 ou 1 com parte das tabelas presentes.
"""


def _initial(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS downloads (
        id TEXT PRIMARY KEY, video_id TEXT NOT NULL, title TEXT NOT NULL,
        url TEXT NOT NULL, status TEXT NOT NULL, progress REAL,
        downloaded REAL, total REAL, speed REAL, eta REAL,
        message TEXT NOT NULL DEFAULT '', filename TEXT,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )''')
    if 'channel' not in {row[1] for row in conn.execute('PRAGMA table_info(downloads)')}:
        conn.execute("ALTER TABLE downloads ADD COLUMN channel TEXT NOT NULL DEFAULT ''")
    conn.execute('CREATE INDEX IF NOT EXISTS downloads_video ON downloads(video_id, status)')
    conn.execute('''CREATE TABLE IF NOT EXISTS library_tracks (
        id TEXT PRIMARY KEY, filename TEXT NOT NULL UNIQUE, video_id TEXT,
        title TEXT NOT NULL, channel TEXT NOT NULL DEFAULT '', artist TEXT NOT NULL DEFAULT '',
        album TEXT NOT NULL DEFAULT '', duration REAL, size INTEGER, mtime_ns INTEGER,
        available INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
        added_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
    )''')


def _original_names(conn):
    """Título original do YouTube e nome de arquivo anterior, para conferir se um arquivo é o mesmo."""
    columns = {row[1] for row in conn.execute('PRAGMA table_info(library_tracks)')}
    for column in ('original_title', 'original_filename'):
        if column not in columns:
            conn.execute(f"ALTER TABLE library_tracks ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")


MIGRATIONS = [_initial, _original_names]


def migrate(conn):
    current = conn.execute('PRAGMA user_version').fetchone()[0]
    if current > len(MIGRATIONS):
        raise RuntimeError('O histórico foi criado por uma versão mais nova da aplicação.')
    for version in range(current, len(MIGRATIONS)):
        MIGRATIONS[version](conn)
        conn.execute(f'PRAGMA user_version={version + 1}')
