"""Serve recorded API responses instead of the network (tests, and offline runs).

A replay directory holds manifest.json and the bodies it names. Each entry matches a
request exactly (method, URL and query, the `api_key` left out and the query sorted) or
by prefix (method, scheme, host and path only: "any FRED observations call"). A request
nothing matches gets HTTP 404 "no fixture" and is listed in `misses`, so a test can tell
an unexpected request from a recorded one. It never opens a socket.

Set SIGNALS_REPLAY_DIR to make `python -m app.cli signals-*` replay instead of fetching.
"""

import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

SECRET_PARAMS = {"api_key"}


def canonical(method: str, url: str) -> str:
    parts = urlsplit(url)
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in SECRET_PARAMS)
    return f"{method.upper()} {parts.scheme}://{parts.netloc}{parts.path}" + (f"?{urlencode(query)}" if query else "")


def prefix_of(method: str, url: str) -> str:
    parts = urlsplit(url)
    return f"{method.upper()} {parts.scheme}://{parts.netloc}{parts.path}"


class ReplayTransport(httpx.BaseTransport):
    def __init__(self, directory: Path | str):
        self.directory = Path(directory)
        manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        self.exact = {e["request"]: e for e in manifest["responses"] if e.get("match", "exact") == "exact"}
        self.prefix = {e["request"]: e for e in manifest["responses"] if e.get("match") == "prefix"}
        self.misses: list[str] = []
        self.served: list[str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        key = canonical(request.method, str(request.url))
        entry = self.exact.get(key) or self.prefix.get(prefix_of(request.method, str(request.url)))
        if entry is None:
            self.misses.append(key)
            return httpx.Response(404, text=f"no fixture for {key}", request=request)
        self.served.append(key)
        body = (self.directory / entry["file"]).read_bytes() if entry.get("file") else b""
        return httpx.Response(entry["status"], content=body, request=request,
                              headers={"Content-Type": entry.get("content_type", "application/json")})
