from pydantic import BaseModel, Field, ConfigDict
from typing import List
from uuid import UUID

class OrderItemIn(BaseModel):
    product_id: str = Field(min_length=1)
    quantity: int = Field(ge=1, le=25)

class OrderCreateIn(BaseModel):
    customer_session: str = Field(min_length=3, max_length=120)
    items: List[OrderItemIn] = Field(min_length=1, max_length=20)

class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: str
    name: str
    description: str
    price_paise: int
    currency: str
    stock_quantity: int
    image_url: str | None = None

class OrderCreatedOut(BaseModel):
    order_id: UUID
    status: str
    total_paise: int
    payment_status: str
    shipment_status: str
    incident_id: UUID
    message: str
