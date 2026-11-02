"""Disposable server with stand-in devices for the headless browser check."""
import json
import sys
import threading
from pathlib import Path
from talk.tests.test_room import TalkTest
from server.tests.test_rooms import Stream

fixture=TalkTest()
fixture.setUp()
stop_audio=threading.Event()
def feed_audio():
    while not stop_audio.wait(.01):
        for stream in list(Stream.instances):
            if stream.input and not stream.closed:
                stream.feed(480)
audio_thread=threading.Thread(target=feed_audio)
audio_thread.start()
try:
    for part in ('intro', 'body'):
        lines=fixture.folder/'script'/part/'lines.json'
        lines.write_text(lines.read_text().replace('First line', part+' first line'))
    config=fixture.root/'access.json'
    config.write_text(json.dumps({'public_origin':'https://viewer.example'}))
    fixture.server.local_connection.config=config
    fixture.server.access=lambda h: h.get('Cf-Access-Jwt-Assertion')=='browser-test-owner'
    print(json.dumps({'port':fixture.server.server_port}),flush=True)
    sys.stdin.read()
finally:
    stop_audio.set()
    audio_thread.join()
    fixture.doCleanups()
