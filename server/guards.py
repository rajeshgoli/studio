"""Local-browser and Cloudflare Access request checks. Fail closed."""
import json
import re
from pathlib import Path


def single_header(headers, name):
    values = headers.get_all(name, [])
    return values[0] if len(values) == 1 else None


def local_guard(peer, headers, port):
    return (peer in {"127.0.0.1", "::1"}
            and single_header(headers, "Host") in {f"localhost:{port}", f"127.0.0.1:{port}"}
            and not any(name.lower().startswith("cf-") for name in headers))


def origin_guard(headers, port):
    """Require a same-host browser origin and a JSON request body."""
    host = single_header(headers, "Host")
    content_type = single_header(headers, "Content-Type")
    return (host in {f"localhost:{port}", f"127.0.0.1:{port}"}
            and single_header(headers, "Origin") == f"http://{host}"
            and content_type is not None
            and content_type.split(";", 1)[0].strip().lower() == "application/json")


class AccessGuard:
    def __init__(self, config_path=None):
        self.config_path = Path(config_path or "~/.config/studio/config.json").expanduser()
        self._clients = {}
        # PyJWKClient caches keys; serialize first creation across request threads.
        import threading
        self._lock = threading.Lock()

    def __call__(self, headers):
        token = single_header(headers, "Cf-Access-Jwt-Assertion")
        if not token:
            return False
        try:
            config = json.loads(self.config_path.read_text())
            team, audience, email = (config[k] for k in ("access_team", "access_aud", "owner_email"))
            if (not isinstance(team, str) or not re.fullmatch(r"[a-zA-Z0-9-]+", team)
                    or not isinstance(audience, str) or not audience
                    or not isinstance(email, str) or not email):
                return False
            import jwt
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                return False
            issuer = f"https://{team}.cloudflareaccess.com"
            with self._lock:
                if issuer not in self._clients:
                    self._clients = {issuer: jwt.PyJWKClient(
                        issuer + "/cdn-cgi/access/certs", timeout=5, lifespan=300)}
                client = self._clients[issuer]
            key = client.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=audience,
                                issuer=issuer, options={"require": ["exp", "iss", "aud", "email"]})
            return claims["email"] == email
        except Exception:
            # Configuration, unavailable keys, missing dependency, and bad tokens all deny access.
            return False


def access_guard(headers, verifier):
    return verifier(headers)
