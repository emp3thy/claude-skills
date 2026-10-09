"""Runs background tasks on a fixed interval."""
from __future__ import annotations

import time


def run_forever(interval: float) -> None:
    while True:
        time.sleep(interval)
