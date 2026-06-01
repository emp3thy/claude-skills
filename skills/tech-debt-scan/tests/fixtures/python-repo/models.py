"""Data models."""
from dataclasses import dataclass


@dataclass
class Widget:
    name: str
    size: int
