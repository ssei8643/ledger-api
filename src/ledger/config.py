"""環境変数から読み込む設定"""

import os
from dataclasses import dataclass
from typing import Self

DEFAULT_DATABASE_URL = "sqlite:///./ledger.db"


def normalize_database_url(url: str) -> str:
    """PostgreSQLのURLを、このアプリで使うドライバ（psycopg 3）向けの書き方にそろえる

    Renderなどのホスティングサービスは "postgres://..." や "postgresql://..." の形でURLを渡すが、
    SQLAlchemyはドライバの指定がないと psycopg2 を使おうとするため、明示的に書き換える。
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


@dataclass(frozen=True)
class Settings:
    # データベースの場所（SQLite・PostgreSQLのどちらでも動く）
    database_url: str = DEFAULT_DATABASE_URL
    # 公開したフロントエンドのURL（CORSで許可する）
    frontend_origin: str | None = None
    # デモ環境：起動時にデータが空ならサンプルデータを読み込む
    demo_mode: bool = False

    @classmethod
    def from_env(cls) -> Self:
        return cls(
            database_url=normalize_database_url(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)),
            frontend_origin=os.getenv("FRONTEND_ORIGIN") or None,
            demo_mode=os.getenv("DEMO_MODE") == "1",
        )
