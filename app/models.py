from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "app_user"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    total_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (CheckConstraint("role IN ('CUSTOMER', 'OWNER')", name="ck_user_role"),)


class RefreshToken(Base):
    __tablename__ = "refresh_token"

    token: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.user_id"), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)


class Store(Base):
    __tablename__ = "store"

    store_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.user_id"), nullable=False)
    store_name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80))
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    business_hours: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(String(40))


class Product(Base):
    __tablename__ = "product"

    product_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("store.store_id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(160), nullable=False)
    original_price: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_price: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    end_time: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        CheckConstraint("status IN ('FOR_SALE', 'SOLD_OUT', 'EXPIRED')", name="ck_product_status"),
    )


class CustomerOrder(Base):
    __tablename__ = "customer_order"

    order_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.user_id"), nullable=False)
    store_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("store.store_id"), nullable=False)
    total_price: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    pickup_status: Mapped[str] = mapped_column(String(20), nullable=False)
    earned_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ordered_at: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        CheckConstraint("payment_method IN ('CARD', 'POINT')", name="ck_payment_method"),
        CheckConstraint("pickup_status IN ('READY', 'COMPLETED', 'CANCELED')", name="ck_pickup_status"),
    )


class OrderItem(Base):
    __tablename__ = "order_item"

    order_item_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customer_order.order_id"), nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("product.product_id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)


class Review(Base):
    __tablename__ = "review"

    review_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customer_order.order_id"), nullable=False, unique=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.user_id"), nullable=False)
    store_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("store.store_id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating"),)


class Favorite(Base):
    __tablename__ = "favorite"

    favorite_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.user_id"), nullable=False)
    store_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("store.store_id"), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (UniqueConstraint("customer_id", "store_id", name="uq_favorite_customer_store"),)


class PointHistory(Base):
    __tablename__ = "point_history"

    point_history_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.user_id"), nullable=False)
    order_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("customer_order.order_id"))
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (CheckConstraint("type IN ('EARN', 'USE', 'CANCEL')", name="ck_point_type"),)

