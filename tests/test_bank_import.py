from sqlalchemy.orm import Session

from ledger import ai_suggest
from tests.testdata import read_sample

# ===== 銀行明細CSVの取り込み =====
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


def test_取り込みが同時に届いても二重には登録されず409が返る(client, monkeypatch):
    drafts = preview_drafts(client)
    drafts[2]["account"] = "消耗品費"
    client.post("/bank-import", json={"drafts": drafts})

    # 登録直前の確認（取り込み済みの件数）を常に0にして、別のリクエストに
    # 先を越された状況を再現する。データベースの一意制約で弾かれるはず
    monkeypatch.setattr(Session, "scalar", lambda self, *args, **kwargs: 0)
    res = client.post("/bank-import", json={"drafts": drafts})
    monkeypatch.undo()

    assert res.status_code == 409
    assert len(client.get("/journal-entries").json()) == 3


def test_勘定科目が未選択の明細は取り込めない(client):
    drafts = preview_drafts(client)
    assert client.post("/bank-import", json={"drafts": drafts}).status_code == 422


def test_相手科目に普通預金を選んだ明細は取り込めない(client):
    drafts = preview_drafts(client)
    drafts[2]["account"] = "普通預金"
    res = client.post("/bank-import", json={"drafts": drafts})
    assert res.status_code == 422
    assert client.get("/journal-entries").json() == []


# ===== samples/ のCSVを使った取り込み =====
def preview_sample(client, name):
    csv_text = read_sample(name)
    return client.post("/bank-import/preview", json={"csv_text": csv_text}).json()


def test_半角カナの振込手数料も支払手数料と推測され推測できないものは空欄のまま(client):
    accounts = {
        d["description"]: d["account"]
        for d in preview_sample(client, "sample1_newest_first_hankaku.csv")
    }
    assert accounts["ﾌﾘｺﾐﾃｽｳﾘﾖｳ"] == "支払手数料"
    assert accounts["ｺﾝﾋﾞﾆ ﾏﾙﾏﾙﾃﾝ"] is None


def test_同じ日に同じ内容の明細が2件あっても別々の明細として扱われる(client):
    drafts = preview_sample(client, "sample4_current_format.csv")
    copies = [d for d in drafts if d["description"] == "コピー用紙"]
    assert len(copies) == 2
    assert copies[0]["import_key"] != copies[1]["import_key"]


def test_ATMは入金なら事業主借と推測される(client):
    csv_text = "取引日,入金,出金,備考\n20261202,60000,,ﾜｲ ATM\n20261203,,30000,ATM ｼｭｯｷﾝ\n"
    drafts = client.post("/bank-import/preview", json={"csv_text": csv_text}).json()
    assert [d["account"] for d in drafts] == ["事業主借", "事業主貸"]


def test_CSVの見出しが違うとエラーになる(client):
    res = client.post("/bank-import/preview", json={"csv_text": "date,memo,out,in\n"})
    assert res.status_code == 422


# ===== AIによる勘定科目の推測（本物のAIは呼ばず、偽の応答を使う） =====
def use_fake_ai(monkeypatch, answer_for):
    """摘要ごとの答えを決めた偽のAIを使う。AIに渡された内容を記録して返す"""
    sent = []

    def fake(items, accounts):
        sent.extend(items)
        return [
            {"index": i, "account": answer_for[desc]}
            for i, (desc, _direction) in enumerate(items)
            if desc in answer_for
        ]

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai_suggest, "_ask_claude", fake)
    return sent


def test_ルールで推測できない明細だけAIが推測し印がつく(client, monkeypatch):
    sent = use_fake_ai(monkeypatch, {"ﾎｰﾑｾﾝﾀｰ ｶｲﾓﾉ": "消耗品費"})
    drafts = preview_drafts(client)

    assert [d["account"] for d in drafts] == ["売掛金", "通信費", "消耗品費"]
    assert [d["suggested_by"] for d in drafts] == ["rule", "rule", "ai"]
    # AIに送るのはルールで推測できなかった明細の摘要と入出金だけ（日付や金額は送らない）
    assert sent == [("ﾎｰﾑｾﾝﾀｰ ｶｲﾓﾉ", "out")]


def test_APIキーがなければ今まで通り空欄のまま(client):
    drafts = preview_drafts(client)
    assert drafts[2]["account"] is None
    assert drafts[2]["suggested_by"] is None


def test_取り込み済みの明細はAIに送らない(client, monkeypatch):
    drafts = preview_drafts(client)
    drafts[2]["account"] = "消耗品費"
    client.post("/bank-import", json={"drafts": drafts})

    sent = use_fake_ai(monkeypatch, {"ﾎｰﾑｾﾝﾀｰ ｶｲﾓﾉ": "消耗品費"})
    preview_drafts(client)
    assert sent == []


def test_AIが推測した科目も登録時には普通にチェックされる(client, monkeypatch):
    use_fake_ai(monkeypatch, {"ﾎｰﾑｾﾝﾀｰ ｶｲﾓﾉ": "消耗品費"})
    drafts = preview_drafts(client)
    # 画面で人が書き換えた場合も、未登録の科目はこれまで通り拒否される
    drafts[2]["account"] = "存在しない科目"
    assert client.post("/bank-import", json={"drafts": drafts}).status_code == 422
