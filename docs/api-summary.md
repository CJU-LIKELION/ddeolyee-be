# API Summary

Sources:

- `C:\Users\leagu\Downloads\api-docs.html`
- `docs/notion-export/part-1/6팀 (고성노) 74c94861f90b83f2adfe011df096c35a.md`

The Notion page was read from the exported Markdown/CSV zip.

## Current Backend Stack

- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Pydantic
- Uvicorn
- pytest

The first prototype was started with H2, but the backend has been moved to PostgreSQL because FastAPI + PostgreSQL is more stable for Python development and frontend integration.

## Implemented Groups

- Auth: signup, login, token reissue, email availability
- Users: profile, profile update, withdrawal, location, points
- Stores: owner store CRUD, nearby search, store products/reviews/orders
- Products: create, feed search, detail, update, delete
- Orders: create, my orders, detail, cancel, complete
- Reviews: create by order, my reviews, update, delete
- Favorites: create, list mine, delete

## Plan-Specific Behavior

- Products become `EXPIRED` automatically once `endTime` has passed.
- Orders decrement product stock immediately.
- Sold out products switch to `SOLD_OUT`.
- Order cancel restores stock and point balance.
- Product/store feeds support distance, discount, price, and end-time sorting.
- Order detail includes store coordinates for pickup-map rendering.

## Not Yet Implemented

These appear in the user flow but not in the supplied API contract:

- Separate cart resources
- Event list/detail resources

