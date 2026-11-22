"""複数のテストファイルで使うテストデータ"""

from pathlib import Path

# ===== 仕訳の入力データ =====
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


OPENING_ENTRY = {
    "entry_date": "2026-10-01",
    "description": "開始仕訳（期首残高）",
    "lines": [
        {"account": "現金", "side": "debit", "amount": 50000},
        {"account": "売掛金", "side": "debit", "amount": 11000},
        {"account": "元入金", "side": "credit", "amount": 61000},
    ],
}


DEPRECIATION_ENTRY = {
    "entry_date": "2026-12-31",
    "description": "減価償却（間接法）",
    "lines": [
        {"account": "減価償却費", "side": "debit", "amount": 5000},
        {"account": "減価償却累計額", "side": "credit", "amount": 5000},
    ],
}


SALES_ENTRY = {
    "entry_date": "2026-11-05",
    "description": "B社へ売上（掛け）",
    "lines": [
        {"account": "売掛金", "side": "debit", "amount": 33000},
        {"account": "売上高", "side": "credit", "amount": 33000},
    ],
}


# ===== samples/ フォルダのサンプルCSV（各銀行の形式を参考に作った架空のデータ） =====
SAMPLES_DIR = Path(__file__).parent.parent / "samples"


def read_sample(name: str) -> str:
    # 画面と同じく、UTF-8で読めなければShift_JISで読み直す
    raw = (SAMPLES_DIR / name).read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("shift_jis")
