"""勘定科目"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledger.chart_of_accounts import CATEGORY_ORDER
from ledger.errors import RuleViolationError
from ledger.models import Account


def list_accounts(db: Session) -> list[Account]:
    accounts = db.scalars(select(Account)).all()
    return sorted(accounts, key=lambda a: (CATEGORY_ORDER.index(a.category), a.name))


def ensure_accounts_exist(db: Session, names: Iterable[str]) -> None:
    """未登録の勘定科目が含まれていれば RuleViolationError を投げる"""
    wanted = set(names)
    known = set(db.scalars(select(Account.name).where(Account.name.in_(wanted))))
    unknown = sorted(wanted - known)
    if unknown:
        raise RuleViolationError(f"未登録の勘定科目です: {', '.join(unknown)}")
