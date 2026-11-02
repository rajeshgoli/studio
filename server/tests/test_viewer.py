import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.jobs import Jobs, QueueUnavailable
from server.productions import Productions
from server.viewer import song


class SongDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.folder = self.root / 'songs' / 'sample'
        (self.folder / 'takes').mkdir(parents=True)
        self.write('poem.json', {'title': '<Song>', 'lines': [dict(id='L1', meaning='Hello', deva='नमस्ते', translit='namaste')], 'sung': ['L1', 'L1']})
        self.productions = Productions(self.root)

    def write(self, relative, data):
        (self.folder / relative).write_text(json.dumps(data))

    def test_full_song_and_latest_render(self):
        self.write('takes/take01.json', dict(seconds=12, peak_dbfs=-8, sa_hz=204, guide='tanpura'))
        (self.folder / 'takes/take01.wav').write_bytes(b'voice')
        (self.folder / 'vocals.wav').write_bytes(b'voice')
        self.write('marks.json', dict(vocals_bytes=5, line_starts=[1, 4], end=12))
        self.write('timing.json', dict(sung=[dict(line='L1', start=1, end=4)]))
        (self.folder / 'youtube.md').write_text('## Title (pick one)\n\nOne\n\n## Description\n\nHello\n\n#Tag\n')
        build = self.root / 'build/sample'
        (build / 'options').mkdir(parents=True)
        (build / 'sample_short.mp4').write_bytes(b'video')
        (build / 'options/alternate.wav').write_bytes(b'audio')
        os.utime(build / 'sample_short.mp4', (1, 1))
        data = song(self.productions, 'sample')
        self.assertEqual(len(data['lines']), 2)
        self.assertTrue(data['takes'][0]['in_use'])
        self.assertEqual(data['takes'][0]['sa_hz'], 204)
        self.assertEqual(data['publishing']['title'], 'One')
        self.assertEqual(data['publishing']['description'], 'Hello\n\n#Tag')
        self.assertEqual(data['renders'][0]['name'], 'alternate.wav')
        self.assertEqual(self.productions.list()[0]['newest_render'], data['renders'][0])
        (self.folder / 'vocals.wav').write_bytes(b'changed size')
        self.assertFalse(song(self.productions, 'sample')['takes'][0]['in_use'])

    def test_optional_corrupt_missing_and_escaping_files(self):
        (self.folder / 'marks.json').write_text('{')
        (self.folder / 'takes/take01.json').write_text('{')
        outside = self.root / 'private.json'
        outside.write_text('{"seconds":99}')
        (self.folder / 'takes/take02.json').symlink_to(outside)
        (self.folder / 'youtube.md').symlink_to(outside)
        data = song(self.productions, 'sample')
        self.assertEqual(data['takes'], [])
        self.assertEqual(data['marks'], {})
        self.assertEqual(data['publishing']['text'], '')
        for pid in ('../sample', 'missing', 'sample/../sample'):
            with self.assertRaises(FileNotFoundError):
                song(self.productions, pid)


class JobsTest(unittest.TestCase):
    def test_fixed_commands_filter_and_log_membership(self):
        jobs = Jobs()
        rows = [dict(id='job_abc', label='song-render', state='succeeded'), dict(id='job_def', label='other')]
        with patch('server.jobs.subprocess.run') as run:
            run.return_value.stdout = json.dumps(rows)
            result = jobs.list()
            self.assertEqual([j['studio'] for j in result], [True, False])
            self.assertEqual(run.call_args.args[0], ['sm', 'queue', 'list', '--all', '--json', '--limit', '50'])
            with self.assertRaises(FileNotFoundError):
                jobs.log('--help')
            self.assertEqual(run.call_count, 1)
            run.return_value.stdout = '\n'.join(str(i) for i in range(300))
            log = jobs.log('song-render')
            self.assertEqual(run.call_args.args[0], ['sm', 'queue', 'log', 'job_abc'])
            self.assertEqual(log.splitlines(), [str(i) for i in range(100, 300)])
            self.assertNotIn('shell', run.call_args.kwargs)

    def test_queue_errors_and_expired_membership(self):
        jobs = Jobs()
        with patch.object(jobs, '_run', return_value='not json'):
            with self.assertRaises(QueueUnavailable): jobs.list()
        with patch('server.jobs.subprocess.run', side_effect=subprocess.TimeoutExpired('sm', 10)):
            with self.assertRaises(QueueUnavailable): jobs.list()
        with patch.object(jobs, '_run', return_value='[]'):
            with self.assertRaises(FileNotFoundError): jobs.log('job_old')

