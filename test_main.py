from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import (
    Base,
    JournalEntry,
    JournalLine,
    UnbalancedEntryError,
    app,
    get_db,
    seed_accounts,
)


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
def test_貸借が一致する仕訳は登録できる(client):
    res = client.post("/journal-entries", json=SIMPLE_ENTRY)
    assert res.status_code == 201
    assert res.json()["id"] == 1


def test_複合仕訳を登録できる(client):
    res = client.post("/journal-entries", json=COMPOUND_ENTRY)
    assert res.status_code == 201
    assert len(res.json()["lines"]) == 3


def test_貸借が一致しない仕訳は拒否され保存もされない(client):
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


def test_仕訳を取り消すと貸借が逆の仕訳が作られる(client):
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


# ===== APIを通らない経路のテスト（データベースを直接使う） =====
@pytest.fixture
def db():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    with sessionmaker(bind=test_engine)() as session:
        seed_accounts(session)
        yield session


def add_entry_directly(db, lines):
    db.add(
        JournalEntry(
            entry_date=date(2026, 11, 1),
            description="APIを通さずに作った仕訳",
            lines=[JournalLine(account=a, side=s, amount=amt) for a, s, amt in lines],
        )
    )


def test_APIを通らない経路でも貸借が一致しない仕訳は保存されない(db):
    add_entry_directly(db, [("現金", "debit", 1000), ("売上高", "credit", 900)])
    with pytest.raises(UnbalancedEntryError):
        db.commit()
    db.rollback()
    assert db.scalar(select(func.count(JournalEntry.id))) == 0


def test_APIを通らない経路でも未登録の勘定科目は保存されない(db):
    add_entry_directly(db, [("現全", "debit", 1000), ("売上高", "credit", 1000)])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.scalar(select(func.count(JournalEntry.id))) == 0


# ===== 評価勘定（残高の向きの上書き）のテスト =====
DEPRECIATION_ENTRY = {
    "entry_date": "2026-12-31",
    "description": "減価償却（間接法）",
    "lines": [
        {"account": "減価償却費", "side": "debit", "amount": 5000},
        {"account": "減価償却累計額", "side": "credit", "amount": 5000},
    ],
}


def test_減価償却累計額は貸方残高でも警告が出ない(client):
    client.post("/journal-entries", json=OPENING_ENTRY)
    client.post("/journal-entries", json=DEPRECIATION_ENTRY)

    rows = {r["account"]: r for r in client.get("/trial-balance").json()["rows"]}
    assert rows["減価償却累計額"]["credit_balance"] == 5000
    assert rows["減価償却累計額"]["warning"] is None


def test_減価償却累計額は貸借対照表で資産から差し引かれる(client):
    client.post("/journal-entries", json=OPENING_ENTRY)  # 資産 61,000
    client.post("/journal-entries", json=DEPRECIATION_ENTRY)

    bs = client.get("/financial-statements").json()["balance_sheet"]
    assert bs["total_assets"] == 61000 - 5000
    assert bs["total_liabilities_and_equity"] == 61000 - 5000
    assert bs["is_balanced"] is True

# ===== 総勘定元帳のテスト =====
def test_総勘定元帳で残高の推移がわかる(client):
    client.post("/journal-entries", json=OPENING_ENTRY)
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    rows = client.get("/accounts/現金/ledger").json()
    assert [r["balance"] for r in rows] == [50000, 48900]


def test_貸方の科目は貸方で残高が増える(client):
    client.post("/journal-entries", json=OPENING_ENTRY)
    rows = client.get("/accounts/元入金/ledger").json()
    assert rows[0]["credit"] == 61000
    assert rows[0]["balance"] == 61000


def test_存在しない科目の元帳は404を返す(client):
    assert client.get("/accounts/現全/ledger").status_code == 404


# ===== 損益計算書・貸借対照表のテスト =====
SALES_ENTRY = {
    "entry_date": "2026-11-05",
    "description": "B社へ売上（掛け）",
    "lines": [
        {"account": "売掛金", "side": "debit", "amount": 33000},
        {"account": "売上高", "side": "credit", "amount": 33000},
    ],
}


def test_損益計算書で当期純利益が計算される(client):
    client.post("/journal-entries", json=OPENING_ENTRY)
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    client.post("/journal-entries", json=SALES_ENTRY)

    pl = client.get("/financial-statements").json()["income_statement"]
    assert pl["total_revenue"] == 33000
    assert pl["total_expense"] == 1100
    assert pl["net_income"] == 31900


def test_貸借対照表は当期純利益を含めて左右が一致する(client):
    client.post("/journal-entries", json=OPENING_ENTRY)
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    client.post("/journal-entries", json=SALES_ENTRY)

    bs = client.get("/financial-statements").json()["balance_sheet"]
    assert bs["net_income"] == 31900
    assert bs["total_assets"] == 92900
    assert bs["total_liabilities_and_equity"] == 92900
    assert bs["is_balanced"] is True

    # ===== サンプルデータのテスト =====
def test_サンプルデータを読み込むと財務諸表が作られる(client):
    res = client.post("/demo-data")
    assert res.status_code == 201
    assert res.json()["created"] == 13

    fs = client.get("/financial-statements").json()
    assert fs["income_statement"]["net_income"] == 206420
    assert fs["balance_sheet"]["total_assets"] == 556420
    assert fs["balance_sheet"]["is_balanced"] is True


def test_仕訳があるとサンプルデータは読み込めない(client):
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    assert client.post("/demo-data").status_code == 409

# ===== テンプレートのテスト =====
def test_テンプレートの科目はすべて勘定科目マスタに存在する(client):
    templates = client.get("/templates").json()
    account_names = {a["name"] for a in client.get("/accounts").json()}

    assert len(templates) > 0
    for t in templates:
        for line in t["lines"]:
            assert line["account"] in account_names

# ===== 月別集計のテスト =====
def test_月別に収益と費用が集計される(client):
    client.post("/journal-entries", json=OPENING_ENTRY)  # 収益・費用を含まない
    client.post("/journal-entries", json=SIMPLE_ENTRY)   # 10月：消耗品費 1,100
    client.post("/journal-entries", json=SALES_ENTRY)    # 11月：売上高 33,000

    rows = client.get("/monthly-summary").json()
    assert rows == [
        {"month": "2026-10", "revenue": 0, "expense": 1100, "net_income": -1100},
        {"month": "2026-11", "revenue": 33000, "expense": 0, "net_income": 33000},
    ]


def test_サンプルデータの月別純利益は損益計算書と一致する(client):
    client.post("/demo-data")
    rows = client.get("/monthly-summary").json()
    pl = client.get("/financial-statements").json()["income_statement"]

    assert len(rows) == 1
    assert rows[0]["net_income"] == pl["net_income"]

# ===== 銀行明細CSVの取り込みのテスト =====
SAMPLE_CSV = (
    "日付,摘要,出金,入金\n"
    "2026-12-01,ﾌﾘｺﾐ ｴｰｼｬ,,88000\n"
    "2026-12-03,ドコモ 携帯料金,5500,\n"
    "2026-12-25,ﾎｰﾑｾﾝﾀｰ ｶｲﾓﾉ,880,\n"
)


def preview_drafts(client):
    return client.post("/bank-import/preview", json={"csv_text": SAMPLE_CSV}).json()


def test_CSVの摘要から勘定科目が推測される(client):
    drafts = preview_drafts(client)
    assert [d["account"] for d in drafts] == ["売掛金", "通信費", None]
    assert [d["direction"] for d in drafts] == ["in", "out", "out"]


def test_取り込んだ明細から仕訳が作られる(client):
    drafts = preview_drafts(client)
    drafts[2]["account"] = "消耗品費"
    res = client.post("/bank-import", json={"drafts": drafts})
    assert res.status_code == 201

    rows = {r["account"]: r for r in client.get("/trial-balance").json()["rows"]}
    assert rows["普通預金"]["debit_balance"] == 88000 - 5500 - 880


def test_同じ明細は二重に取り込めない(client):
    drafts = preview_drafts(client)
    drafts[2]["account"] = "消耗品費"
    client.post("/bank-import", json={"drafts": drafts})

    again = preview_drafts(client)
    assert all(d["already_imported"] for d in again)
    assert client.post("/bank-import", json={"drafts": drafts}).status_code == 409


def test_勘定科目が未選択の明細は取り込めない(client):
    drafts = preview_drafts(client)
    assert client.post("/bank-import", json={"drafts": drafts}).status_code == 422


def test_CSVの見出しが違うとエラーになる(client):
    res = client.post("/bank-import/preview", json={"csv_text": "date,memo,out,in\n"})
    assert res.status_code == 422