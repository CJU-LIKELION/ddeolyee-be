from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    CUSTOMER = "CUSTOMER"
    OWNER = "OWNER"


class ProductStatus(str, Enum):
    FOR_SALE = "FOR_SALE"
    SOLD_OUT = "SOLD_OUT"
    EXPIRED = "EXPIRED"


class PickupStatus(str, Enum):
    READY = "READY"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"


class PaymentMethod(str, Enum):
    CARD = "CARD"
    POINT = "POINT"


class PointType(str, Enum):
    EARN = "EARN"
    USE = "USE"
    CANCEL = "CANCEL"


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    name: str
    phone: str | None = None
    role: UserRole


class LoginRequest(BaseModel):
    email: str
    password: str


class ReissueRequest(BaseModel):
    refreshToken: str


class UserUpdateRequest(BaseModel):
    name: str | None = None
    phone: str | None = None
    password: str | None = None


class LocationRequest(BaseModel):
    latitude: float
    longitude: float


class StoreCreateRequest(BaseModel):
    storeName: str
    category: str | None = None
    address: str
    latitude: float
    longitude: float
    businessHours: str | None = None
    description: str | None = None


class ProductCreateRequest(BaseModel):
    storeId: int
    productName: str
    originalPrice: int
    discountPrice: int
    quantity: int
    endTime: str
    imageUrl: str | None = None


class ProductUpdateRequest(BaseModel):
    productName: str | None = None
    originalPrice: int | None = None
    discountPrice: int | None = None
    quantity: int | None = None
    endTime: str | None = None
    imageUrl: str | None = None


class OrderCreateItem(BaseModel):
    productId: int
    quantity: int = Field(gt=0)


class OrderCreateRequest(BaseModel):
    storeId: int
    paymentMethod: PaymentMethod
    usePoints: int = 0
    items: list[OrderCreateItem]


class ReviewCreateRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    content: str | None = None


class FavoriteCreateRequest(BaseModel):
    storeId: int


class ApiResponse(BaseModel):
    success: bool = True
    data: Any = None
    message: str = "Request succeeded."

