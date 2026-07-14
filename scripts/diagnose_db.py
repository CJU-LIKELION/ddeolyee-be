from app.db import db


def main() -> None:
    db.init_schema()
    row = db.fetch_one("SELECT 1 AS ok")
    print({"database": "ok", "result": row})


if __name__ == "__main__":
    main()

