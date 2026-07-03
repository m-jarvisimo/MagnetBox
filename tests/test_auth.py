import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import auth
from scripts import init_db


class AuthTests(unittest.TestCase):
    def test_hash_and_verify_password_round_trip(self):
        hashed = auth.hash_password('correct horse battery staple')
        self.assertTrue(auth.verify_password('correct horse battery staple', hashed))
        self.assertFalse(auth.verify_password('wrong password', hashed))

    def test_authenticate_user_uses_sqlite_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'magnetbox.sqlite3'
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    '''
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    '''
                )
                conn.execute(
                    '''
                    INSERT INTO users (username, password_hash, is_active, created_at, updated_at)
                    VALUES (?, ?, 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                    ''',
                    ('admin', auth.hash_password('s3cret-pass')),
                )
                conn.commit()

            self.assertTrue(auth.authenticate_user('admin', 's3cret-pass', db_path=db_path))
            self.assertFalse(auth.authenticate_user('admin', 'wrong-pass', db_path=db_path))
            self.assertFalse(auth.authenticate_user('missing', 's3cret-pass', db_path=db_path))


class InitDbTests(unittest.TestCase):
    def test_initialize_database_seeds_admin_user_when_env_vars_are_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / 'data' / 'db' / 'magnetbox.sqlite3'
            inbox = root / 'data' / 'inbox'
            processing = root / 'data' / 'processing'
            completed = root / 'data' / 'completed'
            failed = root / 'data' / 'failed'
            logs = root / 'logs'
            runtime_dirs = (root / 'data', root / 'data' / 'db', inbox, processing, completed, failed, logs)

            with patch.object(init_db, 'DB_PATH', db_path), patch.object(init_db, 'RUNTIME_DIRECTORIES', runtime_dirs), patch.dict('os.environ', {
                'MAGNETBOX_ADMIN_USERNAME': 'admin',
                'MAGNETBOX_ADMIN_PASSWORD_HASH': auth.hash_password('init-pass'),
            }, clear=False):
                init_db.initialize_database()

            self.assertTrue(db_path.exists())
            for directory in runtime_dirs:
                self.assertTrue(directory.exists(), f'{directory} should exist')

            with sqlite3.connect(db_path) as conn:
                row = conn.execute('SELECT username, is_active FROM users WHERE username = ?', ('admin',)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 'admin')
            self.assertEqual(row[1], 1)


if __name__ == '__main__':
    unittest.main()
