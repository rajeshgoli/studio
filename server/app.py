"""Read-only routes and lifecycle. Rooms will extend this foundation later."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from .guards import AccessGuard, access_guard, local_guard, origin_guard
from .media import send_file
from .productions import Productions
from .jobs import Jobs, QueueUnavailable
from .viewer import page, song


class StudioServer(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, address=("127.0.0.1", 8450), *, content=None, config=None,
                 idle_exit_secs=3600, listener=None):
        self.productions = Productions(content)
        self.jobs = Jobs()
        self.access = AccessGuard(config)
        self.idle_exit_secs = idle_exit_secs
        self._lock = threading.Lock()
        self._busy = False
        self._in_flight = 0
        self._last_request = time.monotonic()
        self._stopping = False
        super().__init__(address, Handler, bind_and_activate=listener is None)
        if listener is not None:
            self.socket.close()
            self.socket = listener
            self.server_address = listener.getsockname()
            self.server_name, self.server_port = self.server_address[:2]

    @property
    def busy(self):
        with self._lock:
            return self._busy

    @busy.setter
    def busy(self, value):
        with self._lock:
            if self._stopping and value:
                raise RuntimeError("server is stopping")
            self._busy = bool(value)
            self._last_request = time.monotonic()

    def process_request(self, request, client_address):
        # Count before spawning: idle shutdown must not race a newly accepted request.
        with self._lock:
            if self._stopping:
                self.shutdown_request(request)
                return
            self._in_flight += 1
            self._last_request = time.monotonic()
        try:
            super().process_request(request, client_address)
        except Exception:
            self._finished_request()
            raise

    def _finished_request(self):
        with self._lock:
            self._in_flight -= 1
            self._last_request = time.monotonic()

    def process_request_thread(self, request, client_address):
        try:
            # A stalled connection must not keep the server alive forever.
            request.settimeout(15)
            super().process_request_thread(request, client_address)
        finally:
            self._finished_request()

    def service_actions(self):
        if self.idle_exit_secs <= 0:
            return
        with self._lock:
            if (self._stopping or self._busy or self._in_flight
                    or time.monotonic() - self._last_request < self.idle_exit_secs):
                return
            self._stopping = True
        # shutdown() must run outside the serve_forever thread.
        threading.Thread(target=self.shutdown, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def _send(self, data, ctype="application/json", status=200):
        body = json.dumps(data).encode() if ctype == "application/json" else data.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self, local_only=False):
        local = local_guard(self.client_address[0], self.headers, self.server.server_port)
        if local or (not local_only and access_guard(self.headers, self.server.access)):
            return True
        self._send({"error": "forbidden"}, status=403)
        return False

    def do_GET(self):
        path = urlsplit(self.path).path
        if not self._authorized(local_only=path.startswith("/room/")):
            return
        try:
            if path in {"/api/status", "/api/busy"}:
                result = {"busy": self.server.busy}
                if path == "/api/status":
                    result.update(version=1, room=None, stage="idle")
                self._send(result)
            elif path == "/api/productions":
                self._send(self.server.productions.list())
            elif path in {"/", "/jobs"}:
                self._send(page(), "text/html; charset=utf-8")
            elif path.startswith("/song/"):
                self.server.productions.song_dir(unquote(path[len("/song/"):]))
                self._send(page(), "text/html; charset=utf-8")
            elif path.startswith("/api/song/"):
                self._send(song(self.server.productions, unquote(path[len("/api/song/"):])))
            elif path == "/api/jobs":
                self._send(self.server.jobs.list())
            elif path.startswith("/api/jobs/") and path.endswith("/log"):
                job = unquote(path[len("/api/jobs/"):-len("/log")])
                self._send({"log": self.server.jobs.log(job)})
            elif path.startswith("/file/"):
                pid, relative = unquote(path[len("/file/"):], errors="strict").split("/", 1)
                send_file(self, self.server.productions.file(pid, relative))
            else:
                self._send({"error": "not found"}, status=404)
        except QueueUnavailable as exc:
            self._send({"error": str(exc)}, status=503)
        except (OSError, ValueError, UnicodeError):
            self._send({"error": "not found"}, status=404)

    def do_POST(self):
        if not self._authorized(local_only=True):
            return
        if not origin_guard(self.headers, self.server.server_port):
            self._send({"error": "forbidden"}, status=403)
            return
        self._send({"error": "not found"}, status=404)
