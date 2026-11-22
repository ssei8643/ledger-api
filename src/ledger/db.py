"""データベース接続"""

from typing import Any

from sqlalchemy import Engine, MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase

# 制約・インデックスの名前の付け方を決めておく。名前がないと、データベースによって
# 自動で付く名前が変わり、Alembicのマイグレーションで制約を変更・削除できなくなる
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


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
    # （PostgreSQLは最初から検査するので不要）
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
