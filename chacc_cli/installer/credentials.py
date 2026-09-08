"""
Credential resolution and redaction for ``chacc install``.

The CLI never persists credentials. It only:
- looks up a token in environment variables,
- rewrites the URL in-memory (git receives the rewritten URL via argv),
- redacts any URL or token before it reaches stdout/stderr/logs.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse, urlunparse

HOST_TOKEN_ENV: dict[str, str] = {
    "github.com": "GITHUB_TOKEN",
    "gitlab.com": "GITLAB_TOKEN",
    "bitbucket.org": "BITBUCKET_TOKEN",
}

GENERIC_TOKEN_ENV = "CHACC_GIT_TOKEN"


def classify(url: str) -> str:
    """Return one of: ``"ssh"``, ``"https-with-creds"``, ``"https"``, ``"other"``."""
    if url.startswith(("git@", "ssh://")):
        return "ssh"
    if url.startswith(("http://", "https://")):
        # path part is roughly /segments; check for user:token@
        parts = url.split("/", 3)
        if len(parts) >= 4 and "@" in parts[2]:
            return "https-with-creds"
        return "https"
    return "other"


def lookup_token(url: str, override_env: str | None = None) -> str | None:
    """
    Find a token in the environment for the given URL.

    Order:
    1. ``override_env`` (the ``--token-env`` flag) if set.
    2. Host-specific var (``GITHUB_TOKEN`` for github.com, etc.).
    3. ``CHACC_GIT_TOKEN`` (generic fallback).
    """
    if override_env:
        value = os.environ.get(override_env)
        if value:
            return value

    kind = classify(url)
    if kind in ("ssh", "https-with-creds", "other"):
        return os.environ.get(GENERIC_TOKEN_ENV) or None

    host = (urlparse(url).hostname or "").lower()
    var = HOST_TOKEN_ENV.get(host, GENERIC_TOKEN_ENV)
    return os.environ.get(var) or None


def inject_token(url: str, token: str) -> str:
    """Return ``url`` with the token embedded in the userinfo section."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(netloc=f"{token}@{parsed.netloc}"))


def redact_url(url: str) -> str:
    """Hide the userinfo of an http(s) URL. SSH and other URLs pass through."""
    if not url.startswith(("http://", "https://")):
        return url
    parsed = urlparse(url)
    if "@" not in parsed.netloc:
        return url
    host = parsed.netloc.split("@", 1)[1]
    return urlunparse(parsed._replace(netloc=f"***@{host}"))


def scrub_token(value: str, token: str | None) -> str:
    """Replace any occurrence of ``token`` in ``value`` with ``***``."""
    if not token or not value:
        return value
    return value.replace(token, "***")


def is_tty() -> bool:
    return bool(sys.stdin.isatty())
