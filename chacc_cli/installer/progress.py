"""
Progress UX for ``chacc install``.

Each phase of the install pipeline is wrapped in a small context manager
that prints a visible ``->`` / ``[OK]`` / ``[FAIL]`` marker and an optional
one-line detail. Output is plain ``print()`` so it shows up regardless of
log level and reads cleanly in CI logs and pipes.

Honors ``--quiet``: when quiet, the stepper is silent (only ``final()`` is
still printed because callers need to confirm success/failure).
"""

from __future__ import annotations

import sys
from contextlib import contextmanager

_ARROW = "->"
_OK = "[OK]"
_FAIL = "[FAIL]"

_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


_quiet_flag: dict[str, bool] = {}


def set_quiet(value: bool) -> None:
    """Toggle global quiet mode."""
    _quiet_flag["value"] = bool(value)


def get_quiet() -> bool:
    return bool(_quiet_flag.get("value", False))


def _is_tty() -> bool:
    return sys.stdout.isatty()


def _color(text: str, ansi: str) -> str:
    return f"{ansi}{text}{_RESET}" if _is_tty() else text


def _print(line: str) -> None:
    print(line, flush=True)


@contextmanager
def step(message: str, detail: str = ""):
    """
    Print ``-> message  detail`` on entry, ``[OK] message`` on success,
    and ``[FAIL] message: <error>`` on failure (then re-raise).

    Honors :func:`set_quiet`: when quiet, the stepper is silent but still
    re-raises on failure so callers see the same control flow.

    Usage::

        with step("Resolving source", detail=url):
            resolved = source_mod.resolve(...)
    """
    if not get_quiet():
        arrow = _color(_ARROW, _DIM)
        suffix = f"  {_color(detail, _DIM)}" if detail else ""
        _print(f"{arrow} {message}{suffix}")
    try:
        yield
    except Exception as exc:
        if not get_quiet():
            fail = _color(_FAIL, _BOLD + _RED)
            _print(f"{fail} {message}: {exc}")
        raise
    else:
        if not get_quiet():
            ok = _color(_OK, _BOLD + _GREEN)
            _print(f"{ok} {message}")


def info(message: str) -> None:
    """Print a non-step informational line. Suppressed when --quiet."""
    if not get_quiet():
        _print(f"   {message}")


def warn(message: str) -> None:
    """Print a warning line. Suppressed when --quiet."""
    if not get_quiet():
        prefix = _color("!", _BOLD + _YELLOW)
        _print(f"   {prefix} {message}")


def warn_always(message: str) -> None:
    """Print a warning line even when --quiet. Use sparingly for critical info."""
    prefix = _color("!", _BOLD + _YELLOW)
    _print(f"   {prefix} {message}")


def final(message: str, success: bool = True) -> None:
    """
    Print the final result line. Always shown (even in --quiet) because
    callers need to confirm whether the install succeeded.
    """
    if success:
        line = _color(message, _GREEN)
    else:
        line = _color(message, _RED)
    _print(f"\n{line}")
