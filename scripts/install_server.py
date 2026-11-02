"""Snapshot installer for the macOS socket-activated Studio server."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def loaded(job):
    return subprocess.run(['launchctl', 'print', job], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def request(port, route):
    # Local checks must never go through a configured HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{port}/api/{route}', timeout=10) as response:
        return json.load(response)


def require_idle(port, is_loaded):
    try:
        result = request(port, 'busy')
    except urllib.error.URLError as exc:
        # Only a refused connection with no registered job means first install.
        if not is_loaded and isinstance(exc.reason, ConnectionRefusedError):
            return
        raise RuntimeError('Cannot confirm server is idle; refusing to stop it.') from exc
    if not isinstance(result, dict) or result.get('busy') is not False:
        raise RuntimeError('Server is busy or returned an invalid busy response; refusing to stop it.')
    if not is_loaded:
        raise RuntimeError('Port is occupied by a server outside this launchd job; refusing install.')


def stop(job):
    run('launchctl', 'bootout', job)
    deadline = time.monotonic() + 5
    while loaded(job):
        if time.monotonic() >= deadline:
            raise RuntimeError('Job did not unload within five seconds; refusing bootstrap.')
        time.sleep(.1)


def absolute(name, default):
    return Path(os.environ.get(name, str(default))).expanduser().absolute()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    home = Path.home()
    share = absolute('STUDIO_SHARE', home / '.local/share/studio')
    label = os.environ.get('STUDIO_LABEL', 'com.rajeshgoli.studio-server')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', label):
        raise RuntimeError('STUDIO_LABEL must contain only letters, digits, dots, underscores or hyphens.')
    port = int(os.environ.get('STUDIO_PORT', '8450'))
    idle = float(os.environ.get('STUDIO_IDLE_EXIT_SECS', '3600'))
    if not 1 <= port <= 65535 or not 0 <= idle < float('inf'):
        raise RuntimeError('Invalid port or idle timeout.')
    plist = absolute('STUDIO_PLIST', home / f'Library/LaunchAgents/{label}.plist')
    content = absolute('STUDIO_CONTENT', home / 'projects/studio-content')
    domain = f'gui/{os.getuid()}'
    job = f'{domain}/{label}'
    share.mkdir(parents=True, exist_ok=True)
    # Serialize installers for this release store, including uninstall.
    with (share / '.install.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another installer is using this release store.')
        is_loaded = loaded(job)
        # Read the installed port so changing STUDIO_PORT cannot bypass busy.
        old_port = port
        if plist.exists():
            with plist.open('rb') as source:
                old = plistlib.load(source)
            if old.get('Label') != label:
                raise RuntimeError('Existing plist belongs to a different job.')
            old_port = int(old['Sockets']['http']['SockServiceName'])
        elif is_loaded:
            raise RuntimeError('Loaded job has no plist here; cannot safely determine its port.')
        require_idle(old_port, is_loaded)
        if args.uninstall:
            if is_loaded:
                print(f'Stopping {label} for uninstall.', flush=True)
                stop(job)
            if plist.exists():
                # Retire rather than destroy the previous configuration.
                archive = share / 'retired-plists'
                archive.mkdir(exist_ok=True)
                plist.replace(archive / f'{time.time_ns()}-{plist.name}')
            print(f'Uninstalled {label}; releases and logs remain in {share}')
            return
        if not content.is_dir():
            raise RuntimeError(f'Content checkout does not exist: {content}')
        if port != old_port:
            require_idle(port, False)
        sm = shutil.which('sm')
        if sm is None:
            raise RuntimeError('sm must be on PATH when installing.')
        run('git', '-C', str(root), 'fetch', 'origin', 'main')
        sha = subprocess.check_output(['git', '-C', str(root), 'rev-parse',
                                       'origin/main^{commit}'], text=True).strip()
        releases = share / 'releases'
        releases.mkdir(exist_ok=True)
        release = releases / sha
        marker = release / '.studio-install-complete'
        if release.exists() and not marker.exists():
            raise RuntimeError(f'Incomplete release exists at {release}; move it aside before retrying.')
        if not release.exists():
            release.mkdir()
            # Build at its final path: virtual environment scripts embed this path.
            archive = share / f'.archive-{os.getpid()}.tar'
            try:
                run('git', '-C', str(root), 'archive', '--format=tar', '-o', str(archive), sha)
                run('tar', '-xf', str(archive), '-C', str(release))
                run('uv', 'venv', str(release / '.venv'), '--python', '3.12')
                run('uv', 'pip', 'install', '--python', str(release / '.venv/bin/python'),
                    '-r', str(release / 'server/requirements.txt'))
                marker.touch()
            finally:
                if archive.exists():
                    archive.unlink()  # Created by this invocation only.
        logs = share / 'logs'
        logs.mkdir(exist_ok=True)
        spec = {
            'Label': label,
            'ProgramArguments': [str(release / '.venv/bin/python'), '-m', 'server',
                                 '--launchd-socket', 'http', '--idle-exit-secs', str(idle)],
            'WorkingDirectory': str(release),
            'EnvironmentVariables': {
                'HOME': str(home), 'STUDIO_CONTENT': str(content),
                'PATH': f'{Path(sm).parent}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'},
            'Sockets': {'http': {'SockNodeName': '127.0.0.1', 'SockServiceName': str(port),
                                 'SockType': 'stream'}},
            'StandardOutPath': str(logs / 'server.out.log'),
            'StandardErrorPath': str(logs / 'server.err.log'),
        }
        current = share / 'current'
        if current.exists() and not current.is_symlink():
            raise RuntimeError(f'{current} must be a symlink.')
        # Check again immediately before stopping: dependency installation may take minutes.
        is_loaded = loaded(job)
        require_idle(old_port, is_loaded)
        if is_loaded:
            print(f'Stopping idle {label} to install {sha}.', flush=True)
            stop(job)
        temporary = share / f'.current-{os.getpid()}'
        temporary.symlink_to(release)
        temporary.replace(current)
        plist.parent.mkdir(parents=True, exist_ok=True)
        temporary_plist = plist.with_name(f'.{plist.name}.{os.getpid()}')
        with temporary_plist.open('wb') as target:
            plistlib.dump(spec, target)
        temporary_plist.replace(plist)
        run('launchctl', 'bootstrap', domain, str(plist))
        status = request(port, 'status')
        if not isinstance(status, dict) or status.get('version') != 1 or type(status.get('busy')) is not bool:
            raise RuntimeError('Installed job did not return a valid Studio status.')
        marker.touch()
        complete = sorted((p for p in releases.iterdir()
                           if p.is_dir() and re.fullmatch('[0-9a-f]{40}', p.name)
                           and (p / '.studio-install-complete').is_file()),
                          key=lambda p: (p / '.studio-install-complete').stat().st_mtime,
                          reverse=True)
        # Keep three active releases; move older snapshots aside to preserve user files.
        for old_release in complete[3:]:
            if old_release == release:
                continue
            retired = share / 'retired-releases'
            retired.mkdir(exist_ok=True)
            old_release.rename(retired / f'{old_release.name}-{time.time_ns()}')
        print(f'Installed {sha}: http://127.0.0.1:{port}; idle exit after {idle:g}s')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f'Install failed: {error}')
