"""Logging utilities for collection module.

Provides a small helper to create module loggers with a consistent format.
"""

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for `name`.

    The helper ensures a basic console formatter is set if no handlers exist.
    """
    logger = logging.getLogger(name)
    # If the logger doesn't have handlers and the root logger has none,
    # attach a default stream handler so modules can emit logs without
    # requiring explicit configuration. If the root logger has handlers
    # (e.g., after `configure_logging()`), rely on those instead.
    if not logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


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
