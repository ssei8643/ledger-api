"""Alembicのマイグレーションのテスト"""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from ledger.db import Base, make_engine

ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def test_マイグレーションで作ったテーブルがモデルの定義と一致し元に戻せる(tmp_path, monkeypatch):
    # 一時的なSQLiteのファイルに、マイグレーションを最初から最後まで実行する
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(ALEMBIC_INI))
    command.upgrade(config, "head")

    # models.py の定義と、マイグレーションで作ったテーブルに差がないこと
    # （モデルだけ変えてマイグレーションを作り忘れると、ここで失敗する）
    engine = make_engine(url)
    try:
        with engine.connect() as connection:
            diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        engine.dispose()
    assert diff == []

    # 最初の状態まで戻せること
    command.downgrade(config, "base")
