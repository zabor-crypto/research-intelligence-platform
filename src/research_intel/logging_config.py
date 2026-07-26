"""Structured logging setup for the CLI and library."""

from __future__ import annotations

import logging
import sys


class KeyValueFormatter(logging.Formatter):
    """Simple logfmt-style structured formatter."""

    def format(self, record: logging.LogRecord) -> str:
        base = (
            f"ts={self.formatTime(record, '%Y-%m-%dT%H:%M:%S')} "
            f"level={record.levelname.lower()} "
            f"logger={record.name} "
            f'msg="{record.getMessage()}"'
        )
        if record.exc_info:
            base += f" exc={self.formatException(record.exc_info)!r}"
        return base


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(KeyValueFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # Quiet noisy third-party loggers unless debugging.
    if not verbose:
        for name in ("httpx", "httpcore", "pypdf"):
            logging.getLogger(name).setLevel(logging.WARNING)
