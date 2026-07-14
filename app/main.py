from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import DatabaseNotConfigured, db
from app.schemas import (
    FavoriteCreateRequest,
    LocationRequest,
    LoginRequest,
    OrderCreateRequest,
    PaymentMethod,
    PickupStatus,
    PointType,
    ProductCreateRequest,
    ProductStatus,
    ProductUpdateRequest,
    ReissueRequest,
    ReviewCreateRequest,
    SignupRequest,
    StoreCreateRequest,
    UserRole,
    UserUpdateRequest,
)
from app.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    now_iso,
    parse_access_token,
    verify_password,
)


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    try:
        db.init_schema()
        app.state.db_ready = True
        app.state.db_error = None
    except (DatabaseNotConfigured, Exception) as exc:
        app.state.db_ready = False
        app.state.db_error = str(exc)


def ensure_db_ready() -> None:
    if not getattr(app.state, "db_ready", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=getattr(app.state, "db_error", "Database is not ready."),
        )


def ok(data: Any = None, message: str = "Request succeeded.") -> dict[str, Any]:
    return {"success": True, "data": data, "message": message}


def fail(status_code: int, message: str, error_code: str) -> None:
    raise HTTPException(status_code=status_code, detail={"success": False, "data": None, "message": message, "errorCode": error_code})


def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    ensure_db_ready()
    if not authorization or not authorization.startswith("Bearer "):
        fail(status.HTTP_401_UNAUTHORIZED, "Authentication is required.", "UNAUTHORIZED")
    try:
        user_id, _role = parse_access_token(authorization.removeprefix("Bearer ").strip())
    except ValueError:
        fail(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token.", "UNAUTHORIZED")
    user = db.fetch_one("SELECT * FROM app_user WHERE user_id = ? AND deleted_at IS NULL", [user_id])
    if not user:
        fail(status.HTTP_401_UNAUTHORIZED, "User not found.", "UNAUTHORIZED")
    return user


def require_role(user: dict[str, Any], role: UserRole) -> None:
    if user["role"] != role.value:
        fail(status.HTTP_403_FORBIDDEN, f"{role.value} role is required.", "FORBIDDEN")


def discount_rate(original_price: int, discount_price: int) -> int:
    if original_price <= 0:
        fail(status.HTTP_400_BAD_REQUEST, "originalPrice must be greater than 0.", "BAD_REQUEST")
    if discount_price < 0 or discount_price > original_price:
        fail(status.HTTP_400_BAD_REQUEST, "discountPrice must be between 0 and originalPrice.", "BAD_REQUEST")
    return round((original_price - discount_price) / original_price * 100)


def product_status(quantity: int, end_time: str, current: str | None = None) -> str:
    if is_expired(end_time):
        return ProductStatus.EXPIRED.value
    if quantity <= 0:
        return ProductStatus.SOLD_OUT.value
    return current or ProductStatus.FOR_SALE.value


def parse_datetime(value: str) -> datetime | None:
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def is_expired(end_time: str) -> bool:
    parsed = parse_datetime(end_time)
    return parsed is not None and parsed <= datetime.now(timezone.utc)


def refresh_expired_products() -> None:
    rows = db.fetch_all(
        "SELECT product_id, end_time FROM product WHERE status = 'FOR_SALE' AND deleted_at IS NULL"
    )
    for row in rows:
        if is_expired(row["end_time"]):
            db.execute("UPDATE product SET status = ? WHERE product_id = ?", [ProductStatus.EXPIRED.value, row["product_id"]])


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    radius = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return round(radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def page_slice(items: list[dict[str, Any]], page: int, size: int) -> list[dict[str, Any]]:
    start = max(page, 0) * max(size, 1)
    return items[start : start + max(size, 1)]


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "userId": row["user_id"],
        "email": row["email"],
        "name": row["name"],
        "phone": row["phone"],
        "role": row["role"],
        "totalPoints": row["total_points"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "createdAt": row["created_at"],
    }


def store_detail(row: dict[str, Any]) -> dict[str, Any]:
    stats = db.fetch_one(
        """
        SELECT COALESCE(AVG(r.rating), 0) AS average_rating, COUNT(r.review_id) AS review_count
        FROM review r
        WHERE r.store_id = ?
        """,
        [row["store_id"]],
    )
    product_count = db.fetch_one(
        "SELECT COUNT(*) AS count FROM product WHERE store_id = ? AND status = 'FOR_SALE' AND deleted_at IS NULL",
        [row["store_id"]],
    )
    return {
        "storeId": row["store_id"],
        "storeName": row["store_name"],
        "ownerId": row["owner_id"],
        "category": row["category"],
        "address": row["address"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "businessHours": row["business_hours"],
        "description": row["description"],
        "averageRating": float(stats["average_rating"] or 0),
        "reviewCount": int(stats["review_count"] or 0),
        "onSaleProductCount": int(product_count["count"] or 0),
        "createdAt": row["created_at"],
    }


def product_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "productId": row["product_id"],
        "productName": row["product_name"],
        "discountPrice": row["discount_price"],
        "discountRate": row["discount_rate"],
        "quantity": row["quantity"],
        "status": row["status"],
        "endTime": row["end_time"],
    }


def product_detail(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "productId": row["product_id"],
        "storeId": row["store_id"],
        "storeName": row.get("store_name"),
        "productName": row["product_name"],
        "originalPrice": row["original_price"],
        "discountPrice": row["discount_price"],
        "discountRate": row["discount_rate"],
        "quantity": row["quantity"],
        "endTime": row["end_time"],
        "status": row["status"],
        "imageUrl": row["image_url"],
        "createdAt": row["created_at"],
    }


def order_items(order_id: int) -> list[dict[str, Any]]:
    rows = db.fetch_all("SELECT * FROM order_item WHERE order_id = ? ORDER BY order_item_id", [order_id])
    return [
        {
            "orderItemId": row["order_item_id"],
            "productId": row["product_id"],
            "productName": row["product_name"],
            "quantity": row["quantity"],
            "price": row["price"],
        }
        for row in rows
    ]


def order_detail(row: dict[str, Any]) -> dict[str, Any]:
    review = db.fetch_one("SELECT review_id FROM review WHERE order_id = ?", [row["order_id"]])
    return {
        "orderId": row["order_id"],
        "storeId": row["store_id"],
        "storeName": row["store_name"],
        "storeAddress": row["address"],
        "storeLatitude": row["latitude"],
        "storeLongitude": row["longitude"],
        "totalPrice": row["total_price"],
        "paymentMethod": row["payment_method"],
        "pickupStatus": row["pickup_status"],
        "earnedPoints": row["earned_points"],
        "usedPoints": row["used_points"],
        "orderedAt": row["ordered_at"],
        "items": order_items(row["order_id"]),
        "hasReview": review is not None,
    }


def get_order(order_id: int) -> dict[str, Any] | None:
    return db.fetch_one(
        """
        SELECT o.*, s.store_name, s.address, s.latitude, s.longitude
        FROM customer_order o
        JOIN store s ON s.store_id = o.store_id
        WHERE o.order_id = ?
        """,
        [order_id],
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok" if getattr(app.state, "db_ready", False) else "db_not_ready", "dbError": getattr(app.state, "db_error", None)}


@app.post("/api/auth/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest) -> dict[str, Any]:
    ensure_db_ready()
    existing = db.fetch_one("SELECT user_id FROM app_user WHERE email = ?", [payload.email])
    if existing:
        fail(status.HTTP_409_CONFLICT, "Email is already registered.", "EMAIL_ALREADY_EXISTS")
    created_at = now_iso()
    user_id = db.insert_and_get_id(
        """
        INSERT INTO app_user (email, password_hash, name, phone, role, total_points, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [payload.email, hash_password(payload.password), payload.name, payload.phone, payload.role.value, 0, created_at],
        "app_user",
        "user_id",
    )
    return ok(
        {
            "userId": user_id,
            "email": payload.email,
            "name": payload.name,
            "role": payload.role.value,
            "createdAt": created_at,
        },
        "Signup succeeded.",
    )


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> dict[str, Any]:
    ensure_db_ready()
    user = db.fetch_one("SELECT * FROM app_user WHERE email = ? AND deleted_at IS NULL", [payload.email])
    if not user or not verify_password(payload.password, user["password_hash"]):
        fail(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.", "INVALID_CREDENTIALS")
    refresh_token = create_refresh_token()
    db.execute(
        "INSERT INTO refresh_token (token, user_id, created_at) VALUES (?, ?, ?)",
        [refresh_token, user["user_id"], now_iso()],
    )
    return ok(
        {
            "accessToken": create_access_token(user["user_id"], user["role"]),
            "refreshToken": refresh_token,
            "user": {"userId": user["user_id"], "name": user["name"], "role": user["role"]},
        },
        "Login succeeded.",
    )


@app.post("/api/auth/reissue")
def reissue(payload: ReissueRequest) -> dict[str, Any]:
    ensure_db_ready()
    row = db.fetch_one(
        """
        SELECT u.* FROM refresh_token rt
        JOIN app_user u ON u.user_id = rt.user_id
        WHERE rt.token = ? AND u.deleted_at IS NULL
        """,
        [payload.refreshToken],
    )
    if not row:
        fail(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token.", "INVALID_REFRESH_TOKEN")
    return ok({"accessToken": create_access_token(row["user_id"], row["role"])}, "Token reissued.")


@app.get("/api/auth/check-email")
def check_email(email: str) -> dict[str, Any]:
    ensure_db_ready()
    row = db.fetch_one("SELECT user_id FROM app_user WHERE email = ? AND deleted_at IS NULL", [email])
    return ok({"available": row is None})


@app.get("/api/users/me")
def get_me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return ok(public_user(user))


@app.put("/api/users/me")
def update_me(payload: UserUpdateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    next_name = payload.name if payload.name is not None else user["name"]
    next_phone = payload.phone if payload.phone is not None else user["phone"]
    next_password = hash_password(payload.password) if payload.password else user["password_hash"]
    db.execute(
        "UPDATE app_user SET name = ?, phone = ?, password_hash = ? WHERE user_id = ?",
        [next_name, next_phone, next_password, user["user_id"]],
    )
    return ok(message="User updated.")


@app.delete("/api/users/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(user: dict[str, Any] = Depends(current_user)) -> Response:
    db.execute("UPDATE app_user SET deleted_at = ? WHERE user_id = ?", [now_iso(), user["user_id"]])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/api/users/me/location")
def update_location(payload: LocationRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    db.execute("UPDATE app_user SET latitude = ?, longitude = ? WHERE user_id = ?", [payload.latitude, payload.longitude, user["user_id"]])
    return ok(message="Location updated.")


@app.get("/api/users/me/points")
def my_points(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return ok({"totalPoints": user["total_points"]})


@app.get("/api/users/me/points/history")
def my_point_history(
    type: PointType | None = None,
    page: int = 0,
    size: int = 20,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    params: list[Any] = [user["user_id"]]
    where = "WHERE user_id = ?"
    if type:
        where += " AND type = ?"
        params.append(type.value)
    rows = db.fetch_all(f"SELECT * FROM point_history {where} ORDER BY point_history_id DESC", params)
    content = [
        {
            "pointHistoryId": row["point_history_id"],
            "orderId": row["order_id"],
            "amount": row["amount"],
            "type": row["type"],
            "createdAt": row["created_at"],
        }
        for row in page_slice(rows, page, size)
    ]
    return ok({"totalPoints": user["total_points"], "content": content})


@app.post("/api/stores", status_code=status.HTTP_201_CREATED)
def create_store(payload: StoreCreateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_role(user, UserRole.OWNER)
    store_id = db.insert_and_get_id(
        """
        INSERT INTO store (owner_id, store_name, category, address, latitude, longitude, business_hours, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            user["user_id"],
            payload.storeName,
            payload.category,
            payload.address,
            payload.latitude,
            payload.longitude,
            payload.businessHours,
            payload.description,
            now_iso(),
        ],
        "store",
        "store_id",
    )
    return ok({"storeId": store_id, "storeName": payload.storeName, "ownerId": user["user_id"]}, "Store created.")


@app.get("/api/stores/me")
def my_store(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_role(user, UserRole.OWNER)
    row = db.fetch_one("SELECT * FROM store WHERE owner_id = ? AND deleted_at IS NULL ORDER BY store_id DESC", [user["user_id"]])
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Store not found.", "STORE_NOT_FOUND")
    return ok(store_detail(row))


@app.get("/api/stores/nearby")
def nearby_stores(
    lat: float,
    lng: float,
    radius: int = 3000,
    sort: str = "distance",
    category: str | None = None,
    keyword: str | None = None,
    page: int = 0,
    size: int = 20,
) -> dict[str, Any]:
    ensure_db_ready()
    refresh_expired_products()
    rows = db.fetch_all("SELECT * FROM store WHERE deleted_at IS NULL")
    results = []
    for row in rows:
        if category and row["category"] != category:
            continue
        if keyword and keyword.lower() not in f"{row['store_name']} {row['address']} {row['description'] or ''}".lower():
            continue
        distance = haversine_m(lat, lng, row["latitude"], row["longitude"])
        if distance > radius:
            continue
        products = db.fetch_all(
            "SELECT * FROM product WHERE store_id = ? AND status = 'FOR_SALE' AND deleted_at IS NULL",
            [row["store_id"]],
        )
        results.append(
            {
                "storeId": row["store_id"],
                "storeName": row["store_name"],
                "category": row["category"],
                "address": row["address"],
                "distance": distance,
                "maxDiscountRate": max([p["discount_rate"] for p in products], default=0),
                "minDiscountPrice": min([p["discount_price"] for p in products], default=0),
                "closestEndTime": min([p["end_time"] for p in products], default=None),
                "onSaleProductCount": len(products),
                "thumbnailUrl": next((p["image_url"] for p in products if p["image_url"]), None),
            }
        )
    if sort == "discount":
        results.sort(key=lambda item: item["maxDiscountRate"], reverse=True)
    elif sort == "price":
        results.sort(key=lambda item: item["minDiscountPrice"] or 10**12)
    elif sort == "endTime":
        results.sort(key=lambda item: item["closestEndTime"] or "9999")
    else:
        results.sort(key=lambda item: item["distance"])
    return ok({"content": page_slice(results, page, size)})


@app.get("/api/stores/{storeId}")
def get_store(storeId: int) -> dict[str, Any]:
    ensure_db_ready()
    row = db.fetch_one("SELECT * FROM store WHERE store_id = ? AND deleted_at IS NULL", [storeId])
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Store not found.", "STORE_NOT_FOUND")
    return ok(store_detail(row))


@app.put("/api/stores/{storeId}")
def update_store(storeId: int, payload: StoreCreateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    row = db.fetch_one("SELECT * FROM store WHERE store_id = ? AND deleted_at IS NULL", [storeId])
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Store not found.", "STORE_NOT_FOUND")
    if row["owner_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "Only the owner can update this store.", "FORBIDDEN")
    db.execute(
        """
        UPDATE store
        SET store_name = ?, category = ?, address = ?, latitude = ?, longitude = ?, business_hours = ?, description = ?
        WHERE store_id = ?
        """,
        [payload.storeName, payload.category, payload.address, payload.latitude, payload.longitude, payload.businessHours, payload.description, storeId],
    )
    return ok(message="Store updated.")


@app.delete("/api/stores/{storeId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_store(storeId: int, user: dict[str, Any] = Depends(current_user)) -> Response:
    row = db.fetch_one("SELECT * FROM store WHERE store_id = ? AND deleted_at IS NULL", [storeId])
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Store not found.", "STORE_NOT_FOUND")
    if row["owner_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "Only the owner can delete this store.", "FORBIDDEN")
    db.execute("UPDATE store SET deleted_at = ? WHERE store_id = ?", [now_iso(), storeId])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/stores/{storeId}/products")
def store_products(storeId: int, status_filter: ProductStatus | None = Query(default=None, alias="status")) -> dict[str, Any]:
    ensure_db_ready()
    refresh_expired_products()
    params: list[Any] = [storeId]
    where = "WHERE store_id = ? AND deleted_at IS NULL"
    if status_filter:
        where += " AND status = ?"
        params.append(status_filter.value)
    rows = db.fetch_all(f"SELECT * FROM product {where} ORDER BY product_id DESC", params)
    return ok([product_summary(row) for row in rows])


@app.get("/api/stores/{storeId}/reviews")
def store_reviews(storeId: int, sort: str = "latest", page: int = 0, size: int = 20) -> dict[str, Any]:
    ensure_db_ready()
    order = "r.rating DESC, r.review_id DESC" if sort == "rating" else "r.review_id DESC"
    rows = db.fetch_all(
        f"""
        SELECT r.*, u.name AS customer_name
        FROM review r JOIN app_user u ON u.user_id = r.customer_id
        WHERE r.store_id = ?
        ORDER BY {order}
        """,
        [storeId],
    )
    reviews = [
        {"reviewId": r["review_id"], "customerName": r["customer_name"], "rating": r["rating"], "content": r["content"], "createdAt": r["created_at"]}
        for r in rows
    ]
    average = sum([r["rating"] for r in rows]) / len(rows) if rows else 0
    return ok({"averageRating": average, "reviewCount": len(rows), "content": page_slice(reviews, page, size)})


@app.get("/api/stores/{storeId}/orders")
def store_orders(
    storeId: int,
    status_filter: PickupStatus | None = Query(default=None, alias="status"),
    page: int = 0,
    size: int = 20,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    store = db.fetch_one("SELECT * FROM store WHERE store_id = ? AND deleted_at IS NULL", [storeId])
    if not store:
        fail(status.HTTP_404_NOT_FOUND, "Store not found.", "STORE_NOT_FOUND")
    if store["owner_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "Only the owner can view store orders.", "FORBIDDEN")
    params: list[Any] = [storeId]
    where = "WHERE o.store_id = ?"
    if status_filter:
        where += " AND o.pickup_status = ?"
        params.append(status_filter.value)
    rows = db.fetch_all(
        f"""
        SELECT o.*, u.name AS customer_name,
          (SELECT COUNT(*) FROM order_item oi WHERE oi.order_id = o.order_id) AS item_count
        FROM customer_order o JOIN app_user u ON u.user_id = o.customer_id
        {where}
        ORDER BY o.order_id DESC
        """,
        params,
    )
    content = [
        {
            "orderId": row["order_id"],
            "customerName": row["customer_name"],
            "totalPrice": row["total_price"],
            "pickupStatus": row["pickup_status"],
            "orderedAt": row["ordered_at"],
            "itemCount": row["item_count"],
        }
        for row in page_slice(rows, page, size)
    ]
    return ok({"content": content})


@app.post("/api/products", status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_role(user, UserRole.OWNER)
    store = db.fetch_one("SELECT * FROM store WHERE store_id = ? AND deleted_at IS NULL", [payload.storeId])
    if not store:
        fail(status.HTTP_404_NOT_FOUND, "Store not found.", "STORE_NOT_FOUND")
    if store["owner_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "Only the owner can create products.", "FORBIDDEN")
    if is_expired(payload.endTime):
        fail(status.HTTP_400_BAD_REQUEST, "endTime must be in the future.", "INVALID_END_TIME")
    rate = discount_rate(payload.originalPrice, payload.discountPrice)
    product_id = db.insert_and_get_id(
        """
        INSERT INTO product
          (store_id, product_name, original_price, discount_price, discount_rate, quantity, end_time, status, image_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            payload.storeId,
            payload.productName,
            payload.originalPrice,
            payload.discountPrice,
            rate,
            payload.quantity,
            payload.endTime,
            product_status(payload.quantity, payload.endTime),
            payload.imageUrl,
            now_iso(),
        ],
        "product",
        "product_id",
    )
    row = db.fetch_one("SELECT * FROM product WHERE product_id = ?", [product_id])
    return ok(product_summary(row), "Product created.")


@app.get("/api/products")
def product_feed(
    keyword: str | None = None,
    category: str | None = None,
    sort: str = "endTime",
    lat: float | None = None,
    lng: float | None = None,
    status_filter: ProductStatus | None = Query(default=None, alias="status"),
    page: int = 0,
    size: int = 20,
) -> dict[str, Any]:
    ensure_db_ready()
    refresh_expired_products()
    rows = db.fetch_all(
        """
        SELECT p.*, s.store_name, s.category, s.latitude, s.longitude
        FROM product p JOIN store s ON s.store_id = p.store_id
        WHERE p.deleted_at IS NULL AND s.deleted_at IS NULL
        """,
    )
    results = []
    for row in rows:
        if status_filter and row["status"] != status_filter.value:
            continue
        if category and row["category"] != category:
            continue
        if keyword and keyword.lower() not in f"{row['product_name']} {row['store_name']}".lower():
            continue
        item = product_detail(row)
        if lat is not None and lng is not None:
            item["distance"] = haversine_m(lat, lng, row["latitude"], row["longitude"])
        results.append(item)
    if sort == "distance" and lat is not None and lng is not None:
        results.sort(key=lambda item: item.get("distance", 10**12))
    elif sort == "discount":
        results.sort(key=lambda item: item["discountRate"], reverse=True)
    elif sort == "price":
        results.sort(key=lambda item: item["discountPrice"])
    else:
        results.sort(key=lambda item: item["endTime"])
    return ok({"content": page_slice(results, page, size)})


@app.get("/api/products/{productId}")
def get_product(productId: int) -> dict[str, Any]:
    ensure_db_ready()
    refresh_expired_products()
    row = db.fetch_one(
        """
        SELECT p.*, s.store_name
        FROM product p JOIN store s ON s.store_id = p.store_id
        WHERE p.product_id = ? AND p.deleted_at IS NULL
        """,
        [productId],
    )
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Product not found.", "PRODUCT_NOT_FOUND")
    return ok(product_detail(row))


@app.put("/api/products/{productId}")
def update_product(productId: int, payload: ProductUpdateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    row = db.fetch_one(
        """
        SELECT p.*, s.owner_id FROM product p
        JOIN store s ON s.store_id = p.store_id
        WHERE p.product_id = ? AND p.deleted_at IS NULL
        """,
        [productId],
    )
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Product not found.", "PRODUCT_NOT_FOUND")
    if row["owner_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "Only the owner can update this product.", "FORBIDDEN")
    next_original = payload.originalPrice if payload.originalPrice is not None else row["original_price"]
    next_discount = payload.discountPrice if payload.discountPrice is not None else row["discount_price"]
    next_quantity = payload.quantity if payload.quantity is not None else row["quantity"]
    next_end_time = payload.endTime or row["end_time"]
    if payload.endTime is not None and is_expired(payload.endTime):
        fail(status.HTTP_400_BAD_REQUEST, "endTime must be in the future.", "INVALID_END_TIME")
    db.execute(
        """
        UPDATE product
        SET product_name = ?, original_price = ?, discount_price = ?, discount_rate = ?, quantity = ?, end_time = ?, image_url = ?, status = ?
        WHERE product_id = ?
        """,
        [
            payload.productName or row["product_name"],
            next_original,
            next_discount,
            discount_rate(next_original, next_discount),
            next_quantity,
            next_end_time,
            payload.imageUrl if payload.imageUrl is not None else row["image_url"],
            product_status(next_quantity, next_end_time, row["status"]),
            productId,
        ],
    )
    updated = db.fetch_one("SELECT * FROM product WHERE product_id = ?", [productId])
    return ok(product_summary(updated), "Product updated.")


@app.delete("/api/products/{productId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(productId: int, user: dict[str, Any] = Depends(current_user)) -> Response:
    row = db.fetch_one(
        """
        SELECT p.*, s.owner_id FROM product p
        JOIN store s ON s.store_id = p.store_id
        WHERE p.product_id = ? AND p.deleted_at IS NULL
        """,
        [productId],
    )
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Product not found.", "PRODUCT_NOT_FOUND")
    if row["owner_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "Only the owner can delete this product.", "FORBIDDEN")
    db.execute("UPDATE product SET deleted_at = ? WHERE product_id = ?", [now_iso(), productId])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/orders", status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_role(user, UserRole.CUSTOMER)
    refresh_expired_products()
    if not payload.items:
        fail(status.HTTP_400_BAD_REQUEST, "items must not be empty.", "BAD_REQUEST")
    store = db.fetch_one("SELECT * FROM store WHERE store_id = ? AND deleted_at IS NULL", [payload.storeId])
    if not store:
        fail(status.HTTP_404_NOT_FOUND, "Store not found.", "STORE_NOT_FOUND")

    now = now_iso()
    products = []
    total_price = 0
    with db.transaction() as conn:
        cur = conn.cursor()
        for item in payload.items:
            cur.execute("SELECT * FROM product WHERE product_id = ? AND store_id = ? AND deleted_at IS NULL", [item.productId, payload.storeId])
            product_row = cur.fetchone()
            product = db._row_to_dict(cur, product_row) if product_row else None
            if not product:
                fail(status.HTTP_404_NOT_FOUND, "Product not found.", "PRODUCT_NOT_FOUND")
            if is_expired(product["end_time"]):
                cur.execute("UPDATE product SET status = ? WHERE product_id = ?", [ProductStatus.EXPIRED.value, product["product_id"]])
                fail(status.HTTP_400_BAD_REQUEST, "Product sale has ended.", "PRODUCT_SALE_ENDED")
            if product["status"] != ProductStatus.FOR_SALE.value or product["quantity"] < item.quantity:
                fail(status.HTTP_409_CONFLICT, "Product is out of stock.", "PRODUCT_OUT_OF_STOCK")
            products.append((item, product))
            total_price += product["discount_price"] * item.quantity

        use_points = min(max(payload.usePoints, 0), total_price)
        if payload.paymentMethod == PaymentMethod.POINT and user["total_points"] < total_price:
            fail(status.HTTP_400_BAD_REQUEST, "Not enough points.", "POINT_NOT_ENOUGH")
        if use_points > user["total_points"]:
            fail(status.HTTP_400_BAD_REQUEST, "Not enough points.", "POINT_NOT_ENOUGH")
        earned_points = max(total_price - use_points, 0) // 100

        cur.execute(
            """
            INSERT INTO customer_order
              (customer_id, store_id, total_price, payment_method, pickup_status, earned_points, used_points, ordered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [user["user_id"], payload.storeId, total_price, payload.paymentMethod.value, PickupStatus.READY.value, earned_points, use_points, now],
        )
        key_cur = conn.cursor()
        key_cur.execute("SELECT MAX(order_id) FROM customer_order")
        order_id = int(key_cur.fetchone()[0])

        for item, product in products:
            next_quantity = product["quantity"] - item.quantity
            cur.execute(
                "UPDATE product SET quantity = ?, status = ? WHERE product_id = ?",
                [next_quantity, product_status(next_quantity, product["end_time"]), product["product_id"]],
            )
            cur.execute(
                """
                INSERT INTO order_item (order_id, product_id, product_name, quantity, price)
                VALUES (?, ?, ?, ?, ?)
                """,
                [order_id, product["product_id"], product["product_name"], item.quantity, product["discount_price"]],
            )
        if use_points:
            cur.execute(
                "INSERT INTO point_history (user_id, order_id, amount, type, created_at) VALUES (?, ?, ?, ?, ?)",
                [user["user_id"], order_id, -use_points, PointType.USE.value, now],
            )
        if earned_points:
            cur.execute(
                "INSERT INTO point_history (user_id, order_id, amount, type, created_at) VALUES (?, ?, ?, ?, ?)",
                [user["user_id"], order_id, earned_points, PointType.EARN.value, now],
            )
        cur.execute("UPDATE app_user SET total_points = total_points - ? + ? WHERE user_id = ?", [use_points, earned_points, user["user_id"]])

    row = get_order(order_id)
    return ok(order_detail(row), "Order created.")


@app.get("/api/orders/me")
def my_orders(
    status_filter: PickupStatus | None = Query(default=None, alias="status"),
    page: int = 0,
    size: int = 20,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    params: list[Any] = [user["user_id"]]
    where = "WHERE o.customer_id = ?"
    if status_filter:
        where += " AND o.pickup_status = ?"
        params.append(status_filter.value)
    rows = db.fetch_all(
        f"""
        SELECT o.*, s.store_name,
          (SELECT product_name FROM order_item oi WHERE oi.order_id = o.order_id ORDER BY oi.order_item_id FETCH FIRST 1 ROW ONLY) AS representative_product_name,
          (SELECT COUNT(*) FROM order_item oi WHERE oi.order_id = o.order_id) AS item_count
        FROM customer_order o JOIN store s ON s.store_id = o.store_id
        {where}
        ORDER BY o.order_id DESC
        """,
        params,
    )
    content = [
        {
            "orderId": row["order_id"],
            "storeName": row["store_name"],
            "totalPrice": row["total_price"],
            "pickupStatus": row["pickup_status"],
            "orderedAt": row["ordered_at"],
            "representativeProductName": row["representative_product_name"],
            "itemCount": row["item_count"],
        }
        for row in page_slice(rows, page, size)
    ]
    return ok({"content": content})


@app.get("/api/orders/{orderId}")
def get_order_detail(orderId: int, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    row = get_order(orderId)
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Order not found.", "ORDER_NOT_FOUND")
    store = db.fetch_one("SELECT owner_id FROM store WHERE store_id = ?", [row["store_id"]])
    if row["customer_id"] != user["user_id"] and store["owner_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "You cannot view this order.", "FORBIDDEN")
    return ok(order_detail(row))


@app.patch("/api/orders/{orderId}/cancel")
def cancel_order(orderId: int, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    row = get_order(orderId)
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Order not found.", "ORDER_NOT_FOUND")
    if row["customer_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "Only the customer can cancel this order.", "FORBIDDEN")
    if row["pickup_status"] != PickupStatus.READY.value:
        fail(status.HTTP_400_BAD_REQUEST, "Only READY orders can be canceled.", "ORDER_NOT_CANCELABLE")
    now = now_iso()
    with db.transaction() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE customer_order SET pickup_status = ? WHERE order_id = ?", [PickupStatus.CANCELED.value, orderId])
        cur.execute("SELECT * FROM order_item WHERE order_id = ?", [orderId])
        item_rows = [db._row_to_dict(cur, item) for item in cur.fetchall()]
        for item in item_rows:
            cur.execute("SELECT * FROM product WHERE product_id = ?", [item["product_id"]])
            product = db._row_to_dict(cur, cur.fetchone())
            next_quantity = product["quantity"] + item["quantity"]
            cur.execute(
                "UPDATE product SET quantity = ?, status = ? WHERE product_id = ?",
                [next_quantity, product_status(next_quantity, product["end_time"]), item["product_id"]],
            )
        total_delta = row["used_points"] - row["earned_points"]
        cur.execute("UPDATE app_user SET total_points = total_points + ? WHERE user_id = ?", [total_delta, user["user_id"]])
        if total_delta:
            cur.execute(
                "INSERT INTO point_history (user_id, order_id, amount, type, created_at) VALUES (?, ?, ?, ?, ?)",
                [user["user_id"], orderId, total_delta, PointType.CANCEL.value, now],
            )
    return ok(message="Order canceled.")


@app.patch("/api/orders/{orderId}/complete")
def complete_order(orderId: int, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    row = get_order(orderId)
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Order not found.", "ORDER_NOT_FOUND")
    store = db.fetch_one("SELECT owner_id FROM store WHERE store_id = ?", [row["store_id"]])
    if store["owner_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "Only the owner can complete this order.", "FORBIDDEN")
    db.execute("UPDATE customer_order SET pickup_status = ? WHERE order_id = ?", [PickupStatus.COMPLETED.value, orderId])
    return ok(message="Order completed.")


@app.post("/api/orders/{orderId}/review", status_code=status.HTTP_201_CREATED)
def create_review(orderId: int, payload: ReviewCreateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    row = get_order(orderId)
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Order not found.", "ORDER_NOT_FOUND")
    if row["customer_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "Only the order customer can review.", "FORBIDDEN")
    existing = db.fetch_one("SELECT review_id FROM review WHERE order_id = ?", [orderId])
    if existing:
        fail(status.HTTP_409_CONFLICT, "Review already exists.", "REVIEW_ALREADY_EXISTS")
    created_at = now_iso()
    review_id = db.insert_and_get_id(
        "INSERT INTO review (order_id, customer_id, store_id, rating, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [orderId, user["user_id"], row["store_id"], payload.rating, payload.content, created_at],
        "review",
        "review_id",
    )
    return ok({"reviewId": review_id, "customerName": user["name"], "rating": payload.rating, "content": payload.content, "createdAt": created_at}, "Review created.")


@app.get("/api/reviews/me")
def my_reviews(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    rows = db.fetch_all(
        """
        SELECT r.*, s.store_name
        FROM review r JOIN store s ON s.store_id = r.store_id
        WHERE r.customer_id = ?
        ORDER BY r.review_id DESC
        """,
        [user["user_id"]],
    )
    return ok(
        [
            {
                "reviewId": row["review_id"],
                "storeId": row["store_id"],
                "storeName": row["store_name"],
                "rating": row["rating"],
                "content": row["content"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]
    )


@app.put("/api/reviews/{reviewId}")
def update_review(reviewId: int, payload: ReviewCreateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    row = db.fetch_one("SELECT * FROM review WHERE review_id = ?", [reviewId])
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Review not found.", "REVIEW_NOT_FOUND")
    if row["customer_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "Only the author can update this review.", "FORBIDDEN")
    db.execute("UPDATE review SET rating = ?, content = ?, updated_at = ? WHERE review_id = ?", [payload.rating, payload.content, now_iso(), reviewId])
    return ok(message="Review updated.")


@app.delete("/api/reviews/{reviewId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(reviewId: int, user: dict[str, Any] = Depends(current_user)) -> Response:
    row = db.fetch_one("SELECT * FROM review WHERE review_id = ?", [reviewId])
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Review not found.", "REVIEW_NOT_FOUND")
    if row["customer_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "Only the author can delete this review.", "FORBIDDEN")
    db.execute("DELETE FROM review WHERE review_id = ?", [reviewId])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/favorites", status_code=status.HTTP_201_CREATED)
def create_favorite(payload: FavoriteCreateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    require_role(user, UserRole.CUSTOMER)
    store = db.fetch_one("SELECT store_id FROM store WHERE store_id = ? AND deleted_at IS NULL", [payload.storeId])
    if not store:
        fail(status.HTTP_404_NOT_FOUND, "Store not found.", "STORE_NOT_FOUND")
    existing = db.fetch_one("SELECT favorite_id FROM favorite WHERE customer_id = ? AND store_id = ?", [user["user_id"], payload.storeId])
    if existing:
        fail(status.HTTP_409_CONFLICT, "Favorite already exists.", "FAVORITE_ALREADY_EXISTS")
    favorite_id = db.insert_and_get_id(
        "INSERT INTO favorite (customer_id, store_id, created_at) VALUES (?, ?, ?)",
        [user["user_id"], payload.storeId, now_iso()],
        "favorite",
        "favorite_id",
    )
    return ok({"favoriteId": favorite_id, "storeId": payload.storeId}, "Favorite created.")


@app.get("/api/favorites/me")
def my_favorites(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    rows = db.fetch_all(
        """
        SELECT f.favorite_id, s.*
        FROM favorite f JOIN store s ON s.store_id = f.store_id
        WHERE f.customer_id = ? AND s.deleted_at IS NULL
        ORDER BY f.favorite_id DESC
        """,
        [user["user_id"]],
    )
    content = []
    for row in rows:
        products = db.fetch_all("SELECT * FROM product WHERE store_id = ? AND status = 'FOR_SALE' AND deleted_at IS NULL", [row["store_id"]])
        content.append(
            {
                "favoriteId": row["favorite_id"],
                "storeId": row["store_id"],
                "storeName": row["store_name"],
                "category": row["category"],
                "onSaleProductCount": len(products),
                "maxDiscountRate": max([p["discount_rate"] for p in products], default=0),
                "thumbnailUrl": next((p["image_url"] for p in products if p["image_url"]), None),
            }
        )
    return ok(content)


@app.delete("/api/favorites/{favoriteId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_favorite(favoriteId: int, user: dict[str, Any] = Depends(current_user)) -> Response:
    row = db.fetch_one("SELECT * FROM favorite WHERE favorite_id = ?", [favoriteId])
    if not row:
        fail(status.HTTP_404_NOT_FOUND, "Favorite not found.", "FAVORITE_NOT_FOUND")
    if row["customer_id"] != user["user_id"]:
        fail(status.HTTP_403_FORBIDDEN, "Only the owner can delete this favorite.", "FORBIDDEN")
    db.execute("DELETE FROM favorite WHERE favorite_id = ?", [favoriteId])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
