import os
from uuid import uuid4

import pytest

database_url = os.getenv("TEST_DATABASE_URL")
if not database_url:
    pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests.", allow_module_level=True)

os.environ["DATABASE_URL"] = database_url

from fastapi.testclient import TestClient

from app.main import app, startup


startup()
if not getattr(app.state, "db_ready", False):
    pytest.skip(f"Database is not ready: {app.state.db_error}", allow_module_level=True)
client = TestClient(app)


def signup_and_login(role: str) -> tuple[int, str]:
    suffix = uuid4().hex[:8]
    email = f"{role.lower()}-{suffix}@test.com"
    signup = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": "password123!",
            "name": f"{role.title()} User",
            "role": role,
        },
    )
    assert signup.status_code == 201

    login = client.post("/api/auth/login", json={"email": email, "password": "password123!"})
    assert login.status_code == 200
    data = login.json()["data"]
    return data["user"]["userId"], data["accessToken"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_owner_can_create_product_and_customer_can_order_it() -> None:
    _owner_id, owner_token = signup_and_login("OWNER")
    _customer_id, customer_token = signup_and_login("CUSTOMER")

    store = client.post(
        "/api/stores",
        headers=auth_header(owner_token),
        json={
            "storeName": "Test Bakery",
            "category": "Bakery",
            "address": "Seoul Gangnam",
            "latitude": 37.4979,
            "longitude": 127.0276,
            "businessHours": "10:00-22:00",
        },
    )
    assert store.status_code == 201
    store_id = store.json()["data"]["storeId"]

    product = client.post(
        "/api/products",
        headers=auth_header(owner_token),
        json={
            "storeId": store_id,
            "productName": "Macaron Set",
            "originalPrice": 9000,
            "discountPrice": 4500,
            "quantity": 3,
            "endTime": "2099-07-14T22:00:00+00:00",
        },
    )
    assert product.status_code == 201
    product_data = product.json()["data"]
    assert product_data["discountRate"] == 50

    order = client.post(
        "/api/orders",
        headers=auth_header(customer_token),
        json={
            "storeId": store_id,
            "paymentMethod": "CARD",
            "items": [{"productId": product_data["productId"], "quantity": 2}],
        },
    )
    assert order.status_code == 201
    order_data = order.json()["data"]
    assert order_data["totalPrice"] == 9000
    assert order_data["pickupStatus"] == "READY"

    detail = client.get(f"/api/products/{product_data['productId']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["quantity"] == 1
