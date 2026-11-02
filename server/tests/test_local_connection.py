"""Real HTTP checks for the public-page/direct-loopback recording boundary."""
import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from email.message import Message
from server.app import StudioServer
from server.local_connection import LocalConnection


class ConnectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        config = Path(self.tmp.name) / "config.json"
        config.write_text(json.dumps({"public_origin": "https://viewer.example"}))
        self.server = StudioServer(("127.0.0.1", 0), content=self.tmp.name, config=config, idle_exit_secs=0)
        self.server.access = lambda headers: headers.get("Cf-Access-Jwt-Assertion") == "owner"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01})
        self.thread.start()
        self.addCleanup(self.stop)
        self.token = self.server.local_connection.issue("https://viewer.example")

    def stop(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def request(self, path, method="GET", headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request(method, path, body, headers or {})
        result = conn.getresponse()
        answer = result.status, dict(result.getheaders()), result.read()
        conn.close()
        return answer

    def direct(self, **extra):
        return {"Origin": "https://viewer.example", "X-Studio-Local": self.token, **extra}

    def test_issuance_requires_owner_and_expected_public_host(self):
        for auth, host, expected in [("", "viewer.example", 403), ("owner", "other.example", 503), ("owner", "viewer.example", 200)]:
            status, headers, body = self.request("/api/local-connection", headers={"Host":host,"Cf-Access-Jwt-Assertion":auth})
            self.assertEqual(status, expected)
            if status == 200:
                data=json.loads(body)
                self.assertEqual(data["instance"],self.server.local_connection.instance)
                self.assertTrue(self.server.local_connection.valid(data["token"], "https://viewer.example"))
                self.assertEqual(headers["Cache-Control"],"no-store")

    def test_direct_probe_checks_origin_token_instance_and_tunnel(self):
        for changes, expected in [({},200), ({"X-Studio-Local":"bad"},403), ({"Origin":"https://evil.example"},403), ({"Cf-Ray":"tunnel"},403), ({"Host":"viewer.example"},403)]:
            status, headers, body=self.request("/bridge/probe",headers=self.direct(**changes))
            self.assertEqual(status,expected)
            if status==200:
                self.assertEqual(json.loads(body)["instance"],self.server.local_connection.instance)
                self.assertEqual(headers["Access-Control-Allow-Origin"],"https://viewer.example")
        self.assertEqual(self.request("/bridge/probe",headers={"Origin":"https://viewer.example"})[0],403)

    def test_expiry_restart_and_nonlocal_peer(self):
        bridge=self.server.local_connection
        with patch('server.local_connection.time.time',return_value=time.time()+301):
            self.assertEqual(self.request('/bridge/probe',headers=self.direct())[0],403)
        other=LocalConnection(bridge.config)
        self.assertFalse(other.valid(self.token,'https://viewer.example'))
        h=Message()
        for k,v in self.direct(Host=f'localhost:{self.server.server_port}').items():h[k]=v
        self.assertFalse(bridge.authorized('192.0.2.1',h,self.server.server_port))

    def test_preflight_narrow_origin_methods_headers_and_routes(self):
        h={'Origin':'https://viewer.example','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type,x-studio-local'}
        status,headers,_=self.request('/room/open','OPTIONS',h)
        self.assertEqual(status,204)
        self.assertEqual(headers['Access-Control-Allow-Private-Network'],'true')
        for changes in [{'Origin':'https://evil.example'},{'Cf-Ray':'tunnel'},{'Access-Control-Request-Method':'DELETE'},{'Access-Control-Request-Headers':'authorization'}]:
            self.assertEqual(self.request('/room/open','OPTIONS',dict(h,**changes))[0],403)
        self.assertEqual(self.request('/api/jobs','OPTIONS',h)[0],403)

    def test_commands_stay_direct_json_and_busy_close_is_rejected(self):
        h=self.direct(**{'Content-Type':'application/json'})
        self.assertEqual(self.request('/room/close','POST',h,'{}')[0],200)
        self.server.busy=True
        self.assertEqual(self.request('/room/close','POST',h,'{}')[0],409)
        self.server.busy=False
        for changes in [{'X-Studio-Local':'bad'},{'Content-Type':'text/plain'},{'Host':'viewer.example','Cf-Access-Jwt-Assertion':'owner'}]:
            self.assertEqual(self.request('/room/close','POST',dict(h,**changes),'{}')[0],403)

    def test_remote_room_get_denied_even_for_owner(self):
        self.assertEqual(self.request('/room/sing/',headers={'Host':'viewer.example','Cf-Access-Jwt-Assertion':'owner'})[0],403)
        self.assertEqual(self.request('/api/status',headers=self.direct())[0],200)
