from tests.testdata import SIMPLE_ENTRY


# ===== サンプルデータ =====
def test_サンプルデータを読み込むと財務諸表が作られる(client):
    res = client.post("/demo-data")
    assert res.status_code == 201
    assert res.json()["created"] == 13

    fs = client.get("/financial-statements").json()
    assert fs["income_statement"]["net_income"] == 206420
    assert fs["balance_sheet"]["total_assets"] == 556420
    assert fs["balance_sheet"]["is_balanced"] is True


def test_サンプルデータの試算表は合計と残高がそれぞれ一致する(client):
    client.post("/demo-data")
    tb = client.get("/trial-balance").json()

    # 合計：すべての仕訳の借方・貸方の金額をそのまま足したもの
    assert tb["debit_total"] == tb["credit_total"] == 788920
    # 残高：科目ごとに借方と貸方を差し引いた残りを足したもの
    assert tb["debit_balance_total"] == tb["credit_balance_total"] == 592000
    assert tb["is_balanced"] is True


def test_仕訳があるとサンプルデータは読み込めない(client):
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    assert client.post("/demo-data").status_code == 409


def test_サンプルデータの月別純利益は損益計算書と一致する(client):
    client.post("/demo-data")
    rows = client.get("/monthly-summary").json()
    pl = client.get("/financial-statements").json()["income_statement"]

    assert len(rows) == 1
    assert rows[0]["net_income"] == pl["net_income"]
