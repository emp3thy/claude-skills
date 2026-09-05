from pydantic import BaseModel, Field


class OrderIn(BaseModel):
    sku: str = Field(..., min_length=3, max_length=20)
    quantity: int = Field(..., gt=0, le=100)
    customer_email: str = Field(..., pattern=r"^.+@.+$")
    note: str | None = None


class OrderOut(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
