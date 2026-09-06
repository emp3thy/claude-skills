"""Pydantic request models; FastAPI answers 422 when one of these constraints fails."""
from __future__ import annotations

from pydantic import BaseModel, Field


class OrderRequest(BaseModel):
    reference: str = Field(min_length=1, max_length=50)
    sku: str = Field(pattern=r"^[A-Z]{3}-\d{4}$")
    quantity: int = Field(gt=0)
