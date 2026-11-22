"""勘定科目マスタ（分類・残高の向き・初期データ）"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledger.models import Account

# 分類ごとに、残高が本来どちら側に出るか
CATEGORY_NORMAL_SIDE = {
    "資産": "debit",
    "負債": "credit",
    "純資産": "credit",
    "収益": "credit",
    "費用": "debit",
}
CATEGORY_ORDER = list(CATEGORY_NORMAL_SIDE)

DEFAULT_ACCOUNTS = [
    ("現金", "資産"),
    ("普通預金", "資産"),
    ("売掛金", "資産"),
    ("事業主貸", "資産"),
    ("買掛金", "負債"),
    ("未払金", "負債"),
    ("元入金", "純資産"),
    ("事業主借", "純資産"),
    ("売上高", "収益"),
    ("仕入高", "費用"),
    ("消耗品費", "費用"),
    ("支払手数料", "費用"),
    ("通信費", "費用"),
    ("旅費交通費", "費用"),
    ("減価償却費", "費用"),
    ("貸倒引当金繰入額", "費用"),
    ("会議費", "費用"),
    ("接待交際費", "費用"),
    ("水道光熱費", "費用"),
    ("地代家賃", "費用"),
    ("新聞図書費", "費用"),
    ("雑費", "費用"),
    # 評価勘定：分類は資産だが、残高は貸方に出る（3つ目の値で残高の向きを上書き）
    ("減価償却累計額", "資産", "credit"),
    ("貸倒引当金", "資産", "credit"),
]


def seed_accounts(db: Session) -> None:
    """初期の勘定科目を登録（登録済みのものはスキップ）"""
    existing = set(db.scalars(select(Account.name)))
    for name, category, *override in DEFAULT_ACCOUNTS:
        if name not in existing:
            normal_side = override[0] if override else CATEGORY_NORMAL_SIDE[category]
            db.add(Account(name=name, category=category, normal_side=normal_side))
    db.commit()
