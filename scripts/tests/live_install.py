"""Run via sm queue on macOS; uses a dedicated label, port and build directory."""
import json
import os
from pathlib import Path
import plistlib
import subprocess
import time
import urllib.request

root = Path(__file__).resolve().parents[2]
store = root / 'build/install-test'
plist = store / 'test.plist'
label = 'com.rajeshgoli.studio-test-2'
job = f'gui/{os.getuid()}/{label}'
env = dict(os.environ, STUDIO_PORT='18452', STUDIO_LABEL=label,
           STUDIO_SHARE=str(store), STUDIO_PLIST=str(plist), STUDIO_IDLE_EXIT_SECS='2')


def install(*args, success=True):
    result = subprocess.run(['bash', 'scripts/install-server.sh', *args], cwd=root, env=env,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, flush=True)
    assert (result.returncode == 0) == success, result.stdout
    return result.stdout


def state():
    return subprocess.check_output(['launchctl', 'print', job], text=True)


def request(route):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:18452/api/{route}', timeout=15) as response:
        return json.load(response)


install()
time.sleep(4)
assert 'state = not running' in state()
assert request('status')['version'] == 1
assert 'state = running' in state()
print('PASS: idle exit and socket wake', flush=True)
# Use a test-only entry point to put the real server in a busy state. No public
# mutation route is added, and the installed snapshot remains unchanged.
assert request('busy') == {'busy': False}
subprocess.run(['launchctl', 'bootout', job], check=True)
for _ in range(50):
    if subprocess.run(['launchctl', 'print', job], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode:
        break
    time.sleep(.1)
with plist.open('rb') as source:
    spec = plistlib.load(source)
busy_file = store / 'busy-fixture'
busy_file.touch()
fixture = '''
from pathlib import Path
import threading, time
from server.app import StudioServer
from server.launchd import activate_socket
s = StudioServer(('127.0.0.1', 18452), listener=activate_socket('http'), idle_exit_secs=2)
s.busy = True
def watch():
    while Path(%r).exists(): time.sleep(.1)
    s.busy = False
threading.Thread(target=watch, daemon=True).start()
s.serve_forever(poll_interval=.1)
''' % str(busy_file)
spec['ProgramArguments'] = [spec['ProgramArguments'][0], '-c', fixture]
with plist.open('wb') as target:
    plistlib.dump(spec, target)
subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(plist)], check=True)
try:
    assert request('busy') == {'busy': True}
    before = plist.read_bytes()
    for args in ((), ('--uninstall',)):
        assert 'busy' in install(*args, success=False)
        assert plist.read_bytes() == before
        assert request('busy') == {'busy': True}
    print('PASS: install and uninstall refuse a live busy server', flush=True)
finally:
    busy_file.unlink()
    time.sleep(.3)
    install('--uninstall')
assert not plist.exists()
assert (store / 'logs/server.out.log').exists()
print('PASS: uninstall unloads job, retires plist and retains logs', flush=True)
