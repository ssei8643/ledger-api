import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ledger.chart_of_accounts import seed_accounts
from ledger.config import Settings, normalize_database_url
from ledger.db import Base, make_engine
from ledger.main import create_app

# 既定はメモリ上のSQLite。TEST_DATABASE_URL を指定すると、同じテストをPostgreSQLでも実行できる（CIで使う）
TEST_DATABASE_URL = normalize_database_url(os.getenv("TEST_DATABASE_URL", "sqlite://"))


@pytest.fixture(autouse=True)
def no_real_ai(monkeypatch):
    # 手元にAPIキーが設定されていても、テストでは本物のAIを呼ばない
    # （費用がかかる・結果が毎回同じとは限らない・ネットがないと失敗する）
    # AIを使うテストでは、偽のキーと偽の応答を自分で用意する
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def session_factory():
    # テストごとにテーブルを作り直し、まっさらな状態から始める
    if TEST_DATABASE_URL.startswith("sqlite"):
        # メモリ上のSQLiteは接続ごとに別のDBになるので、StaticPoolで1つの接続を共有する
        engine = make_engine(TEST_DATABASE_URL, poolclass=StaticPool)
    else:
        engine = make_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(session_factory):
    # 環境変数に左右されないよう、設定とデータベースを明示してアプリを作る
    app = create_app(settings=Settings(), session_factory=session_factory)
    with TestClient(app) as c:  # with で起動時の処理（勘定科目の登録）も実行される
        yield c


@pytest.fixture
def db(session_factory):
    # APIを通さずに、サービスやデータベースを直接使うテスト用
    with session_factory() as session:
        seed_accounts(session)
        yield session
