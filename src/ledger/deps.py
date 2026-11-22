"""エンドポイントに渡す共通の依存（データベースのセッションなど）"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session


def get_db(request: Request) -> Iterator[Session]:
    # セッションの作り方は create_app() で決めて app.state に置いておく
    # （テストではメモリ上のデータベースにつながるものに差し替える）
    with request.app.state.session_factory() as db:
        yield db


DbSession = Annotated[Session, Depends(get_db)]
