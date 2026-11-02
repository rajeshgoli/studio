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

- `GET /`: plain song list (no per-song viewer yet).
- `GET /api/productions`: songs with `poem.json`, returning `id`, `kind`, `title`.
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
