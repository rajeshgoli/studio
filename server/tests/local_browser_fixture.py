"""Disposable server with stand-in devices for the headless browser check."""
import json
import sys
from pathlib import Path
from talk.tests.test_room import TalkTest

fixture=TalkTest()
fixture.setUp()
try:
    config=fixture.root/'access.json'
    config.write_text(json.dumps({'public_origin':'https://viewer.example'}))
    fixture.server.local_connection.config=config
    fixture.server.access=lambda h: h.get('Cf-Access-Jwt-Assertion')=='browser-test-owner'
    print(json.dumps({'port':fixture.server.server_port}),flush=True)
    sys.stdin.read()
finally:
    fixture.doCleanups()
