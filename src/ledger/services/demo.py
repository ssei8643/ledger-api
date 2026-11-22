"""デモ用のサンプルデータ"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ledger.errors import ConflictError
from ledger.models import JournalEntry
from ledger.schemas import JournalEntryCreate
from ledger.services.journal import build_entry

# 個人事業主（Webデザイナー）の1か月分の取引
SAMPLE_ENTRIES = [
    (
        "2026-11-01",
        "開始仕訳（期首残高）",
        [("現金", "debit", 50000), ("普通預金", "debit", 300000), ("元入金", "credit", 350000)],
    ),
    (
        "2026-11-03",
        "A社 Webサイト制作（掛け）",
        [("売掛金", "debit", 110000), ("売上高", "credit", 110000)],
    ),
    ("2026-11-05", "コピー用紙購入", [("消耗品費", "debit", 1100), ("現金", "credit", 1100)]),
    ("2026-11-07", "打ち合わせの電車代", [("旅費交通費", "debit", 640), ("現金", "credit", 640)]),
    ("2026-11-10", "スマホ代", [("通信費", "debit", 5500), ("普通預金", "credit", 5500)]),
    (
        "2026-11-12",
        "B社 バナー制作（振込）",
        [("普通預金", "debit", 55000), ("売上高", "credit", 55000)],
    ),
    (
        "2026-11-15",
        "A社 売掛金入金（振込手数料差引）",
        [("普通預金", "debit", 109340), ("支払手数料", "debit", 660), ("売掛金", "credit", 110000)],
    ),
    (
        "2026-11-18",
        "販売用素材の仕入（掛け）",
        [("仕入高", "debit", 22000), ("買掛金", "credit", 22000)],
    ),
    (
        "2026-11-20",
        "生活費の引き出し",
        [("事業主貸", "debit", 30000), ("普通預金", "credit", 30000)],
    ),
    ("2026-11-22", "打ち合わせの交通費", [("旅費交通費", "debit", 1280), ("現金", "credit", 1280)]),
    ("2026-11-25", "買掛金の支払い", [("買掛金", "debit", 22000), ("普通預金", "credit", 22000)]),
    (
        "2026-11-28",
        "C社 ロゴ制作（掛け）",
        [("売掛金", "debit", 77000), ("売上高", "credit", 77000)],
    ),
    ("2026-11-30", "インターネット料金", [("通信費", "debit", 4400), ("普通預金", "credit", 4400)]),
]


def has_entries(db: Session) -> bool:
    return db.scalar(select(func.count(JournalEntry.id))) > 0


def load_demo_data(db: Session) -> int:
    """サンプルの仕訳をまとめて登録し、登録した件数を返す"""
    # すでに仕訳がある場合は、実データと混ざらないよう読み込まない
    if has_entries(db):
        raise ConflictError("すでに仕訳が登録されているため、サンプルデータは読み込めません")

    for entry_date, description, lines in SAMPLE_ENTRIES:
        # サンプルデータも通常の入力と同じルール（貸借一致など）で検証する
        payload = JournalEntryCreate.model_validate(
            {
                "entry_date": entry_date,
                "description": description,
                "lines": [{"account": a, "side": s, "amount": amt} for a, s, amt in lines],
            }
        )
        db.add(build_entry(payload))
    db.commit()  # 13件をまとめて1つのトランザクションで保存
    return len(SAMPLE_ENTRIES)


def load_demo_data_if_empty(db: Session) -> None:
    """デモ環境の起動時用：データが空のときだけサンプルデータを読み込む"""
    if not has_entries(db):
        load_demo_data(db)
