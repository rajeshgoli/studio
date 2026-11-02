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
rehearsing, or transferring phone footage. Both recording rooms report their active stage; a phone download also keeps the server busy.

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
with an eight-file temporary disk cache keyed by the opened file's identity,
modification/change times, and size. Other media streams directly from disk.
The old singing studio imports
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
Origin matching the local Host and `Content-Type: application/json`.

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

The singing room opens locally with `POST /room/open` and a JSON body
`{"kind":"sing","production":"<song-id>"}`. Device names are read at open time
from `$STUDIO_CONTENT/studio.json`: `{"mic":"<microphone name>","ear":"<earbud name>"}`.
The page is `/room/sing/`; close it with `POST /room/close` and `{}` once idle.
All POSTs require `Content-Type: application/json` and an Origin matching the
local Host, including its port. Another open room or a listener on port 9400
prevents opening. Preview, recording and marking keep the server busy; closing
an idle room releases the devices and stops its background threads.
Take playback opens the validated file while holding the room lock, then converts
and streams it after releasing the lock. A slow playback client does not delay
recording controls; moving a take or closing the room cannot redirect that playback.

Room regression tests use stand-in streams, a temporary song and an ephemeral
local port, without touching hardware:
`python -m unittest server.tests.test_rooms`.


## Talking room

Open with `POST /room/open` and `{"kind":"talk","production":"<id>"}` from
localhost with the matching Origin header, then visit `/room/talk/`. Close with
`POST /room/close` and `{}`. A second room cannot open until the first closes.
An older recorder answering on port 9400 must be closed first.

The private `talks/<id>/production.json` supplies `script_dir`, `takes_dir`,
`parts`, `sessions` (named lists of parts), and `camera_parts`. Paths must remain
inside that production without symbolic links. Each script part contains
`lines.json` and optional `clips/NN_claude.wav`. Camera parts default to silent
output; audio parts use the configured earbud. Every take reloads the clips.
`studio.json` supplies `mic`, `ear`, and `phone` with `camera_package`,
`record_tap: [x,y]`, `dcim`, `preview_size: [width,height]`, and optional `serial`.

Read-only local routes are `state`, `outputs`, and `preview.jpg`. Actions use
JSON POST bodies: `step {dir: 1 or -1}`, `part {name}`, `ear {name}`,
`start {line}` (zero-based), `rehearse {on: boolean}`, and `abort`, `beep`,
`rescan` with `{}`. Rehearsal runs the prompter without writing files or tapping
the camera. With no connected phone, the camera preview shows “No phone
connected”; starting a camera recording gives a clean “no phone” message.

Full and strip prompter modes, mirror, and browser preferences are retained.
Takes keep per-line positions counted in recorded mic samples. Existing take
files are never overwritten. If a phone pull fails, mic audio and line timings
remain saved and the page reports the error.

Focused hardware-free checks: `python -m unittest talk.tests.test_room -v`.
A real camera take still needs the owner at the Mac; do not automate playback.


## Recording from the public viewer

The public viewer can connect directly to the recording Mac without changing the
browser address. Add `"public_origin": "https://studio.example.com"` to the private
server configuration, using the exact HTTPS viewer origin (no trailing slash).
After owner authentication, `/api/local-connection` issues a credential valid for
five minutes and the current server instance identifier. The page probes
`http://localhost:<port>/bridge/probe` and requires the same instance before
enabling **Open singing room** or **Open talking room**. The browser may ask for
local-network permission. No OS detection is used; a failed probe leaves the viewer
available with a retry button. The direct localhost entry continues to work.

Recording HTML, commands, state, camera preview and take playback go over the
loopback connection, with the credential in `X-Studio-Local`, never in URLs.
The room page is displayed in an embedded frame under the viewer's origin. Its
requests use the parent's direct transport; camera images and requested take audio
use temporary browser blob URLs. Loading take playback does not start playback.
Credentials refresh while the page is in use. Commands are never automatically
retried after a network failure, because the first command might have succeeded.

The direct route requires a loopback peer, exact local Host, no Cloudflare headers,
the configured public Origin, and a valid origin-bound credential. POST still
requires JSON. Preflights allow only GET/POST and Content-Type/X-Studio-Local on
room, status and probe routes. Public tunnel requests cannot control rooms, even
with a credential. Closing a busy room remains forbidden.

Checks: `python -m unittest server.tests.test_local_connection` and
`node server/tests/test_local_browser.cjs` (requires Playwright; optionally set
`PLAYWRIGHT_MODULE` and `STUDIO_TEST_PYTHON`). Browser checks use disposable content
and stand-in devices, verify both rooms under an HTTPS viewer origin, simulate an
unreachable local server, and confirm no recording command uses the public route.
