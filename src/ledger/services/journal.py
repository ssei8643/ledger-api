"""仕訳の登録・取得・取消"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ledger.errors import ConflictError, NotFoundError, RuleViolationError
from ledger.models import JournalEntry, JournalLine
from ledger.schemas import JournalEntryCreate, ReverseRequest
from ledger.services.accounts import ensure_accounts_exist

OPPOSITE_SIDE = {"debit": "credit", "credit": "debit"}


def build_entry(payload: JournalEntryCreate) -> JournalEntry:
    """検証済みの入力から、本体と明細を持つ仕訳を作る（保存はしない）"""
    return JournalEntry(
        entry_date=payload.entry_date,
        description=payload.description,
        lines=[
            JournalLine(account=line.account, side=line.side, amount=line.amount)
            for line in payload.lines
        ],
    )


def create_entry(db: Session, payload: JournalEntryCreate) -> JournalEntry:
    ensure_accounts_exist(db, (line.account for line in payload.lines))
    entry = build_entry(payload)
    db.add(entry)
    db.commit()  # 本体と明細を1つのトランザクションで保存
    db.refresh(entry)
    return entry


def list_entries(db: Session) -> Sequence[JournalEntry]:
    stmt = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
    )
    return db.scalars(stmt).all()


def get_entry(db: Session, entry_id: int) -> JournalEntry:
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise NotFoundError("仕訳が見つかりません")
    return entry


def reverse_entry(db: Session, entry_id: int, payload: ReverseRequest) -> JournalEntry:
    """借方と貸方を入れ替えた仕訳を作って、元の仕訳を取り消す（元の仕訳は消さない）"""
    original = get_entry(db, entry_id)
    if original.reverses_id is not None:
        raise RuleViolationError("取消仕訳をさらに取り消すことはできません")

    already = db.scalar(select(JournalEntry.id).where(JournalEntry.reverses_id == entry_id))
    if already is not None:
        raise ConflictError(f"この仕訳はすでに仕訳#{already}で取り消されています")

    reversal = JournalEntry(
        entry_date=payload.entry_date,
        description=f"【取消】仕訳#{entry_id}：{payload.reason}",
        reverses_id=entry_id,
        lines=[
            JournalLine(account=line.account, side=OPPOSITE_SIDE[line.side], amount=line.amount)
            for line in original.lines
        ],
    )
    db.add(reversal)
    try:
        db.commit()
    except IntegrityError:
        # 同じ仕訳への取消が同時に届き、確認のあとで先にもう一方が保存された場合。
        # reverses_id の一意制約で弾かれるので、500ではなく409として返す
        db.rollback()
        raise ConflictError("この仕訳はすでに取り消されています") from None
    db.refresh(reversal)
    return reversal
