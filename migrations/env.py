"""Alembicの実行環境（マイグレーションの接続先と、比較に使うテーブル定義を決める）"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

import ledger.models  # noqa: F401  テーブル定義を読み込んで Base.metadata に登録する
from ledger.config import Settings
from ledger.db import Base, make_engine

config = context.config
if config.config_file_name is not None:
    # テストから呼んだときに pytest のログ設定を消さないよう、既存のロガーは残す
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# `alembic revision --autogenerate` は、このテーブル定義と実際のデータベースの差分からファイルを作る
target_metadata = Base.metadata
database_url = Settings.from_env().database_url


def run_migrations_offline() -> None:
    """データベースに接続せず、実行するSQLだけを出力する（alembic upgrade --sql）"""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=database_url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLiteは ALTER TABLE でできることが少ないので、テーブルを作り直す方式で変更する
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
