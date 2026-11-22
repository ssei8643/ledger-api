from ledger.schemas import JournalEntryCreate
from ledger.services import journal, reports
from tests.testdata import (
    COMPOUND_ENTRY,
    DEPRECIATION_ENTRY,
    OPENING_ENTRY,
    SALES_ENTRY,
    SIMPLE_ENTRY,
)


# ===== 合計残高試算表と残高の警告 =====
def test_試算表の借方合計と貸方合計が一致する(client):
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    client.post("/journal-entries", json=COMPOUND_ENTRY)

    tb = client.get("/trial-balance").json()
    assert tb["debit_total"] == 12100
    assert tb["credit_total"] == 12100
    assert tb["is_balanced"] is True

    balances = {r["account"]: r for r in tb["rows"]}
    assert balances["普通預金"]["debit_balance"] == 10780
    assert (
        balances["売掛金"]["credit_balance"] == 11000
    )  # ===== 勘定科目マスタと残高警告のテスト =====


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


# ===== 評価勘定（残高の向きの上書き） =====
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


# ===== 総勘定元帳 =====
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


# ===== 損益計算書・貸借対照表 =====
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


# ===== 月別集計 =====
def test_月別に収益と費用が集計される(client):
    client.post("/journal-entries", json=OPENING_ENTRY)  # 収益・費用を含まない
    client.post("/journal-entries", json=SIMPLE_ENTRY)  # 10月：消耗品費 1,100
    client.post("/journal-entries", json=SALES_ENTRY)  # 11月：売上高 33,000

    rows = client.get("/monthly-summary").json()
    assert rows == [
        {"month": "2026-10", "revenue": 0, "expense": 1100, "net_income": -1100},
        {"month": "2026-11", "revenue": 33000, "expense": 0, "net_income": 33000},
    ]


# ===== サービスを直接呼ぶテスト（HTTPを通さない） =====
def test_HTTPを通さずにサービスを直接呼んでも試算表を作れる(db):
    journal.create_entry(db, JournalEntryCreate(**SIMPLE_ENTRY))
    journal.create_entry(db, JournalEntryCreate(**COMPOUND_ENTRY))

    tb = reports.trial_balance(db)
    assert tb.debit_total == tb.credit_total == 12100
    assert tb.is_balanced is True
