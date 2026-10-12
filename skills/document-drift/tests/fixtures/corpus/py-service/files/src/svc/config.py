"""Settings read from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str) -> str:
    """The variable ``name``, or ``default`` when it is unset or empty."""
    value = os.environ.get(name)
    return default if not value else value


@dataclass(frozen=True)
class Settings:
    home: Path
    port: int
    workers: int
    log_level: str


def load() -> Settings:
    """The settings of this process."""
    return Settings(
        home=Path(os.environ.get("SVC_HOME", "~/.svc")).expanduser(),
        port=int(os.environ.get("SVC_PORT", "0")),
        workers=int(os.environ.get("SVC_WORKERS", "0")),
        log_level=_env("SVC_LOG_LEVEL", "info"),
    )
