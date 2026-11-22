"""テーブルの定義と、保存の直前に必ず行うチェック"""

from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, event
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from ledger.db import Base


class Account(Base):
    """勘定科目"""

    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("normal_side IN ('debit', 'credit')", name="ck_normal_side"),)

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    category: Mapped[str] = mapped_column(String(10))
    # 残高が本来どちら側に出るか（分類の既定値を、科目ごとに上書きできる）
    normal_side: Mapped[str] = mapped_column(String(6))


class JournalEntry(Base):
    """仕訳本体"""

    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(200))
    reverses_id: Mapped[int | None] = mapped_column(
        ForeignKey("journal_entries.id"), unique=True, default=None
    )
    import_key: Mapped[str | None] = mapped_column(String(64), unique=True, default=None)
    lines: Mapped[list["JournalLine"]] = relationship(back_populates="entry")


class JournalLine(Base):
    """仕訳明細"""

    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_amount_positive"),
        CheckConstraint("side IN ('debit', 'credit')", name="ck_side"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"))
    account: Mapped[str] = mapped_column(String(50), ForeignKey("accounts.name"))
    side: Mapped[str] = mapped_column(String(6))
    amount: Mapped[int]
    entry: Mapped[JournalEntry] = relationship(back_populates="lines")


# ===== 貸借一致のチェック（すべての保存経路で必ず通る） =====
class UnbalancedEntryError(ValueError):
    """貸借が一致しない仕訳を保存しようとしたときのエラー"""


def ensure_balanced(entry: JournalEntry) -> None:
    debit = sum(line.amount for line in entry.lines if line.side == "debit")
    credit = sum(line.amount for line in entry.lines if line.side == "credit")
    if len(entry.lines) < 2 or debit != credit:
        raise UnbalancedEntryError(
            f"貸借が一致しない仕訳は保存できません（借方 {debit}／貸方 {credit}）"
        )


@event.listens_for(Session, "before_flush")
def check_entries_before_flush(session, flush_context, instances):
    # APIのバリデーションを通らない経路（取消・CSV取り込みなど）も含め、
    # データベースに書き込む直前に、追加・変更された仕訳の貸借を確認する
    entries = set()
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, JournalEntry):
            entries.add(obj)
        elif isinstance(obj, JournalLine) and obj.entry is not None:
            entries.add(obj.entry)
    for entry in entries:
        ensure_balanced(entry)
