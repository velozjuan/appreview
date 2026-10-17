#!/usr/bin/env python3
"""Minimal, read-only App Store Connect API client.

- Signs ES256 JWTs from an App Store Connect API key (.p8). Supports team keys
  (issuer ID) and individual keys (no issuer ID, `sub: user`).
- Exposes GET requests only. There is deliberately no way to POST/PATCH/DELETE,
  so nothing in this skill can change an account.
- Never prints or logs the key or the token.

Credentials come from environment variables (never from chat):
    ASC_KEY_ID              required  e.g. 2X9R4HXF34
    ASC_ISSUER_ID           team keys only (omit for an individual key)
    ASC_PRIVATE_KEY_PATH    path to AuthKey_<KEY_ID>.p8
    ASC_PRIVATE_KEY         alternative: the PEM contents themselves
    ASC_BASE_URL            optional override (used by selftest.py)

If neither key variable is set, the usual Apple locations are searched for
AuthKey_<KEY_ID>.p8: ./private_keys, ~/private_keys, ~/.private_keys,
~/.appstoreconnect/private_keys.

Requires: Python 3.9+. Signing uses the `cryptography` package if it's installed,
otherwise the `openssl` command that ships with macOS and most Linux systems, so nothing
extra has to be installed. Set APPREVIEW_SIGNER=openssl or =cryptography to force one.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional

DEFAULT_BASE_URL = "https://api.appstoreconnect.apple.com"
AUDIENCE = "appstoreconnect-v1"
MAX_LIFETIME_SECONDS = 20 * 60  # Apple rejects longer-lived tokens for these endpoints
REFRESH_AFTER_SECONDS = 15 * 60


class AscConfigError(Exception):
    """Missing or unreadable credentials."""


class AscApiError(Exception):
    """The API answered with an error status."""

    def __init__(self, status: int, errors: List[Dict[str, Any]], url: str):
        self.status = status
        self.errors = errors
        self.url = url
        detail = "; ".join(
            f"{e.get('title', '')}: {e.get('detail', '')}".strip(": ") for e in errors
        )
        super().__init__(f"HTTP {status} for {url} - {detail or 'no error body'}")

    def hint(self) -> str:
        if self.status == 0 and ("Tunnel connection failed" in str(self) or "403" in str(self)):
            return (
                "The network here blocks api.appstoreconnect.apple.com (a proxy allowlist, not "
                "Apple). Run the scripts in a normal Terminal on the user's computer, ask the "
                "user to allow that domain, or switch to browser mode."
            )
        if self.status == 401:
            return (
                "401 means the token was refused. Check ASC_KEY_ID, ASC_ISSUER_ID (team "
                "keys only; omit it for an individual key), that the .p8 matches the key "
                "ID, that the key is not revoked, and that this machine's clock is correct."
            )
        if self.status == 403:
            return (
                "403 means the key's role cannot read this resource. Use a key with the "
                "App Manager or Admin role, or one with access to the app."
            )
        if self.status == 404:
            return "404 means the resource does not exist or the key cannot see it."
        if self.status == 409:
            return (
                "409: the resource is in a state that blocks this call (reported for "
                "submissions sitting in Unresolved Issues)."
            )
        if self.status == 429:
            return "429: rate limit hit. Wait a few minutes and retry."
        return ""


@dataclass
class Credentials:
    key_id: str
    private_key_pem: bytes
    issuer_id: Optional[str] = None  # None => individual key
    key_path: Optional[Path] = None  # set when the key came from a file


def _search_key_file(key_id: str) -> Optional[Path]:
    home = Path.home()
    candidates = [
        Path.cwd() / "private_keys",
        home / "private_keys",
        home / ".private_keys",
        home / ".appstoreconnect" / "private_keys",
    ]
    for folder in candidates:
        p = folder / f"AuthKey_{key_id}.p8"
        if p.is_file():
            return p
    return None


def load_credentials(env: Mapping[str, str] = os.environ) -> Credentials:
    key_id = (env.get("ASC_KEY_ID") or "").strip()
    if not key_id:
        raise AscConfigError(
            "ASC_KEY_ID is not set. Set ASC_KEY_ID (and ASC_ISSUER_ID for a team key) "
            "plus ASC_PRIVATE_KEY_PATH in your shell. Do not paste the .p8 into chat."
        )
    issuer = (env.get("ASC_ISSUER_ID") or "").strip() or None

    pem_text = env.get("ASC_PRIVATE_KEY")
    path = None
    if pem_text:
        pem = pem_text.replace("\\n", "\n").encode()
    else:
        path_str = (env.get("ASC_PRIVATE_KEY_PATH") or "").strip()
        path = Path(path_str).expanduser() if path_str else _search_key_file(key_id)
        if path is None or not path.is_file():
            raise AscConfigError(
                "Private key not found. Set ASC_PRIVATE_KEY_PATH to your AuthKey_"
                f"{key_id}.p8 file (or put it in ~/.appstoreconnect/private_keys/)."
            )
        pem = path.read_bytes()
    if b"PRIVATE KEY" not in pem:
        raise AscConfigError("The private key file does not look like a PEM .p8 key.")
    return Credentials(key_id=key_id, private_key_pem=pem, issuer_id=issuer, key_path=path)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _der_ecdsa_to_raw(der: bytes) -> bytes:
    """ECDSA signature: DER SEQUENCE{INTEGER r, INTEGER s} -> 64-byte r||s (JWT ES256)."""
    def read_len(buf: bytes, i: int):
        n = buf[i]; i += 1
        if n & 0x80:
            k = n & 0x7F
            n = int.from_bytes(buf[i:i + k], "big"); i += k
        return n, i
    if not der or der[0] != 0x30:
        raise AscConfigError("Unexpected signature format from openssl.")
    _, i = read_len(der, 1)
    out = b""
    for _ in range(2):
        if der[i] != 0x02:
            raise AscConfigError("Unexpected signature format from openssl.")
        n, i = read_len(der, i + 1)
        val = der[i:i + n].lstrip(b"\x00"); i += n
        if len(val) > 32:
            raise AscConfigError("The key is not a P-256 key.")
        out += val.rjust(32, b"\x00")
    return out


def _sign_with_cryptography(pem: bytes, data: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise AscConfigError("The key is not an EC (P-256) private key.")
    r, s = decode_dss_signature(key.sign(data, ec.ECDSA(hashes.SHA256())))
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def _sign_with_openssl(creds: Credentials, data: bytes) -> bytes:
    openssl = shutil.which("openssl")
    if not openssl:
        raise AscConfigError(
            "Can't sign the API key: neither the 'cryptography' package nor the 'openssl' "
            "command is available. Install one (pip install cryptography)."
        )
    tmpdir = None
    key_file = creds.key_path
    try:
        if key_file is None:  # key given as text: write it to a private temp file briefly
            tmpdir = tempfile.mkdtemp(prefix="appreview-")
            os.chmod(tmpdir, 0o700)
            key_file = Path(tmpdir) / "key.p8"
            fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(creds.private_key_pem)
        proc = subprocess.run([openssl, "dgst", "-sha256", "-sign", str(key_file)],
                              input=data, capture_output=True, timeout=30)
        if proc.returncode != 0 or not proc.stdout:
            raise AscConfigError("openssl couldn't sign with this key. Check that the .p8 file "
                                 "is the one downloaded from App Store Connect.")
        return _der_ecdsa_to_raw(proc.stdout)
    finally:
        if tmpdir:
            for f in Path(tmpdir).iterdir():
                f.unlink()
            os.rmdir(tmpdir)


def signer_name() -> str:
    forced = (os.environ.get("APPREVIEW_SIGNER") or "").strip().lower()
    if forced in ("openssl", "cryptography"):
        return forced
    try:
        import cryptography  # noqa: F401
        return "cryptography"
    except ImportError:
        return "openssl"


def make_token(creds: Credentials, lifetime: int = MAX_LIFETIME_SECONDS,
               now: Optional[float] = None) -> str:
    """Return a signed ES256 JWT. The signature is raw r||s as JWT requires."""
    lifetime = max(60, min(int(lifetime), MAX_LIFETIME_SECONDS))
    iat = int(now if now is not None else time.time())
    header = {"alg": "ES256", "kid": creds.key_id, "typ": "JWT"}
    payload: Dict[str, Any] = {"iat": iat, "exp": iat + lifetime, "aud": AUDIENCE}
    if creds.issuer_id:
        payload["iss"] = creds.issuer_id
    else:
        payload["sub"] = "user"  # individual API keys

    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    ).encode()

    if signer_name() == "cryptography":
        try:
            signature = _sign_with_cryptography(creds.private_key_pem, signing_input)
        except ImportError as exc:
            raise AscConfigError("APPREVIEW_SIGNER=cryptography but the package isn't installed.") from exc
    else:
        signature = _sign_with_openssl(creds, signing_input)
    return signing_input.decode() + "." + _b64url(signature)


class AscClient:
    """Read-only client with pagination, retries and token refresh."""

    def __init__(self, creds: Credentials, base_url: Optional[str] = None,
                 timeout: int = 30, max_retries: int = 3):
        self.creds = creds
        self.base_url = (base_url or os.environ.get("ASC_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._token: Optional[str] = None
        self._token_time = 0.0
        self.request_count = 0

    # -- auth ---------------------------------------------------------------
    def _auth_header(self) -> Dict[str, str]:
        if not self._token or time.time() - self._token_time > REFRESH_AFTER_SECONDS:
            self._token = make_token(self.creds)
            self._token_time = time.time()
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    # -- requests -----------------------------------------------------------
    def _url(self, path_or_url: str, params: Optional[Mapping[str, Any]]) -> str:
        if path_or_url.startswith("http"):
            # Only ever send the token to the configured API host. A `links.next`
            # pointing elsewhere must not receive our credentials.
            want = urllib.parse.urlsplit(self.base_url).netloc
            got = urllib.parse.urlsplit(path_or_url).netloc
            if want != got:
                raise AscApiError(0, [{"title": "Blocked", "detail": f"Refusing to call {got}"}], path_or_url)
            url = path_or_url
        else:
            url = self.base_url + (path_or_url if path_or_url.startswith("/") else "/" + path_or_url)
        if params:
            q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, safe=",[]")
            url += ("&" if "?" in url else "?") + q
        return url

    def get(self, path_or_url: str, params: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        url = self._url(path_or_url, params)
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, headers=self._auth_header(), method="GET")
            self.request_count += 1
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read()
                    return json.loads(body) if body else {}
            except urllib.error.HTTPError as err:
                raw = err.read()
                try:
                    errors = json.loads(raw).get("errors", []) if raw else []
                except ValueError:
                    errors = []
                retriable = err.code == 429 or 500 <= err.code < 600
                if retriable and attempt < self.max_retries:
                    wait = err.headers.get("Retry-After")
                    time.sleep(min(float(wait), 60) if wait and wait.isdigit() else 2 ** attempt)
                    continue
                raise AscApiError(err.code, errors, url) from None
            except (urllib.error.URLError, TimeoutError) as err:
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise AscApiError(0, [{"title": "Network error", "detail": str(err)}], url) from None
        raise AscApiError(0, [{"title": "Unreachable"}], url)  # pragma: no cover

    def paginate(self, path: str, params: Optional[Mapping[str, Any]] = None,
                 max_pages: int = 50) -> Iterator[Dict[str, Any]]:
        """Yield each page's full JSON body, following `links.next`."""
        page = self.get(path, params)
        yield page
        pages = 1
        while page.get("links", {}).get("next") and pages < max_pages:
            page = self.get(page["links"]["next"])
            pages += 1
            yield page

    def collect(self, path: str, params: Optional[Mapping[str, Any]] = None):
        """Return (all data rows, all included resources) across pages."""
        data: List[Dict[str, Any]] = []
        included: List[Dict[str, Any]] = []
        for page in self.paginate(path, params):
            data.extend(page.get("data", []))
            included.extend(page.get("included", []))
        return data, included


def client_from_env() -> AscClient:
    return AscClient(load_credentials())


if __name__ == "__main__":
    # Quick credential check: lists the first few apps.
    try:
        c = client_from_env()
        rows, _ = c.collect("/v1/apps", {"limit": 5})
        print(f"OK: authenticated. Sample apps: {[r['attributes'].get('name') for r in rows]}")
    except AscConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(2)
    except AscApiError as e:
        print(f"{e}\n{e.hint()}", file=sys.stderr)
        sys.exit(3)
