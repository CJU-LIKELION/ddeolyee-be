from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, CursorResult, Row
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.models import Base


class DatabaseNotConfigured(RuntimeError):
    pass


class CursorAdapter:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self.result: CursorResult[Any] | None = None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        statement, named_params = _convert_positional_params(sql, list(params))
        self.result = self.connection.execute(text(statement), named_params)

    def fetchone(self) -> Row[Any] | None:
        if self.result is None:
            return None
        return self.result.fetchone()

    def fetchall(self) -> list[Row[Any]]:
        if self.result is None:
            return []
        return list(self.result.fetchall())


class ConnectionAdapter:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def cursor(self) -> CursorAdapter:
        return CursorAdapter(self.connection)


class PostgresDatabase:
    def __init__(self) -> None:
        self.settings = get_settings()
        try:
            self.engine = create_engine(self.settings.database_url, pool_pre_ping=True, future=True)
        except SQLAlchemyError as exc:
            raise DatabaseNotConfigured(str(exc)) from exc

    def init_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def transaction(self):
        try:
            with self.engine.begin() as connection:
                yield ConnectionAdapter(connection)
        except SQLAlchemyError:
            raise

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self.transaction() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return None
            return self._row_to_dict(cur, row)

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            return [self._row_to_dict(cur, row) for row in cur.fetchall()]

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self.transaction() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)

    def insert_and_get_id(self, sql: str, params: Iterable[Any], table: str, id_column: str) -> int:
        with self.transaction() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            key_cur = conn.cursor()
            key_cur.execute(f"SELECT MAX({id_column}) FROM {table}")
            row = key_cur.fetchone()
            if row is None:
                raise RuntimeError("Failed to read generated id.")
            return int(row[0])

    @staticmethod
    def _row_to_dict(_cur: CursorAdapter, row: Row[Any]) -> dict[str, Any]:
        return dict(row._mapping)


def _convert_positional_params(sql: str, params: list[Any]) -> tuple[str, dict[str, Any]]:
    index = 0

    def replace(_match: re.Match[str]) -> str:
        nonlocal index
        name = f"p{index}"
        index += 1
        return f":{name}"

    statement = re.sub(r"\?", replace, sql)
    return statement, {f"p{i}": value for i, value in enumerate(params)}


db = PostgresDatabase()

