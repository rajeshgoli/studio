"""HTTP checks with real take files and stand-in streams; never touches Mac devices."""
import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from server.app import StudioServer
from server.rooms import legacy_running
from songs.sing_room import RATE, Studio, make_page


class Stream:
    instances = []

    def __init__(self, **kwargs):
        self.callback = kwargs['callback']
        self.input = kwargs['channels'] == 1
        self.closed = False
        self.instances.append(self)

    def start(self):
        if self.input:
            self.feed(480)

    def feed(self, frames):
        t = np.arange(frames) / RATE
        self.callback((.2 * np.sin(2 * np.pi * 220 * t)).astype('float32')[:, None], frames, None, None)

    def close(self):
        self.closed = True


class RoomTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        folder = self.root / 'songs' / 'test'
        folder.mkdir(parents=True)
        (folder / 'poem.json').write_text(json.dumps(dict(title='Test', music={}, sung=['a'],
            lines=[dict(id='a', translit='Test line', meaning='Test meaning')],
            spoken_intro={'text': 'Test intro', 'until': 0})))
        (self.root / 'studio.json').write_text(json.dumps(dict(mic='Test mic', ear='Test ear')))
        self.folder = folder
        Stream.instances = []
        devices = [{'name': 'Test mic', 'max_output_channels': 2},
                   {'name': 'Test ear', 'max_output_channels': 2}]
        for target, value in [('server.devices.sd.InputStream', Stream),
                              ('server.devices.sd.OutputStream', Stream)]:
            mock = patch(target, value)
            mock.start()
            self.addCleanup(mock.stop)
        for target, value in [('server.devices.sd.query_devices', devices),
                              ('server.rooms.legacy_running', False),
                              ('songs.sing_room.tanpura', np.ones((RATE * 4, 2), dtype='float32') * .1)]:
            mock = patch(target, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        self.server = StudioServer(('127.0.0.1', 0), content=self.root, idle_exit_secs=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01})
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def request(self, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        h = {'Origin': f'http://127.0.0.1:{self.server.server_port}', 'Content-Type': 'application/json'}
        h.update(headers or {})
        conn.request('POST' if body is not None or raw is not None else 'GET', path,
                     body=raw if raw is not None else json.dumps(body) if body is not None else None, headers=h)
        res = conn.getresponse()
        result = res.status, res.read()
        conn.close()
        return result

    def post(self, action, body=None):
        return self.request('/room/sing/' + action, {} if body is None else body)[0]

    def open(self):
        self.assertEqual(self.request('/room/open', {'kind': 'sing', 'production': 'test'})[0], 200)
        return self.server.room

    def test_take_preview_use_delete_and_close(self):
        room = self.open()
        self.assertEqual(self.request('/room/sing/outputs')[1], b'["Test ear"]')
        self.assertEqual(self.post('preview'), 200)
        self.assertTrue(self.server.busy)
        room.mic.feed(RATE)
        self.assertEqual(list(room.takes_dir.iterdir()), [])
        self.assertEqual(self.request('/room/close', {})[0], 409)
        self.assertEqual(self.post('preview'), 200)
        self.assertFalse(self.server.busy)
        self.assertEqual(self.post('step'), 200)
        room.mic.feed(RATE * 2)
        self.assertEqual(self.post('step'), 200)  # guide after spoken intro
        self.assertEqual(self.post('step'), 200)  # mark the only line
        room.mic.feed(RATE)
        self.assertEqual(self.post('step'), 200)  # finish
        y, rate = sf.read(room.takes_dir / 'take01.wav')
        self.assertEqual((len(y), rate), (RATE * 3, RATE))
        self.assertAlmostEqual(float(abs(y).max()), .2, places=5)
        self.assertFalse(self.server.busy)
        self.assertEqual(self.request('/room/sing/take/take01.wav')[0], 200)
        self.assertEqual(self.post('use', {'name': 'take01'}), 200)
        marks = json.loads((self.folder / 'marks.json').read_text())
        self.assertEqual(marks['guide_sa_hz'], 204)
        self.assertEqual(marks['line_starts'], [2.0])
        self.assertEqual(json.loads((self.folder / 'poem.json').read_text())['spoken_intro']['until'], 2)
        self.assertEqual(self.post('delete', {'name': 'take01'}), 200)
        self.assertEqual(len(list((room.takes_dir / 'deleted').iterdir())), 2)
        self.assertEqual(self.request('/room/close', {})[0], 200)
        self.assertTrue(all(s.closed for s in Stream.instances))
        self.assertFalse(room.watchdog.is_alive())
        self.assertFalse(room.writer.is_alive())

    def test_guards_validation_and_exclusivity(self):
        for h in ({'Host': 'studio.example'}, {'Cf-Ray': 'test'}):
            self.assertEqual(self.request('/room/open', {'kind': 'sing', 'production': 'test'}, h)[0], 403)
            self.assertEqual(self.request('/room/sing/state', headers=h)[0], 403)
        self.assertEqual(self.request('/room/open', raw='[]')[0], 400)
        self.assertEqual(self.request('/room/open', raw='{')[0], 400)
        with patch('server.rooms.legacy_running', return_value=True):
            self.assertEqual(self.request('/room/open', {'kind': 'sing', 'production': 'test'})[0], 409)
        room = self.open()
        self.assertEqual(self.request('/room/open', {'kind': 'sing', 'production': 'test'})[0], 409)
        for action, body in [('ear', {'name': 'Test mic'}), ('use', {'name': '../vocals'}),
                             ('delete', {'name': 'take0000'}), ('set', {'gain': 99}),
                             ('set', {'mix': float('nan')}), ('set', {'start_at': -1}),
                             ('set', {'mode': []}), ('set', {'mode': 'unknown'})]:
            self.assertEqual(self.post(action, body), 400, (action, body))
        self.assertEqual(self.post('set', {'mix': .4, 'gain': .5, 'start_at': 1, 'mode': 'tanpura'}), 200)
        self.assertEqual(room.ear.gain, .5)
        self.assertEqual(self.post('step'), 200)
        self.assertEqual(self.post('delete', {'name': 'take01'}), 409)
        self.assertEqual(self.post('abort'), 200)
        self.assertEqual(len(list((room.takes_dir / 'deleted').glob('*.wav'))), 1)

    def test_preview_completion_and_idle_exit(self):
        room = self.open()
        self.post('preview')
        room.ear.buf = None  # output finished naturally, even with no page polling
        self.assertFalse(self.server.busy)
        self.server.idle_exit_secs = .03
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())
        self.assertIsNone(self.server.room)
        self.assertTrue(all(s.closed for s in Stream.instances))

    def test_three_digit_names_and_page_controls(self):
        room = self.open()
        (room.takes_dir / 'take99.wav').touch()
        self.assertEqual(room.next_name(), 'take100')
        (room.takes_dir / 'take100.wav').touch()
        self.assertEqual(room.next_name(), 'take101')
        page = make_page(room)
        for text in ('passive:false', 'lastWheel>600', 'setInterval(tick,250)',
                     '/room/sing/state', '/room/sing/outputs', "'Content-Type':'application/json'", 'tk!=lastTakes'):
            self.assertIn(text, page)

    def test_port_probe(self):
        import socket
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            from server import rooms
            with patch.object(rooms.socket, 'create_connection', return_value=socket.create_connection(listener.getsockname())):
                self.assertTrue(legacy_running())
