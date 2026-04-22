"""Structured logging setup."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure a structured log format for the application."""
    fmt = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("httpcore", "httpx", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
