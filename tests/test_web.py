import io
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

from app import auth, settings
from app.main import application
from scripts import init_db


class MagnetBoxWebTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        root = Path(self.tmpdir.name)
        self.db_path = root / 'data' / 'db' / 'magnetbox.sqlite3'
        self.inbox = root / 'data' / 'inbox'
        self.processing = root / 'data' / 'processing'
        self.completed = root / 'data' / 'completed'
        self.failed = root / 'data' / 'failed'
        self.logs = root / 'logs'
        runtime_dirs = (root / 'data', root / 'data' / 'db', self.inbox, self.processing, self.completed, self.failed, self.logs)
        patches = [
            patch.object(init_db, 'DB_PATH', self.db_path),
            patch.object(init_db, 'RUNTIME_DIRECTORIES', runtime_dirs),
            patch.object(settings, 'DB_PATH', self.db_path),
            patch.object(settings, 'INBOX_DIR', self.inbox),
            patch.object(settings, 'PROCESSING_DIR', self.processing),
            patch.object(settings, 'COMPLETED_DIR', self.completed),
            patch.object(settings, 'FAILED_DIR', self.failed),
            patch.object(settings, 'LOG_DIR', self.logs),
            patch.object(settings, 'SECRET_KEY', 'test-secret'),
            patch.object(settings, 'SESSION_COOKIE_NAME', 'magnetbox_session'),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        with patch.dict(os.environ, {
            'MAGNETBOX_ADMIN_USERNAME': 'admin',
            'MAGNETBOX_ADMIN_PASSWORD_HASH': auth.hash_password('init-pass'),
        }, clear=False):
            init_db.initialize_database()

    def request(self, path='/', method='GET', data=None, cookie=None):
        payload = ''
        if data:
            payload = '&'.join(f'{key}={value}' for key, value in data.items())
        body = payload.encode('utf-8')
        environ = {
            'REQUEST_METHOD': method,
            'PATH_INFO': path,
            'QUERY_STRING': '',
            'SERVER_NAME': 'testserver',
            'SERVER_PORT': '80',
            'SERVER_PROTOCOL': 'HTTP/1.1',
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'http',
            'wsgi.input': io.BytesIO(body),
            'wsgi.errors': io.StringIO(),
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'CONTENT_LENGTH': str(len(body)),
            'CONTENT_TYPE': 'application/x-www-form-urlencoded',
        }
        if cookie:
            environ['HTTP_COOKIE'] = cookie
        captured = {}
        def start_response(status, headers):
            captured['status'] = status
            captured['headers'] = headers
        body_chunks = application(environ, start_response)
        captured['body'] = b''.join(body_chunks).decode('utf-8')
        return captured

    def cookie_from_headers(self, headers):
        for key, value in headers:
            if key.lower() == 'set-cookie':
                return value
        return None

    def test_login_page_and_redirects_work(self):
        response = self.request('/submit')
        self.assertTrue(response['status'].startswith('302'))
        self.assertIn('/login', dict(response['headers'])['Location'])

        login = self.request('/login')
        self.assertTrue(login['status'].startswith('200'))
        self.assertIn('Sign in', login['body'])

    def test_authenticated_user_can_submit_and_view_history(self):
        login = self.request('/login', method='POST', data={'username': 'admin', 'password': 'init-pass', 'next': '/submit'})
        self.assertTrue(login['status'].startswith('302'))
        cookie = self.cookie_from_headers(login['headers'])
        self.assertIsNotNone(cookie)

        submit = self.request('/submit', method='POST', data={'magnet_uri': 'magnet:?xt=urn:btih:1234567890ABCDEF'}, cookie=cookie)
        self.assertTrue(submit['status'].startswith('200'))
        self.assertIn('queued successfully', submit['body'])

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute('SELECT job_id, magnet_uri, status, submitted_by FROM jobs ORDER BY id DESC LIMIT 1').fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], 'magnet:?xt=urn:btih:1234567890ABCDEF')
        self.assertEqual(row[2], 'queued')
        self.assertEqual(row[3], 'admin')

        history = self.request('/history', cookie=cookie)
        self.assertTrue(history['status'].startswith('200'))
        self.assertIn('Job History', history['body'])
        self.assertIn(row[0], history['body'])

        inbox_files = list(self.inbox.glob('*.json'))
        self.assertEqual(len(inbox_files), 1)

    def test_bad_login_is_rejected(self):
        response = self.request('/login', method='POST', data={'username': 'admin', 'password': 'wrong', 'next': '/submit'})
        self.assertTrue(response['status'].startswith('401'))
        self.assertIn('Invalid username or password', response['body'])


if __name__ == '__main__':
    unittest.main()
