"""Where kv keeps its files and how it reads its settings."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

SETTINGS = "settings.toml"


def _env(name: str, default: str = "") -> str:
    """One kv environment variable, or ``default``."""
    return os.environ.get(name, default)


def home() -> Path:
    """The store directory: KV_HOME, else ~/.kv."""
    return Path(os.environ.get("KV_HOME", "~/.kv")).expanduser()


def token() -> str:
    """The token sync writes to the sync log."""
    return _env("KV_TOKEN")


def load_settings() -> dict[str, object]:
    """The keys of settings.toml in the store directory, or none."""
    path = home() / SETTINGS
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)
