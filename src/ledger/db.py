"""データベース接続"""

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_engine(url: str, **kwargs: Any) -> Engine:
    """データベースの種類に合わせた設定でエンジンを作る"""
    if url.startswith("sqlite"):
        # FastAPIは複数のスレッドからリクエストを処理するので、SQLiteの同一スレッド制限を外す
        kwargs.setdefault("connect_args", {"check_same_thread": False})
    engine = create_engine(url, **kwargs)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def _enable_sqlite_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
    # SQLiteは外部キー制約を既定では検査しないので、接続するたびに有効にする
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
