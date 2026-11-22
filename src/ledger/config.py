"""環境変数から読み込む設定"""

import os
from dataclasses import dataclass
from typing import Self

DEFAULT_DATABASE_URL = "sqlite:///./ledger.db"


@dataclass(frozen=True)
class Settings:
    # データベースの場所（Dockerではボリューム内に置く）
    database_url: str = DEFAULT_DATABASE_URL
    # 公開したフロントエンドのURL（CORSで許可する）
    frontend_origin: str | None = None
    # デモ環境：起動時にデータが空ならサンプルデータを読み込む
    demo_mode: bool = False

    @classmethod
    def from_env(cls) -> Self:
        return cls(
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
            frontend_origin=os.getenv("FRONTEND_ORIGIN") or None,
            demo_mode=os.getenv("DEMO_MODE") == "1",
        )
