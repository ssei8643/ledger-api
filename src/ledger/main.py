"""FastAPIアプリの組み立て（設定・データベース・ルーター・エラー処理をつなぐ）"""

from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker

from ledger.chart_of_accounts import seed_accounts
from ledger.config import Settings
from ledger.db import make_engine
from ledger.errors import ConflictError, LedgerError, NotFoundError, RuleViolationError
from ledger.models import Account
from ledger.routers import accounts, bank_import, demo, journal_entries, reports
from ledger.services.demo import load_demo_data_if_empty

LOCAL_FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# 業務ルールのエラーと、APIで返すステータスコードの対応
ERROR_STATUS_CODES: dict[type[LedgerError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    RuleViolationError: 422,
}


def _error_handler(
    status_code: int,
) -> Callable[[Request, Exception], Coroutine[Any, Any, JSONResponse]]:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        # HTTPException と同じ {"detail": "..."} の形で返す（画面側の表示処理はそのまま使える）
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    """アプリを作る。テストでは設定とデータベースを差し替えて呼ぶ"""
    settings = settings or Settings.from_env()
    factory = session_factory or sessionmaker(bind=make_engine(settings.database_url))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # 起動時の準備（以前は import した時点で実行していたので、テストでも実行されていた）
        with factory() as db:
            # テーブルはアプリでは作らず、Alembicのマイグレーションで作る
            if not inspect(db.get_bind()).has_table(Account.__tablename__):
                raise RuntimeError(
                    "テーブルがありません。先に `uv run alembic upgrade head` を実行してください"
                )
            seed_accounts(db)
            if settings.demo_mode:
                load_demo_data_if_empty(db)
        yield

    app = FastAPI(title="ledger-api", lifespan=lifespan)
    app.state.session_factory = factory

    allowed_origins = list(LOCAL_FRONTEND_ORIGINS)
    if settings.frontend_origin:
        allowed_origins.append(settings.frontend_origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for error_class, status_code in ERROR_STATUS_CODES.items():
        app.add_exception_handler(error_class, _error_handler(status_code))

    @app.get("/health", tags=["システム"])
    def health():
        return {"status": "ok"}

    for module in (accounts, journal_entries, reports, bank_import, demo):
        app.include_router(module.router)

    return app


# uvicorn・fastapi dev から使うアプリ（import しただけではデータベースに接続しない）
app = create_app()
