import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import Base, app, get_db, seed_accounts


# ===== テストの準備：毎回まっさらなメモリ上のDBを使う =====
@pytest.fixture
def client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine)
    with TestSession() as db:
        seed_accounts(db)

    def override_get_db():
        with TestSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ===== テストデータ =====
SIMPLE_ENTRY = {
    "entry_date": "2026-10-24",
    "description": "コピー用紙購入",
    "lines": [
        {"account": "消耗品費", "side": "debit", "amount": 1100},
        {"account": "現金", "side": "credit", "amount": 1100},
    ],
}

COMPOUND_ENTRY = {
    "entry_date": "2026-10-24",
    "description": "A社売掛金入金（振込手数料差引）",
    "lines": [
        {"account": "普通預金", "side": "debit", "amount": 10780},
        {"account": "支払手数料", "side": "debit", "amount": 220},
        {"account": "売掛金", "side": "credit", "amount": 11000},
    ],
}


# ===== テスト本体 =====
def test_借貸が一致する仕訳は登録できる(client):
    res = client.post("/journal-entries", json=SIMPLE_ENTRY)
    assert res.status_code == 201
    assert res.json()["id"] == 1


def test_複合仕訳を登録できる(client):
    res = client.post("/journal-entries", json=COMPOUND_ENTRY)
    assert res.status_code == 201
    assert len(res.json()["lines"]) == 3


def test_借貸が一致しない仕訳は拒否され保存もされない(client):
    bad = {**SIMPLE_ENTRY, "lines": [
        {"account": "消耗品費", "side": "debit", "amount": 1100},
        {"account": "現金", "side": "credit", "amount": 1000},
    ]}
    res = client.post("/journal-entries", json=bad)
    assert res.status_code == 422
    assert client.get("/journal-entries").json() == []


def test_金額が0以下の明細は拒否される(client):
    bad = {**SIMPLE_ENTRY, "lines": [
        {"account": "消耗品費", "side": "debit", "amount": 0},
        {"account": "現金", "side": "credit", "amount": 0},
    ]}
    res = client.post("/journal-entries", json=bad)
    assert res.status_code == 422


def test_存在しない仕訳は404を返す(client):
    res = client.get("/journal-entries/999")
    assert res.status_code == 404


def test_試算表の借方合計と貸方合計が一致する(client):
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    client.post("/journal-entries", json=COMPOUND_ENTRY)

    tb = client.get("/trial-balance").json()
    assert tb["debit_total"] == 12100
    assert tb["credit_total"] == 12100
    assert tb["is_balanced"] is True

    balances = {r["account"]: r for r in tb["rows"]}
    assert balances["普通預金"]["debit_balance"] == 10780
    assert balances["売掛金"]["credit_balance"] == 11000# ===== 勘定科目マスタと残高警告のテスト =====
OPENING_ENTRY = {
    "entry_date": "2026-10-01",
    "description": "開始仕訳（期首残高）",
    "lines": [
        {"account": "現金", "side": "debit", "amount": 50000},
        {"account": "売掛金", "side": "debit", "amount": 11000},
        {"account": "元入金", "side": "credit", "amount": 61000},
    ],
}


def test_未登録の勘定科目は拒否され保存もされない(client):
    bad = {**SIMPLE_ENTRY, "lines": [
        {"account": "消耗品費", "side": "debit", "amount": 1100},
        {"account": "現全", "side": "credit", "amount": 1100},
    ]}
    res = client.post("/journal-entries", json=bad)
    assert res.status_code == 422
    assert "現全" in res.json()["detail"]
    assert client.get("/journal-entries").json() == []


def test_期首残高がないと資産の貸方残高に警告が出る(client):
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    client.post("/journal-entries", json=COMPOUND_ENTRY)

    tb = client.get("/trial-balance").json()
    rows = {r["account"]: r for r in tb["rows"]}
    assert tb["warning_count"] == 2
    assert rows["現金"]["warning"] is not None
    assert rows["売掛金"]["warning"] is not None
    assert rows["消耗品費"]["warning"] is None


def test_開始仕訳を登録すると警告が消える(client):
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    client.post("/journal-entries", json=COMPOUND_ENTRY)
    client.post("/journal-entries", json=OPENING_ENTRY)

    tb = client.get("/trial-balance").json()
    rows = {r["account"]: r for r in tb["rows"]}
    assert tb["warning_count"] == 0
    assert rows["現金"]["debit_balance"] == 48900
    assert tb["debit_total"] == 73100
    assert tb["credit_total"] == 73100
    

# ===== 訂正仕訳のテスト =====
REVERSE_REQUEST = {"entry_date": "2026-10-28", "reason": "金額誤り"}


def test_仕訳を取り消すと借貸が逆の仕訳が作られる(client):
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    res = client.post("/journal-entries/1/reverse", json=REVERSE_REQUEST)
    assert res.status_code == 201
    body = res.json()
    assert body["reverses_id"] == 1
    sides = {l["account"]: l["side"] for l in body["lines"]}
    assert sides == {"消耗品費": "credit", "現金": "debit"}


def test_取り消すと残高は元に戻り元の仕訳は残る(client):
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    client.post("/journal-entries/1/reverse", json=REVERSE_REQUEST)

    tb = client.get("/trial-balance").json()
    rows = {r["account"]: r for r in tb["rows"]}
    assert rows["消耗品費"]["debit_balance"] == 0
    assert rows["消耗品費"]["credit_balance"] == 0
    assert client.get("/journal-entries/1").status_code == 200


def test_同じ仕訳は二重に取り消せない(client):
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    client.post("/journal-entries/1/reverse", json=REVERSE_REQUEST)
    res = client.post("/journal-entries/1/reverse", json=REVERSE_REQUEST)
    assert res.status_code == 409


def test_取消仕訳はさらに取り消せない(client):
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    client.post("/journal-entries/1/reverse", json=REVERSE_REQUEST)
    res = client.post("/journal-entries/2/reverse", json=REVERSE_REQUEST)
    assert res.status_code == 422