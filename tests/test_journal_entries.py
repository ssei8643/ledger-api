from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ledger.models import JournalEntry, JournalLine, UnbalancedEntryError
from tests.testdata import COMPOUND_ENTRY, SIMPLE_ENTRY


# ===== 仕訳の登録 =====
def test_貸借が一致する仕訳は登録できる(client):
    res = client.post("/journal-entries", json=SIMPLE_ENTRY)
    assert res.status_code == 201
    assert res.json()["id"] == 1


def test_複合仕訳を登録できる(client):
    res = client.post("/journal-entries", json=COMPOUND_ENTRY)
    assert res.status_code == 201
    assert len(res.json()["lines"]) == 3


def test_貸借が一致しない仕訳は拒否され保存もされない(client):
    bad = {
        **SIMPLE_ENTRY,
        "lines": [
            {"account": "消耗品費", "side": "debit", "amount": 1100},
            {"account": "現金", "side": "credit", "amount": 1000},
        ],
    }
    res = client.post("/journal-entries", json=bad)
    assert res.status_code == 422
    assert client.get("/journal-entries").json() == []


def test_金額が0以下の明細は拒否される(client):
    bad = {
        **SIMPLE_ENTRY,
        "lines": [
            {"account": "消耗品費", "side": "debit", "amount": 0},
            {"account": "現金", "side": "credit", "amount": 0},
        ],
    }
    res = client.post("/journal-entries", json=bad)
    assert res.status_code == 422


def test_存在しない仕訳は404を返す(client):
    res = client.get("/journal-entries/999")
    assert res.status_code == 404


def test_未登録の勘定科目は拒否され保存もされない(client):
    bad = {
        **SIMPLE_ENTRY,
        "lines": [
            {"account": "消耗品費", "side": "debit", "amount": 1100},
            {"account": "現全", "side": "credit", "amount": 1100},
        ],
    }
    res = client.post("/journal-entries", json=bad)
    assert res.status_code == 422
    assert "現全" in res.json()["detail"]
    assert client.get("/journal-entries").json() == []


def test_同じ勘定科目を借方と貸方の両方に使う仕訳は拒否される(client):
    bad = {
        **SIMPLE_ENTRY,
        "lines": [
            {"account": "現金", "side": "debit", "amount": 1000},
            {"account": "現金", "side": "credit", "amount": 1000},
        ],
    }
    res = client.post("/journal-entries", json=bad)
    assert res.status_code == 422
    assert client.get("/journal-entries").json() == []


def test_摘要が200文字を超える仕訳は拒否され保存もされない(client):
    res = client.post("/journal-entries", json={**SIMPLE_ENTRY, "description": "あ" * 201})
    assert res.status_code == 422
    assert client.get("/journal-entries").json() == []


def test_摘要がちょうど200文字の仕訳は登録できる(client):
    res = client.post("/journal-entries", json={**SIMPLE_ENTRY, "description": "あ" * 200})
    assert res.status_code == 201
    assert res.json()["description"] == "あ" * 200


def test_摘要が空白だけの仕訳は拒否される(client):
    res = client.post("/journal-entries", json={**SIMPLE_ENTRY, "description": "   "})
    assert res.status_code == 422


# ===== 訂正仕訳（取消） =====
REVERSE_REQUEST = {"entry_date": "2026-10-28", "reason": "金額誤り"}


def test_仕訳を取り消すと貸借が逆の仕訳が作られる(client):
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    res = client.post("/journal-entries/1/reverse", json=REVERSE_REQUEST)
    assert res.status_code == 201
    body = res.json()
    assert body["reverses_id"] == 1
    sides = {line["account"]: line["side"] for line in body["lines"]}
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


def test_取消が同時に届いても取消仕訳は1つだけで409が返る(client, monkeypatch):
    client.post("/journal-entries", json=SIMPLE_ENTRY)
    client.post("/journal-entries/1/reverse", json=REVERSE_REQUEST)

    # 「まだ取り消されていない」と判定された直後に、別のリクエストが
    # 先に取消仕訳を保存した状況を再現する（確認の結果を常に「なし」にする）
    monkeypatch.setattr(Session, "scalar", lambda self, *args, **kwargs: None)
    res = client.post("/journal-entries/1/reverse", json=REVERSE_REQUEST)
    monkeypatch.undo()

    assert res.status_code == 409
    assert len(client.get("/journal-entries").json()) == 2


# ===== APIを通らない経路（データベースを直接使う） =====
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


# ===== テンプレート =====
def test_テンプレートの科目はすべて勘定科目マスタに存在する(client):
    templates = client.get("/templates").json()
    account_names = {a["name"] for a in client.get("/accounts").json()}

    assert len(templates) > 0
    for t in templates:
        for line in t["lines"]:
            assert line["account"] in account_names
