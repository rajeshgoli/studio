# Studio server core

Run from the repository root with Python 3.12:

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r server/requirements.txt
STUDIO_CONTENT=/absolute/path/to/studio-content .venv/bin/python -m server --port 18450
```

Development uses an unused port, not the installed server's 8450. The default
content checkout is `../studio-content` relative to the repository. Set
`STUDIO_CONTENT` explicitly in worktrees and installed snapshots.

`--launchd-socket http` adopts macOS's named listening socket instead of binding
a port. `--idle-exit-secs 3600` exits after a quiet hour; zero disables idle exit.
Accepted connections count as in flight until the response finishes. A stalled
connection has a 15-second socket timeout. The synchronized `server.busy` flag
prevents idle exit; future rooms must set it while recording, previewing, marking,
rehearsing, or transferring phone footage. There are no rooms in this package yet.

## Routes

- `GET /`: productions with newest render and recording-room status.
- `GET /song/<id>` and `/api/song/<id>`: lines, takes, marks, line times, renders,
  images, and publishing text. Copy buttons copy the title/description sections.
- `GET /jobs` and `/api/jobs`: the newest 50 sm queue jobs; studio prefixes are
  selected by default, with a show-all switch.
- `GET /api/jobs/<job>/log`: last 200 lines for a job in the fresh queue list.
  Commands use argument lists, a ten-second timeout, and no shell. Queue failures
  return 503; unknown jobs return 404.
- `GET /api/productions`: songs with `poem.json`, returning `id`, `kind`, `title`, `newest_render`.
- `GET /api/status`: protocol version, room (`null`), stage (`idle`), busy flag.
- `GET /api/busy`: `{"busy": false}` until a future room sets the flag.
- `GET /file/<id>/<path>`: allowed production files, with HTTP byte ranges.

File paths are relative to `songs/<id>/`, except `build/<path>` maps to
`studio-content/build/<id>/<path>`. At the song's top level, only `vocals.wav`,
`poem.json`, `marks.json`, `timing.json`, and `youtube.md` are served. Direct files
in `takes/` and `reference/`, and build files at the top level, in `options/`, or
in `thumbnails/` are allowed. Extensions are `.wav .mp3 .m4a .mp4 .png .jpg .json
.md`. Both the requested path and the resolved link target must pass this policy.
Hidden paths, deleted takes, intermediate build folders, and escapes are denied.

WAV files are converted to 16-bit samples for browser compatibility, in chunks,
with an eight-file temporary disk cache keyed by resolved path, modification time,
and size. Other media streams directly from disk. The old singing studio imports
`playable` and `_send_audio` from this package and retains its existing launcher.

## Access configuration

Local access requires a loopback peer, exactly `localhost:<port>` or
`127.0.0.1:<port>` as Host, and no `Cf-*` headers. Other requests require a verified
Cloudflare Access signed token. Configure `~/.config/studio/config.json` with
`access_team` (team slug), `access_aud` (audience tag), and `owner_email`.
Missing or invalid settings deny non-local access. Keys are fetched from the
team's HTTPS certificate endpoint and cached for five minutes. Signature
algorithm, issuer, audience, expiry, and email must all match.

Room paths require local access even with a valid token. POST also requires an
Origin matching the local Host and `Content-Type: application/json`; since no
mutating routes exist yet, a POST passing the guards returns 404.

## Checks

```sh
.venv/bin/python -m unittest discover -s server/tests -v
```

Tests use temporary content and ephemeral loopback ports, generated RSA signing
keys, and a mocked HTTPS key response. They cover local and token guards, POST
checks, file escapes and links, byte ranges, WAV conversion/cache invalidation,
idle/busy/in-flight behavior, lazy imports, and launchd socket adoption.

## Installed server (macOS)

Run `scripts/install-server.sh` from a checkout. It fetches `origin/main`, archives
that commit into `~/.local/share/studio/releases/<sha>`, and installs Python 3.12
and the requirements with `uv`. Uncommitted files and the current branch are not
installed. `python3`, `uv`, `git`, and `sm` must be on PATH.

The `com.rajeshgoli.studio-server` LaunchAgent listens on `127.0.0.1:8450` and
starts Python when a request arrives. It exits after an hour without requests.
The installer checks `/api/busy` before stopping a job, including during
`--uninstall`; busy, malformed, or unreachable responses from a loaded job refuse
the operation. There is no force option. The check is repeated after preparing
the release. Avoid starting a recording during an installation: the busy check
and launchd stopping the process are separate operations.

Overrides: `STUDIO_PORT`, `STUDIO_LABEL`, `STUDIO_SHARE` (release store and logs),
`STUDIO_PLIST` (full plist path), `STUDIO_CONTENT` (default
`~/projects/studio-content`), `STUDIO_IDLE_EXIT_SECS`, and `STUDIO_INSTALL_PYTHON`
(the Python executable used by the installer). Use a distinct port, label, share,
and plist for testing. An existing plist supplies the old port during an update.

`current` is switched by an atomic rename. The three most recently installed
complete releases stay in `releases`; older ones move to `retired-releases` so no
user files are deleted. An interrupted dependency install leaves an incomplete
release: move it aside before retrying. Failed activation is reported, with logs
in `STUDIO_SHARE/logs/server.{out,err}.log` available for diagnosis.
`--uninstall` unloads the job and moves its plist to `retired-plists`; releases and
logs remain. The first microphone use from the installed Python may require the
owner to allow microphone access in System Settings (checked by the singing-room
ticket).

Installer safety tests: `python3 -m unittest discover -s scripts/tests -v`.

Viewer pages poll no faster than once per second while visible, skip unchanged
sections, and use native media controls with `preload="none"`. Takes are marked
in use when their file size matches both vocals.wav and marks.json vocals_bytes;
this follows the recording format, rather than claiming a byte-for-byte identity.
Missing optional files display empty sections. All metadata reads follow the same
file allowlist and symlink checks as media.
