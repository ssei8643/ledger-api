"""銀行の入出金明細CSVを読み取る。

銀行ごとに違う「列名」「日付の書き方」「金額の書き方」をここで吸収し、
アプリの中では同じ形（BankRow）として扱えるようにする。
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date


class BankCsvError(ValueError):
    """CSVを読み取れなかったときのエラー（メッセージはそのまま画面に出す）"""


@dataclass
class BankRow:
    entry_date: date
    description: str
    direction: str  # "in"（入金）または "out"（出金）
    amount: int


# 列名の別名。見出しは全角・半角や「(円)」の有無をそろえてから比べる
DATE_COLUMNS = ["日付", "取引日", "勘定日"]
DESCRIPTION_COLUMNS = ["摘要", "入出金内容", "お取り扱い内容", "詳細1", "備考"]
EXTRA_DESCRIPTION_COLUMNS = ["追加摘要", "詳細2"]  # あれば摘要のうしろにつなげる
OUT_COLUMNS = ["出金", "出金金額", "お引出し", "支払金額"]
IN_COLUMNS = ["入金", "入金金額", "お預入れ", "預入金額"]
SIGNED_COLUMNS = ["入出金", "入出金額", "入出金金額"]  # 1列で、マイナスなら出金

HEADER_ERROR = (
    "1行目の見出しから、日付・摘要・金額の列が見つかりません。"
    "対応している列名：日付（" + "・".join(DATE_COLUMNS) + "）、"
    "摘要（" + "・".join(DESCRIPTION_COLUMNS) + "）、"
    "金額（出金と入金の2列、または入出金の1列）"
)

DATE_PATTERNS = [
    re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})"),  # 2026-12-01, 2026/12/1, 2026.12.01
    re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"),  # 2026年12月1日
    re.compile(r"(\d{4})(\d{2})(\d{2})"),  # 20261201
]


def normalize_header(name: str) -> str:
    # 「出金金額（円）」→「出金金額」のように、全角をそろえて単位と空白を取る
    text = unicodedata.normalize("NFKC", name or "").replace(" ", "")
    return re.sub(r"\(円\)$", "", text)


def parse_date(value: str) -> date:
    text = unicodedata.normalize("NFKC", value or "").strip()
    for pattern in DATE_PATTERNS:
        m = pattern.fullmatch(text)
        if m:
            year, month, day = (int(g) for g in m.groups())
            return date(year, month, day)  # 存在しない日付なら ValueError
    raise ValueError(f"日付として読めません: {value}")


def parse_amount(value: str) -> int:
    # 「1,000」「1,000円」に対応し、空欄や「-」「−」は0として扱う
    text = unicodedata.normalize("NFKC", value or "").strip()
    text = text.replace(",", "").replace("円", "").replace("−", "-")
    if text in ("", "-"):
        return 0
    return int(text)


def _cell(row: list[str], col: int | None) -> str:
    # 列が見つからない・行の列数が足りないときは空欄として扱う
    return row[col] if col is not None and col < len(row) else ""


def parse_bank_csv(text: str) -> list[BankRow]:
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows:
        raise BankCsvError(HEADER_ERROR)

    columns = {normalize_header(h): i for i, h in enumerate(rows[0])}

    def find(candidates: list[str]) -> int | None:
        return next((columns[c] for c in candidates if c in columns), None)

    date_col = find(DATE_COLUMNS)
    desc_col = find(DESCRIPTION_COLUMNS)
    extra_col = find(EXTRA_DESCRIPTION_COLUMNS)
    out_col, in_col = find(OUT_COLUMNS), find(IN_COLUMNS)
    signed_col = find(SIGNED_COLUMNS)

    two_columns = out_col is not None and in_col is not None
    if date_col is None or desc_col is None or not (two_columns or signed_col is not None):
        raise BankCsvError(HEADER_ERROR)

    result = []
    for row_no, row in enumerate(rows[1:], start=2):
        if not any(value.strip() for value in row):
            continue  # 末尾の空行などは飛ばす

        try:
            entry_date = parse_date(_cell(row, date_col))
            if two_columns:
                out_amount = parse_amount(_cell(row, out_col))
                in_amount = parse_amount(_cell(row, in_col))
            else:
                signed = parse_amount(_cell(row, signed_col))
                out_amount, in_amount = max(-signed, 0), max(signed, 0)
        except ValueError as e:
            raise BankCsvError(f"{row_no}行目の日付または金額を読み取れません") from e

        if out_amount > 0 and in_amount == 0:
            direction, amount = "out", out_amount
        elif in_amount > 0 and out_amount == 0:
            direction, amount = "in", in_amount
        else:
            raise BankCsvError(f"{row_no}行目は出金か入金のどちらか一方を入力してください")

        parts = [_cell(row, desc_col).strip(), _cell(row, extra_col).strip()]
        description = " ".join(p for p in parts if p)

        result.append(BankRow(entry_date, description, direction, amount))

    # 新しい順・古い順のどちらのCSVでも、日付の古い順に並べる（同じ日の順番は保つ）
    return sorted(result, key=lambda r: r.entry_date)
