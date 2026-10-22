from datetime import date
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import CheckConstraint, Date, ForeignKey, String, case, create_engine, func, select
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    selectinload,
    sessionmaker,
)

# ===== 数据库连接 =====
engine = create_engine("sqlite:///./ledger.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


# ===== 数据库表 =====
class JournalEntry(Base):
    """仕訳本体"""
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(200))
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
    account: Mapped[str] = mapped_column(String(50))
    side: Mapped[str] = mapped_column(String(6))
    amount: Mapped[int]
    entry: Mapped[JournalEntry] = relationship(back_populates="lines")


Base.metadata.create_all(engine)


# ===== 请求和响应的格式 =====
class JournalLineIn(BaseModel):
    account: str
    side: Literal["debit", "credit"]
    amount: int = Field(gt=0)


class JournalEntryCreate(BaseModel):
    entry_date: date
    description: str
    lines: list[JournalLineIn] = Field(min_length=2)

    @model_validator(mode="after")
    def check_balanced(self):
        debit = sum(l.amount for l in self.lines if l.side == "debit")
        credit = sum(l.amount for l in self.lines if l.side == "credit")
        if debit != credit:
            raise ValueError(f"借方合計 {debit} と貸方合計 {credit} が一致しません")
        return self


class JournalLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    account: str
    side: str
    amount: int


class JournalEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    entry_date: date
    description: str
    lines: list[JournalLineOut]


# ===== 应用和接口 =====
app = FastAPI()


def get_db():
    with SessionLocal() as db:
        yield db


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/journal-entries", status_code=201, response_model=JournalEntryOut)
def create_journal_entry(payload: JournalEntryCreate, db: Session = Depends(get_db)):
    entry = JournalEntry(
        entry_date=payload.entry_date,
        description=payload.description,
        lines=[
            JournalLine(account=l.account, side=l.side, amount=l.amount)
            for l in payload.lines
        ],
    )
    db.add(entry)
    db.commit()  # 本体と明細を1つのトランザクションで保存
    db.refresh(entry)
    return entry


@app.get("/journal-entries", response_model=list[JournalEntryOut])
def list_journal_entries(db: Session = Depends(get_db)):
    stmt = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())
    )
    return db.scalars(stmt).all()


@app.get("/journal-entries/{entry_id}", response_model=JournalEntryOut)
def get_journal_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="仕訳が見つかりません")
    return entry

# ===== 試算表 =====
class TrialBalanceRow(BaseModel):
    account: str
    debit_total: int
    credit_total: int
    debit_balance: int
    credit_balance: int


class TrialBalance(BaseModel):
    rows: list[TrialBalanceRow]
    debit_total: int
    credit_total: int
    is_balanced: bool


@app.get("/trial-balance", response_model=TrialBalance)
def get_trial_balance(db: Session = Depends(get_db)):
    debit_sum = func.sum(case((JournalLine.side == "debit", JournalLine.amount), else_=0))
    credit_sum = func.sum(case((JournalLine.side == "credit", JournalLine.amount), else_=0))
    stmt = (
        select(JournalLine.account, debit_sum, credit_sum)
        .group_by(JournalLine.account)
        .order_by(JournalLine.account)
    )

    rows = []
    for account, debit, credit in db.execute(stmt).all():
        diff = debit - credit
        rows.append(
            TrialBalanceRow(
                account=account,
                debit_total=debit,
                credit_total=credit,
                debit_balance=max(diff, 0),
                credit_balance=max(-diff, 0),
            )
        )

    debit_total = sum(r.debit_total for r in rows)
    credit_total = sum(r.credit_total for r in rows)
    return TrialBalance(
        rows=rows,
        debit_total=debit_total,
        credit_total=credit_total,
        is_balanced=debit_total == credit_total,
    )