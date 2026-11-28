"""銀行ごとのCSVの形式の違いを吸収できるかのテスト（データベースを使わない）"""

from datetime import date

import pytest

from ledger.bank_csv import BankCsvError, parse_bank_csv, parse_date
from tests.testdata import read_sample


# ===== 日付・列名・金額の書き方 =====
@pytest.mark.parametrize(
    "text",
    ["2026-12-01", "2026/12/01", "20261201", "2026.12.01", "2026年12月1日", "2026/12/1"],
)
def test_いろいろな日付の書き方を読み取れる(text):
    assert parse_date(text) == date(2026, 12, 1)


def test_列名や並び順が違うCSVも読み取れる():
    # 「取引日・入金・出金・備考」の順で、日付は区切りなし、新しい順に並んでいる
    rows = parse_bank_csv("取引日,入金,出金,備考\n20261210,,50000,ｼｮｳﾃﾝ\n20261202,60000,,ﾜｲ ATM\n")
    assert [(r.entry_date.day, r.direction, r.amount) for r in rows] == [
        (2, "in", 60000),
        (10, "out", 50000),
    ]


def test_入出金が1列でマイナスが出金のCSVも読み取れる():
    rows = parse_bank_csv(
        '日付,摘要,入出金（円）\n2026/12/01,ﾌﾘｺﾐ ｴｰｼｬ,"88,000"\n2026/12/03,ドコモ,"−5,500"\n'
    )
    assert [(r.direction, r.amount) for r in rows] == [("in", 88000), ("out", 5500)]


def test_金額の空欄やハイフンは0として扱い追加摘要はつなげる():
    rows = parse_bank_csv(
        '勘定日,摘要,追加摘要,お引出し,お預入れ\n2026年12月1日,ﾌﾘｺﾐ,ｴｰｼｬ,-,"1,000"\n'
    )
    assert rows[0].direction == "in"
    assert rows[0].amount == 1000
    assert rows[0].description == "ﾌﾘｺﾐ ｴｰｼｬ"


def test_読めない行は行番号つきのエラーになる():
    with pytest.raises(BankCsvError, match="2行目"):
        parse_bank_csv("日付,摘要,出金,入金\n2026-13-01,存在しない日付,100,\n")


def test_摘要が長すぎる行は行番号つきのエラーになる():
    with pytest.raises(BankCsvError, match="2行目の摘要が長すぎます"):
        parse_bank_csv("日付,摘要,出金,入金\n2026-12-01," + "あ" * 201 + ",100,\n")


def test_摘要が空の行は摘要なしとして読み取る():
    rows = parse_bank_csv("日付,摘要,出金,入金\n2026-12-01,,100,\n")
    assert rows[0].description == "（摘要なし）"


# ===== samples/ フォルダのサンプルCSV =====
@pytest.mark.parametrize(
    "name, count",
    [
        ("sample1_newest_first_hankaku.csv", 7),
        ("sample2_single_column_signed.csv", 6),
        ("sample3_shiftjis_hyphen_kanjidate.csv", 5),
        ("sample4_current_format.csv", 6),
    ],
)
def test_サンプルCSVはすべて読み取れて日付順に並ぶ(name, count):
    rows = parse_bank_csv(read_sample(name))
    assert len(rows) == count
    assert rows == sorted(rows, key=lambda r: r.entry_date)
