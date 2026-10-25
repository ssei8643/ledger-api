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

# ===== データベース接続 =====
engine = create_engine("sqlite:///./ledger.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


# ===== 勘定科目マスタ =====
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
]


class Account(Base):
    """勘定科目"""
    __tablename__ = "accounts"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    category: Mapped[str] = mapped_column(String(10))


# ===== 仕訳 =====
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


def seed_accounts(db: Session) -> None:
    """初期の勘定科目を登録（登録済みのものはスキップ）"""
    existing = set(db.scalars(select(Account.name)))
    for name, category in DEFAULT_ACCOUNTS:
        if name not in existing:
            db.add(Account(name=name, category=category))
    db.commit()


Base.metadata.create_all(engine)
with SessionLocal() as _db:
    seed_accounts(_db)


# ===== リクエスト・レスポンスの形式 =====
class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    category: str


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


class TrialBalanceRow(BaseModel):
    account: str
    category: str
    debit_total: int
    credit_total: int
    debit_balance: int
    credit_balance: int
    warning: str | None = None


class TrialBalance(BaseModel):
    rows: list[TrialBalanceRow]
    debit_total: int
    credit_total: int
    is_balanced: bool
    warning_count: int


# ===== アプリとAPI =====
app = FastAPI()


def get_db():
    with SessionLocal() as db:
        yield db


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    accounts = db.scalars(select(Account)).all()
    return sorted(accounts, key=lambda a: (CATEGORY_ORDER.index(a.category), a.name))


@app.post("/journal-entries", status_code=201, response_model=JournalEntryOut)
def create_journal_entry(payload: JournalEntryCreate, db: Session = Depends(get_db)):
    # 未登録の勘定科目が含まれていないか確認
    names = {l.account for l in payload.lines}
    known = set(db.scalars(select(Account.name).where(Account.name.in_(names))))
    unknown = sorted(names - known)
    if unknown:
        raise HTTPException(status_code=422, detail=f"未登録の勘定科目です: {', '.join(unknown)}")

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


@app.get("/trial-balance", response_model=TrialBalance)
def get_trial_balance(db: Session = Depends(get_db)):
    debit_sum = func.sum(case((JournalLine.side == "debit", JournalLine.amount), else_=0))
    credit_sum = func.sum(case((JournalLine.side == "credit", JournalLine.amount), else_=0))
    stmt = (
        select(JournalLine.account, Account.category, debit_sum, credit_sum)
        .join(Account, Account.name == JournalLine.account)
        .group_by(JournalLine.account, Account.category)
    )

    rows = []
    for account, category, debit, credit in db.execute(stmt).all():
        diff = debit - credit
        normal_side = CATEGORY_NORMAL_SIDE[category]

        # 本来と逆側に残高が出ていれば警告
        warning = None
        if normal_side == "debit" and diff < 0:
            warning = f"{category}の科目が貸方残高になっています"
        elif normal_side == "credit" and diff > 0:
            warning = f"{category}の科目が借方残高になっています"

        rows.append(
            TrialBalanceRow(
                account=account,
                category=category,
                debit_total=debit,
                credit_total=credit,
                debit_balance=max(diff, 0),
                credit_balance=max(-diff, 0),
                warning=warning,
            )
        )

    rows.sort(key=lambda r: (CATEGORY_ORDER.index(r.category), r.account))
    debit_total = sum(r.debit_total for r in rows)
    credit_total = sum(r.credit_total for r in rows)
    return TrialBalance(
        rows=rows,
        debit_total=debit_total,
        credit_total=credit_total,
        is_balanced=debit_total == credit_total,
        warning_count=sum(1 for r in rows if r.warning),
    )