"""Short-lived, origin-bound credentials for a direct loopback connection."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlsplit
from .guards import local_guard, single_header


class LocalConnection:
    def __init__(self, config):
        self.config = config
        self.secret = secrets.token_bytes(32)
        self.instance = secrets.token_urlsafe(24)

    def origin(self):
        try:
            value = json.loads(self.config.read_text())["public_origin"]
            parsed = urlsplit(value)
            if parsed.scheme == "https" and parsed.netloc and value == "https://" + parsed.netloc and not parsed.username and not parsed.password:
                return value
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def issue(self, origin):
        payload = base64.urlsafe_b64encode(json.dumps([origin, time.time() + 300]).encode()).decode()
        signature = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
        return payload + "." + signature

    def valid(self, token, origin):
        try:
            payload, signature = token.split(".")
            expected = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                return False
            bound, expiry = json.loads(base64.urlsafe_b64decode(payload))
            return bound == origin and time.time() < expiry
        except (ValueError, TypeError, AttributeError):
            return False

    def route(self, peer, headers, port):
        origin = self.origin()
        return bool(origin and local_guard(peer, headers, port)
                    and single_header(headers, "Origin") == origin)

    def authorized(self, peer, headers, port):
        return self.route(peer, headers, port) and self.valid(
            single_header(headers, "X-Studio-Local"), self.origin())
