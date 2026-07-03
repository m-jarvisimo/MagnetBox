import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app import auth, settings
from scripts import init_db
from worker import main as worker_main


class WorkerPhaseTests(unittest.TestCase):
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

    def _write_inbox_job(self, job_id='job-1', magnet_uri='magnet:?xt=urn:btih:1234567890ABCDEF'):
        self.inbox.mkdir(parents=True, exist_ok=True)
        path = self.inbox / f'{job_id}.json'
        path.write_text('\n'.join([
            '{',
            f'  "job_id": "{job_id}",',
            f'  "magnet_uri": "{magnet_uri}",',
            '  "submitted_by": "admin",',
            '  "status": "queued",',
            '  "created_at": "2026-01-01T00:00:00+00:00"',
            '}',
            ''
        ]), encoding='utf-8')
        return path

    def test_process_pending_jobs_once_completes_queued_job(self):
        self._write_inbox_job()
        result = worker_main.process_pending_jobs_once()
        self.assertEqual(result, 1)
        self.assertEqual(list(self.inbox.glob('*.json')), [])
        self.assertEqual(len(list(self.processing.glob('*.json'))), 0)
        completed_files = list(self.completed.glob('*.json'))
        self.assertEqual(len(completed_files), 1)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute('SELECT status, claimed_at, completed_at, output_path FROM jobs WHERE job_id = ?', ('job-1',)).fetchone()
        self.assertEqual(row[0], 'completed')
        self.assertIsNotNone(row[1])
        self.assertIsNotNone(row[2])
        self.assertTrue(row[3])

    def test_process_pending_jobs_once_moves_bad_job_to_failed(self):
        self.inbox.mkdir(parents=True, exist_ok=True)
        (self.inbox / 'bad.json').write_text('{not-json', encoding='utf-8')
        result = worker_main.process_pending_jobs_once()
        self.assertEqual(result, 0)
        self.assertEqual(list(self.inbox.glob('*.json')), [])
        self.assertEqual(len(list(self.failed.glob('*.json'))), 1)

    def test_run_worker_loop_processes_until_stop_event(self):
        stop_event = threading.Event()
        calls = []
        processor_runs = 0

        def processor():
            nonlocal processor_runs
            processor_runs += 1
            calls.append('process')
            if processor_runs == 2:
                stop_event.set()
            return 0

        def sleeper(seconds):
            calls.append(f'sleep:{seconds}')

        with patch.object(worker_main, 'process_pending_jobs_once', side_effect=processor), patch.object(worker_main.time, 'sleep', side_effect=sleeper):
            worker_main.run_worker_loop(interval_seconds=1.5, stop_event=stop_event)

        self.assertEqual(calls, ['process', 'sleep:1.5', 'process'])


if __name__ == '__main__':
    unittest.main()
