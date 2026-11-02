import ctypes
import http.client
import io
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from server.app import StudioServer
from server.jobs import QueueUnavailable
from server.guards import AccessGuard, local_guard, origin_guard
from server.launchd import activate_socket
from server.media import byte_range, playable
from server.productions import Productions


def headers(**values):
    result = Message()
    for key, value in values.items():
        result[key.replace('_', '-')] = value
    return result


class GuardsTest(unittest.TestCase):
    def test_local(self):
        for host in ('localhost:8450', '127.0.0.1:8450'):
            for peer in ('127.0.0.1', '::1'):
                self.assertTrue(local_guard(peer, headers(Host=host), 8450))
        for host in ('viewer.example', 'localhost.evil:8450', 'localhost', 'localhost:8451'):
            self.assertFalse(local_guard('127.0.0.1', headers(Host=host), 8450))
        self.assertFalse(local_guard('192.0.2.1', headers(Host='localhost:8450'), 8450))
        for name in ('Cf-Ray', 'Cf-Visitor', 'Cf-Connecting-Ip', 'Cf-Access-Jwt-Assertion', 'cF-other'):
            h = headers(Host='localhost:8450')
            h[name] = ''
            self.assertFalse(local_guard('127.0.0.1', h, 8450))
        h = headers(Host='localhost:8450')
        h['Host'] = 'localhost:8450'
        self.assertFalse(local_guard('127.0.0.1', h, 8450))

    def test_origin(self):
        h = headers(Host='localhost:8450', Origin='http://localhost:8450', Content_Type='application/json; charset=utf-8')
        self.assertTrue(origin_guard(h, 8450))
        for origin in (None, 'null', 'https://localhost:8450', 'http://127.0.0.1:8450', 'http://evil.example'):
            candidate = headers(Host='localhost:8450', Content_Type='application/json')
            if origin:
                candidate['Origin'] = origin
            self.assertFalse(origin_guard(candidate, 8450))
        h.replace_header('Content-Type', 'text/plain')
        self.assertFalse(origin_guard(h, 8450))


class AccessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = Path(self.tmp.name) / 'config.json'
        self.config.write_text(json.dumps(dict(access_team='test-team', access_aud='test-aud', owner_email='owner@example.test')))
        self.guard = AccessGuard(self.config)
        self.claims = dict(iss='https://test-team.cloudflareaccess.com', aud='test-aud',
                           email='owner@example.test', exp=time.time() + 60)
        self.keys = {'keys': [dict(json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key())), kid='test', use='sig', alg='RS256')]}

    def check(self, claims=None, key=None, algorithm='RS256'):
        token = jwt.encode(claims if claims is not None else self.claims, key or self.key,
                           algorithm=algorithm, headers={'kid': 'test'})
        # Exercise real PyJWKClient key parsing and actual RSA verification; only HTTPS is replaced.
        with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(self.keys).encode())):
            return self.guard(headers(Cf_Access_Jwt_Assertion=token))

    def test_valid_and_cached_keys(self):
        self.assertTrue(self.check())
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('must use cached keys')):
            token = jwt.encode(self.claims, self.key, algorithm='RS256', headers={'kid': 'test'})
            self.assertTrue(self.guard(headers(Cf_Access_Jwt_Assertion=token)))

    def test_reject_claims_and_signatures(self):
        for field, value in [('iss', 'https://wrong.example'), ('aud', 'wrong'), ('email', 'wrong@example.test'), ('exp', time.time() - 1)]:
            with self.subTest(field=field):
                self.assertFalse(self.check(dict(self.claims, **{field: value})))
        for field in self.claims:
            self.assertFalse(self.check({k: v for k, v in self.claims.items() if k != field}))
        self.assertFalse(self.check(key=self.other))
        self.assertFalse(self.check(key='a' * 32, algorithm='HS256'))
        self.assertFalse(self.guard(headers(Cf_Access_Jwt_Assertion='not.a.token')))
        self.assertFalse(self.guard(headers()))

    def test_missing_config_and_keys(self):
        self.config.unlink()
        self.assertFalse(self.check())
        self.config.write_text('{}')
        self.assertFalse(self.check())
        self.config.write_text(json.dumps(dict(access_team='test-team', access_aud='test-aud', owner_email='owner@example.test')))
        token = jwt.encode(self.claims, self.key, algorithm='RS256', headers={'kid': 'test'})
        with patch('urllib.request.OpenerDirector.open', side_effect=OSError('offline')):
            self.assertFalse(self.guard(headers(Cf_Access_Jwt_Assertion=token)))


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.song = self.root / 'songs' / 'sample'
        self.song.mkdir(parents=True)
        (self.song / 'poem.json').write_text('{"title":"A <song>"}')
        (self.song / 'takes').mkdir()
        (self.song / 'takes' / 'take01.mp4').write_bytes(b'0123456789')
        self.server = StudioServer(('127.0.0.1', 0), content=self.root, config=self.root / 'absent', idle_exit_secs=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join(3)
        self.server.server_close()

    def request(self, path='/', method='GET', headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            conn.request(method, path, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_routes_and_remote_denial(self):
        status, _, body = self.request()
        self.assertEqual(status, 200)
        self.assertIn(b'/api/productions', body)
        self.assertEqual(json.loads(self.request('/api/productions')[2])[0]['id'], 'sample')
        self.assertFalse(json.loads(self.request('/api/busy')[2])['busy'])
        self.assertEqual(self.request('/unknown')[0], 404)
        for h in ({'Host': 'viewer.example'}, {'Cf-Ray': 'test'}, {'Host': 'localhost.evil'}):
            self.assertEqual(self.request(headers=h)[0], 403)
            self.assertEqual(self.request('/room/sing/', headers=h)[0], 403)
        with patch.object(self.server, 'access', return_value=True):
            self.assertEqual(self.request(headers={'Host': 'viewer.example'})[0], 200)
            self.assertEqual(self.request('/room/sing/', headers={'Host': 'viewer.example'})[0], 403)
            self.assertEqual(self.request('/room/open', 'POST', {'Host': 'viewer.example'})[0], 403)

    def test_viewer_routes(self):
        for path in ('/song/sample', '/jobs', '/api/song/sample', '/api/jobs'):
            with patch.object(self.server.jobs, 'list', return_value=[]):
                self.assertEqual(self.request(path)[0], 200)
                self.assertEqual(self.request(path, headers={'Cf-Ray': 'remote'})[0], 403)
        for path in ('/song/no', '/api/song/no', '/song/sample/../sample'):
            self.assertEqual(self.request(path)[0], 404)
        with patch.object(self.server.jobs, 'list', return_value=[]):
            self.assertEqual(self.request('/api/jobs/--help/log')[0], 404)
        with patch.object(self.server.jobs, 'list', side_effect=QueueUnavailable('Queue offline')):
            self.assertEqual(self.request('/api/jobs')[0], 503)

    def test_post_checks(self):
        self.assertEqual(self.request('/room/open', 'POST')[0], 403)
        h = {'Origin': f'http://127.0.0.1:{self.server.server_port}', 'Content-Type': 'application/json'}
        self.assertEqual(self.request('/room/open', 'POST', h)[0], 400)
        h['Content-Type'] = 'text/plain'
        self.assertEqual(self.request('/room/open', 'POST', h)[0], 403)

    def test_ranges(self):
        path = '/file/sample/takes/take01.mp4'
        self.assertEqual(self.request(path)[2], b'0123456789')
        for value, data, bounds in [('bytes=2-4', b'234', '2-4'), ('bytes=-3', b'789', '7-9'), ('bytes=7-', b'789', '7-9'), ('bytes=8-999', b'89', '8-9')]:
            status, h, body = self.request(path, headers={'Range': value})
            self.assertEqual((status, body), (206, data))
            self.assertEqual(h['Content-Range'], f'bytes {bounds}/10')
            self.assertEqual(int(h['Content-Length']), len(data))
        for value in ('bytes=10-', 'bytes=5-2', 'bytes=-0', 'bytes=0-1,3-4', 'bytes=x-y', 'bytes=-', 'items=1-2'):
            status, h, body = self.request(path, headers={'Range': value})
            self.assertEqual((status, body), (416, b''))
            self.assertEqual(h['Content-Range'], 'bytes */10')

    def test_path_allowlist(self):
        deleted = self.song / 'takes' / 'deleted'
        deleted.mkdir()
        (deleted / 'take02.mp4').write_bytes(b'secret')
        (self.song / 'takes' / 'link.mp4').symlink_to(deleted / 'take02.mp4')
        (self.song / 'takes' / 'outside.mp4').symlink_to(self.root / 'outside.mp4')
        (self.root / 'outside.mp4').write_bytes(b'outside')
        (self.song / 'secret.json').write_text('{}')
        (self.song / 'takes' / 'secret.json').symlink_to(self.song / 'secret.json')
        build = self.root / 'build' / 'sample'
        (build / 'options').mkdir(parents=True)
        (build / 'options' / 'render.mp4').write_bytes(b'render')
        self.assertEqual(self.request('/file/sample/build/options/render.mp4')[2], b'render')
        for relative in ('../poem.json', '%2e%2e/poem.json', '/etc/passwd', 'takes/deleted/take02.mp4', 'takes/link.mp4', 'takes/outside.mp4', 'takes/secret.json', 'secret.json', '.hidden.json', 'build/options/../options/render.mp4', 'takes/no.py'):
            with self.subTest(path=relative):
                self.assertEqual(self.request('/file/sample/' + relative)[0], 404)
        self.assertEqual(self.request('/file/sample%2f../poem.json')[0], 404)

    def test_wav_conversion_and_cache_invalidation(self):
        import soundfile as sf
        import numpy as np
        path = self.song / 'vocals.wav'
        samples = np.linspace(-0.8, 0.8, 100)
        sf.write(path, samples, 8000, subtype='PCM_24')
        first = playable(path)
        self.assertEqual(sf.info(io.BytesIO(first)).subtype, 'PCM_16')
        converted, rate = sf.read(io.BytesIO(first))
        self.assertEqual(rate, 8000)
        self.assertEqual(len(converted), len(samples))
        self.assertLessEqual(float(np.max(np.abs(converted - samples))), 1 / 32768)
        self.assertEqual(self.request('/file/sample/vocals.wav', headers={'Range': 'bytes=0-3'})[2], b'RIFF')
        sf.write(path, np.ones(200) * 0.5, 8000, subtype='FLOAT')
        second = playable(path)
        self.assertNotEqual(first, second)
        self.assertEqual(sf.info(io.BytesIO(second)).frames, 200)

    def test_idle_busy_and_request_in_flight(self):
        self.server.idle_exit_secs = 0.05
        self.server.busy = True
        time.sleep(0.1)
        self.assertTrue(self.thread.is_alive())
        self.server.busy = False
        conn = socket.create_connection(self.server.server_address)
        conn.sendall(b'GET / HTTP/1.0\r\n')
        time.sleep(0.1)
        self.assertTrue(self.thread.is_alive())
        conn.sendall(f'Host: 127.0.0.1:{self.server.server_port}\r\n\r\n'.encode())
        while conn.recv(65536):
            pass
        conn.close()
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())


class StartupTest(unittest.TestCase):
    def test_import_does_not_load_device_libraries(self):
        subprocess.run([sys.executable, '-c', 'import server.app, sys; assert not ({"numpy", "sounddevice", "soundfile", "PIL"} & sys.modules.keys())'], check=True)

    def test_adopt_listener(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        address = listener.getsockname()
        with StudioServer(listener=listener) as server:
            self.assertEqual(server.server_port, address[1])
            self.assertIs(server.socket, listener)

    def test_launchd_ffi(self):
        from unittest.mock import Mock
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        import os
        first, extra = os.dup(listener.fileno()), os.dup(listener.fileno())
        array = (ctypes.c_int * 2)(first, extra)
        def activate(name, fds, count):
            self.assertEqual(name, b'http')
            ctypes.cast(fds, ctypes.POINTER(ctypes.POINTER(ctypes.c_int)))[0] = ctypes.cast(array, ctypes.POINTER(ctypes.c_int))
            ctypes.cast(count, ctypes.POINTER(ctypes.c_size_t))[0] = 2
            return 0
        libc = Mock()
        libc.launch_activate_socket.side_effect = activate
        with patch('ctypes.CDLL', return_value=libc):
            adopted = activate_socket('http')
        self.assertEqual(adopted.getsockname(), listener.getsockname())
        adopted.close()
        with self.assertRaises(OSError):
            os.fstat(extra)
        libc.free.assert_called_once()
        libc.launch_activate_socket.side_effect = None
        libc.launch_activate_socket.return_value = 2
        with patch('ctypes.CDLL', return_value=libc), self.assertRaises(OSError):
            activate_socket('missing')


if __name__ == '__main__':
    unittest.main()
