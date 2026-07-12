"""Logging utilities for collection module.

Provides a small helper to create module loggers with a consistent format.
"""

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a plain module logger for `name`.

    Deliberately does not attach its own handler: every real entrypoint
    (this package's `__main__.py`, and each script's own `if __name__ ==
    "__main__":` block) calls `configure_logging()` once, which sets up the
    root logger's single handler. Records propagate up to it. Attaching a
    handler here too used to double-print every message (once via this
    logger's own handler, once via root's) whenever `configure_logging()`
    ran after this module had already been imported -- which is always,
    since imports resolve before `main()` runs.
    """
    return logging.getLogger(name)


def configure_logging(level: int = logging.INFO, fmt: str | None = None) -> None:
    """Configure global logging for the collection package.

    Should be called from top-level entrypoints (CLI scripts or `__main__`).
    Multiple calls are idempotent — if the root logger already has handlers,
    this function will not reconfigure them.
    """
    root = logging.getLogger()
    if root.handlers:
        return
    if fmt is None:
        fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=level, format=fmt)
    logging.getLogger("pydriller").setLevel(logging.WARNING)
