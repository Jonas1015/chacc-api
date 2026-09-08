"""
URL classification, inline-ref parsing, and git fetch for ``chacc install``.

Source forms accepted (in this strict order):

1. Local path - ``os.path.exists(source)`` is true.
2. Explicit URL - starts with ``http://``, ``https://``, ``ssh://``, or ``git@``.
3. Short form - matches ``^\\w[\\w.-]*/[\\w.-]+$``, resolved to github.com.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from urllib.parse import urlparse

from . import credentials

SHORT_FORM_RE = re.compile(r"^[\w][\w.-]*/[\w.-]+$")


class SourceError(Exception):
    """Raised for any user-facing source resolution problem."""


@dataclass
class ResolvedSource:
    """Result of turning a user-typed string into something we can install."""

    kind: str  # "local" | "git"
    path: str  # absolute path to a directory holding module_meta.json
    origin_url: str | None = None  # the original (possibly redacted) URL, for logging
    cleanup: bool = True  # whether the caller should remove ``path`` on exit


def split_source_and_ref(source: str) -> tuple[str, str | None]:
    """
    Split ``owner/repo@main`` into ``("owner/repo", "main")``.

    SSH (``git@github.com:...``) and HTTPS-with-creds (``https://x:y@...``)
    URLs are returned as-is with no ref.
    """
    if source.startswith(("git@", "ssh://")):
        return source, None
    if (
        source.startswith(("http://", "https://"))
        and credentials.classify(source) == "https-with-creds"
    ):
        return source, None
    if "@" in source:
        src, ref = source.rsplit("@", 1)
        return src, ref
    return source, None


def classify_source(source: str) -> str:
    """Return ``"local"``, ``"url"``, or ``"short"``."""
    if os.path.exists(source):
        return "local"
    if source.startswith(("http://", "https://", "ssh://", "git@")):
        return "url"
    if SHORT_FORM_RE.match(source):
        return "short"
    raise SourceError(
        f"Source '{source}' is not a local path, a recognized URL, or a short form (owner/repo)."
    )


def resolve_short_form(source: str) -> str:
    return f"https://github.com/{source}.git"


def _ensure_git_available() -> None:
    if shutil.which("git") is None:
        raise SourceError("git executable not found in PATH. Install git and retry.")


def fetch_git_source(url: str, ref: str | None, depth: int) -> str:
    """
    Clone ``url`` into a temp dir and return the staging path.
    Credentials are passed via git config, not embedded in the URL.
    """
    _ensure_git_available()

    kind = credentials.classify(url)
    clone_url = url

    staging = tempfile.mkdtemp(prefix="chacc-install-")
    cmd: list[str] = ["git", "clone"]
    if depth and depth > 0 and not (ref and "/" in ref):
        cmd += [f"--depth={depth}"]
    if ref:
        cmd += ["--branch", ref]
    cmd += [clone_url, staging]

    env = os.environ.copy()
    if kind not in ("ssh", "https-with-creds"):
        token = credentials.lookup_token(url)
        if token:
            hostname = urlparse(url).hostname or ""
            creds = base64.b64encode(f":{token}".encode()).decode()
            env["GIT_CONFIG_PARAMETERS"] = (
                f"http.{hostname}.extraheader=Authorization: Basic {creds}"
            )

    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:  # git not found - already caught above
        shutil.rmtree(staging, ignore_errors=True)
        raise SourceError(str(exc)) from exc

    if result.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        stderr_tail = (result.stderr or "").strip().splitlines()[-3:]
        stderr_msg = "\n".join(stderr_tail) if stderr_tail else "git clone failed"
        redacted = credentials.redact_url(url)
        token = credentials.lookup_token(url)
        stderr_msg = credentials.scrub_token(stderr_msg, token)
        if (
            not credentials.is_tty()
            and "Authentication" in stderr_msg
            or "403" in stderr_msg
            or "401" in stderr_msg
        ):
            raise SourceError(
                f"Cannot reach private repository '{redacted}'. Set GITHUB_TOKEN "
                "(or pass --token-env NAME) or use an SSH URL. "
                "Running in non-interactive mode; cannot prompt for credentials.\n"
                f"git: {stderr_msg}"
            )
        if (
            kind != "ssh"
            and credentials.lookup_token(url) is None
            and ("Authentication failed" in stderr_msg or "could not read Username" in stderr_msg)
        ):
            raise SourceError(
                f"Cannot reach private repository '{redacted}'. "
                "Set GITHUB_TOKEN (or pass --token-env NAME) or use an SSH URL.\n"
                f"git: {stderr_msg}"
            )
        raise SourceError(f"Failed to fetch from '{redacted}': {stderr_msg}")

    return staging


def resolve(source: str, ref: str | None, depth: int) -> ResolvedSource:
    """
    Top-level entry: turn a user-typed source into a ``ResolvedSource``.
    Cleans up cloned staging on failure.
    """
    src, inline_ref = split_source_and_ref(source)
    effective_ref = ref or inline_ref

    kind = classify_source(src)
    if kind == "local":
        path = os.path.abspath(src)
        if not os.path.isdir(path):
            raise SourceError(f"Path '{path}' does not exist or is not a directory.")
        return ResolvedSource(kind="local", path=path, origin_url=None, cleanup=False)
    if kind == "short":
        url = resolve_short_form(src)
    else:
        url = src

    staging = fetch_git_source(url, effective_ref, depth)
    return ResolvedSource(
        kind="git",
        path=staging,
        origin_url=url,
        cleanup=True,
    )


def cleanup(resolved: ResolvedSource) -> None:
    if resolved.cleanup and resolved.kind == "git" and os.path.exists(resolved.path):
        shutil.rmtree(resolved.path, ignore_errors=True)
