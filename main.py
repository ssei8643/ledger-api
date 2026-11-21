import os
import csv
import hashlib
import io
import unicodedata

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from datetime import date
from typing import Literal
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import CheckConstraint, Date, ForeignKey, String, case, cast, create_engine, event, func, select
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


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    # SQLiteは外部キー制約を既定では検査しないので、接続するたびに有効にする
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


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
    ("減価償却費", "費用"),
    ("貸倒引当金繰入額", "費用"),
    # 評価勘定：分類は資産だが、残高は貸方に出る（3つ目の値で残高の向きを上書き）
    ("減価償却累計額", "資産", "credit"),
    ("貸倒引当金", "資産", "credit"),
]


class Account(Base):
    """勘定科目"""
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("normal_side IN ('debit', 'credit')", name="ck_normal_side"),
    )

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    category: Mapped[str] = mapped_column(String(10))
    # 残高が本来どちら側に出るか（分類の既定値を、科目ごとに上書きできる）
    normal_side: Mapped[str] = mapped_column(String(6))


# ===== 仕訳 =====
class JournalEntry(Base):
    """仕訳本体"""
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(200))
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"), unique=True, default=None)
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
    debit = sum(l.amount for l in entry.lines if l.side == "debit")
    credit = sum(l.amount for l in entry.lines if l.side == "credit")
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


def seed_accounts(db: Session) -> None:
    """初期の勘定科目を登録（登録済みのものはスキップ）"""
    existing = set(db.scalars(select(Account.name)))
    for name, category, *override in DEFAULT_ACCOUNTS:
        if name not in existing:
            normal_side = override[0] if override else CATEGORY_NORMAL_SIDE[category]
            db.add(Account(name=name, category=category, normal_side=normal_side))
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
    reverses_id: int | None = None


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
    # 合計（各科目の借方・貸方の合計額を足したもの）
    debit_total: int
    credit_total: int
    # 残高（各科目の借方残高・貸方残高を足したもの）
    debit_balance_total: int
    credit_balance_total: int
    is_balanced: bool
    warning_count: int


# ===== アプリとAPI =====
app = FastAPI()

allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
if os.getenv("FRONTEND_ORIGIN"):
    allowed_origins.append(os.getenv("FRONTEND_ORIGIN"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        select(JournalLine.account, Account.category, Account.normal_side, debit_sum, credit_sum)
        .join(Account, Account.name == JournalLine.account)
        .group_by(JournalLine.account, Account.category, Account.normal_side)
    )

    rows = []
    for account, category, normal_side, debit, credit in db.execute(stmt).all():
        diff = debit - credit

        # 本来と逆側に残高が出ていれば警告（科目ごとの残高の向きで判定）
        warning = None
        if normal_side == "debit" and diff < 0:
            warning = f"{account}が貸方残高になっています（通常は借方残高）"
        elif normal_side == "credit" and diff > 0:
            warning = f"{account}が借方残高になっています（通常は貸方残高）"

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
    debit_balance_total = sum(r.debit_balance for r in rows)
    credit_balance_total = sum(r.credit_balance for r in rows)
    return TrialBalance(
        rows=rows,
        debit_total=debit_total,
        credit_total=credit_total,
        debit_balance_total=debit_balance_total,
        credit_balance_total=credit_balance_total,
        is_balanced=(
            debit_total == credit_total
            and debit_balance_total == credit_balance_total
        ),
        warning_count=sum(1 for r in rows if r.warning),
    )
    
    
# ===== 訂正仕訳（取消） =====
class ReverseRequest(BaseModel):
    entry_date: date
    reason: str = Field(min_length=1, max_length=100)


@app.post("/journal-entries/{entry_id}/reverse", status_code=201, response_model=JournalEntryOut)
def reverse_journal_entry(entry_id: int, payload: ReverseRequest, db: Session = Depends(get_db)):
    original = db.get(JournalEntry, entry_id)
    if original is None:
        raise HTTPException(status_code=404, detail="仕訳が見つかりません")
    if original.reverses_id is not None:
        raise HTTPException(status_code=422, detail="取消仕訳をさらに取り消すことはできません")

    already = db.scalar(select(JournalEntry.id).where(JournalEntry.reverses_id == entry_id))
    if already is not None:
        raise HTTPException(status_code=409, detail=f"この仕訳はすでに仕訳#{already}で取り消されています")

    # 借方と貸方を入れ替えた仕訳を作る
    opposite = {"debit": "credit", "credit": "debit"}
    reversal = JournalEntry(
        entry_date=payload.entry_date,
        description=f"【取消】仕訳#{entry_id}：{payload.reason}",
        reverses_id=entry_id,
        lines=[
            JournalLine(account=l.account, side=opposite[l.side], amount=l.amount)
            for l in original.lines
        ],
    )
    db.add(reversal)
    db.commit()
    db.refresh(reversal)
    return reversal

# ===== 総勘定元帳 =====
class LedgerRow(BaseModel):
    entry_id: int
    entry_date: date
    description: str
    debit: int
    credit: int
    balance: int


@app.get("/accounts/{account_name}/ledger", response_model=list[LedgerRow])
def get_ledger(account_name: str, db: Session = Depends(get_db)):
    # 科目が存在しなければ404
    account = db.get(Account, account_name)
    if account is None:
        raise HTTPException(status_code=404, detail="勘定科目が見つかりません")

    # この科目の明細を、仕訳の日付順に取得（本体と明細を結合）
    stmt = (
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .where(JournalLine.account == account_name)
        .order_by(JournalEntry.entry_date, JournalEntry.id)
    )

    # 1行ずつ残高を計算（科目ごとの残高の向きによって増減の向きが変わる）
    normal_side = account.normal_side
    balance = 0
    rows = []
    for line, entry in db.execute(stmt).all():
        debit = line.amount if line.side == "debit" else 0
        credit = line.amount if line.side == "credit" else 0
        if normal_side == "debit":
            balance += debit - credit
        else:
            balance += credit - debit
        rows.append(
            LedgerRow(
                entry_id=entry.id,
                entry_date=entry.entry_date,
                description=entry.description,
                debit=debit,
                credit=credit,
                balance=balance,
            )
        )
    return rows

# ===== 損益計算書・貸借対照表 =====
class StatementItem(BaseModel):
    account: str
    amount: int


class IncomeStatement(BaseModel):
    revenues: list[StatementItem]
    expenses: list[StatementItem]
    total_revenue: int
    total_expense: int
    net_income: int


class BalanceSheet(BaseModel):
    assets: list[StatementItem]
    liabilities: list[StatementItem]
    equity: list[StatementItem]
    net_income: int
    total_assets: int
    total_liabilities_and_equity: int
    is_balanced: bool


class FinancialStatements(BaseModel):
    income_statement: IncomeStatement
    balance_sheet: BalanceSheet


@app.get("/financial-statements", response_model=FinancialStatements)
def get_financial_statements(db: Session = Depends(get_db)):
    debit_sum = func.sum(case((JournalLine.side == "debit", JournalLine.amount), else_=0))
    credit_sum = func.sum(case((JournalLine.side == "credit", JournalLine.amount), else_=0))
    stmt = (
        select(JournalLine.account, Account.category, debit_sum, credit_sum)
        .join(Account, Account.name == JournalLine.account)
        .group_by(JournalLine.account, Account.category)
        .order_by(JournalLine.account)
    )

    # 科目ごとの残高を、分類の本来の側を正として計算し、分類ごとにまとめる
    # （減価償却累計額などの評価勘定はマイナスになり、資産の合計から差し引かれる）
    groups = {category: [] for category in CATEGORY_ORDER}
    for account, category, debit, credit in db.execute(stmt).all():
        if CATEGORY_NORMAL_SIDE[category] == "debit":
            amount = debit - credit
        else:
            amount = credit - debit
        if amount != 0:
            groups[category].append(StatementItem(account=account, amount=amount))

    def total(items):
        return sum(i.amount for i in items)

    # 損益計算書：収益 − 費用 ＝ 当期純利益
    total_revenue = total(groups["収益"])
    total_expense = total(groups["費用"])
    net_income = total_revenue - total_expense

    # 貸借対照表：資産 ＝ 負債 ＋ 純資産 ＋ 当期純利益
    total_assets = total(groups["資産"])
    total_liabilities_and_equity = total(groups["負債"]) + total(groups["純資産"]) + net_income

    return FinancialStatements(
        income_statement=IncomeStatement(
            revenues=groups["収益"],
            expenses=groups["費用"],
            total_revenue=total_revenue,
            total_expense=total_expense,
            net_income=net_income,
        ),
        balance_sheet=BalanceSheet(
            assets=groups["資産"],
            liabilities=groups["負債"],
            equity=groups["純資産"],
            net_income=net_income,
            total_assets=total_assets,
            total_liabilities_and_equity=total_liabilities_and_equity,
            is_balanced=total_assets == total_liabilities_and_equity,
        ),
    )

# ===== サンプルデータ =====
# 個人事業主（Webデザイナー）の1か月分の取引
SAMPLE_ENTRIES = [
    ("2026-11-01", "開始仕訳（期首残高）",
     [("現金", "debit", 50000), ("普通預金", "debit", 300000), ("元入金", "credit", 350000)]),
    ("2026-11-03", "A社 Webサイト制作（掛け）",
     [("売掛金", "debit", 110000), ("売上高", "credit", 110000)]),
    ("2026-11-05", "コピー用紙購入",
     [("消耗品費", "debit", 1100), ("現金", "credit", 1100)]),
    ("2026-11-07", "打ち合わせの電車代",
     [("旅費交通費", "debit", 640), ("現金", "credit", 640)]),
    ("2026-11-10", "スマホ代",
     [("通信費", "debit", 5500), ("普通預金", "credit", 5500)]),
    ("2026-11-12", "B社 バナー制作（振込）",
     [("普通預金", "debit", 55000), ("売上高", "credit", 55000)]),
    ("2026-11-15", "A社 売掛金入金（振込手数料差引）",
     [("普通預金", "debit", 109340), ("支払手数料", "debit", 660), ("売掛金", "credit", 110000)]),
    ("2026-11-18", "販売用素材の仕入（掛け）",
     [("仕入高", "debit", 22000), ("買掛金", "credit", 22000)]),
    ("2026-11-20", "生活費の引き出し",
     [("事業主貸", "debit", 30000), ("普通預金", "credit", 30000)]),
    ("2026-11-22", "打ち合わせの交通費",
     [("旅費交通費", "debit", 1280), ("現金", "credit", 1280)]),
    ("2026-11-25", "買掛金の支払い",
     [("買掛金", "debit", 22000), ("普通預金", "credit", 22000)]),
    ("2026-11-28", "C社 ロゴ制作（掛け）",
     [("売掛金", "debit", 77000), ("売上高", "credit", 77000)]),
    ("2026-11-30", "インターネット料金",
     [("通信費", "debit", 4400), ("普通預金", "credit", 4400)]),
]


@app.post("/demo-data", status_code=201)
def load_demo_data(db: Session = Depends(get_db)):
    # すでに仕訳がある場合は、実データと混ざらないよう読み込まない
    if db.scalar(select(func.count(JournalEntry.id))) > 0:
        raise HTTPException(
            status_code=409,
            detail="すでに仕訳が登録されているため、サンプルデータは読み込めません",
        )

    for entry_date, description, lines in SAMPLE_ENTRIES:
        # サンプルデータも通常の入力と同じルール（貸借一致など）で検証する
        payload = JournalEntryCreate(
            entry_date=entry_date,
            description=description,
            lines=[{"account": a, "side": s, "amount": amt} for a, s, amt in lines],
        )
        db.add(
            JournalEntry(
                entry_date=payload.entry_date,
                description=payload.description,
                lines=[
                    JournalLine(account=l.account, side=l.side, amount=l.amount)
                    for l in payload.lines
                ],
            )
        )
    db.commit()  # 13件をまとめて1つのトランザクションで保存
    return {"created": len(SAMPLE_ENTRIES)}


# ===== よく使う仕訳のテンプレート =====
class TemplateLine(BaseModel):
    account: str
    side: Literal["debit", "credit"]


class JournalTemplate(BaseModel):
    name: str
    description: str
    lines: list[TemplateLine]


def make_template(name: str, description: str, debit: str, credit: str) -> JournalTemplate:
    return JournalTemplate(
        name=name,
        description=description,
        lines=[
            TemplateLine(account=debit, side="debit"),
            TemplateLine(account=credit, side="credit"),
        ],
    )


TEMPLATES = [
    make_template("交通費（現金払い）", "交通費", "旅費交通費", "現金"),
    make_template("消耗品の購入（現金払い）", "消耗品購入", "消耗品費", "現金"),
    make_template("通信費（口座引き落とし）", "通信費", "通信費", "普通預金"),
    make_template("売上（掛け）", "売上", "売掛金", "売上高"),
    make_template("売掛金の入金（振込）", "売掛金入金", "普通預金", "売掛金"),
    make_template("生活費の引き出し", "生活費の引き出し", "事業主貸", "普通預金"),
]


@app.get("/templates", response_model=list[JournalTemplate])
def list_templates():
    return TEMPLATES

# ===== 月別の収益・費用 =====
class MonthlySummary(BaseModel):
    month: str
    revenue: int
    expense: int
    net_income: int


@app.get("/monthly-summary", response_model=list[MonthlySummary])
def get_monthly_summary(db: Session = Depends(get_db)):
    # 日付 "2026-11-05" の先頭7文字 "2026-11" を「月」として使う
    month = func.substr(cast(JournalEntry.entry_date, String), 1, 7)
    stmt = (
        select(month, Account.category, JournalLine.side, func.sum(JournalLine.amount))
        .select_from(JournalLine)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .join(Account, Account.name == JournalLine.account)
        .where(Account.category.in_(["収益", "費用"]))
        .group_by(month, Account.category, JournalLine.side)
        .order_by(month)
    )

    totals: dict[str, dict[str, int]] = {}
    for m, category, side, amount in db.execute(stmt).all():
        t = totals.setdefault(m, {"revenue": 0, "expense": 0})
        if category == "収益":
            t["revenue"] += amount if side == "credit" else -amount
        else:
            t["expense"] += amount if side == "debit" else -amount

    return [
        MonthlySummary(
            month=m,
            revenue=t["revenue"],
            expense=t["expense"],
            net_income=t["revenue"] - t["expense"],
        )
        for m, t in totals.items()
    ]

# ===== 銀行明細CSVの取り込み =====
BANK_ACCOUNT = "普通預金"

# 摘要に含まれるキーワードから勘定科目を推測するルール
OUT_RULES = [
    ("手数料", "支払手数料"),
    ("ドコモ", "通信費"),
    ("ソフトバンク", "通信費"),
    ("NTT", "通信費"),
    ("JR", "旅費交通費"),
    ("SUICA", "旅費交通費"),
    ("AMAZON", "消耗品費"),
    ("アマゾン", "消耗品費"),
    ("ATM", "事業主貸"),
]
IN_RULES = [
    ("フリコミ", "売掛金"),
    ("振込", "売掛金"),
]


def suggest_account(description: str, direction: str) -> str | None:
    # 半角カナ・全角英数字を揃えてから比較する（例：ﾌﾘｺﾐ → フリコミ）
    text = unicodedata.normalize("NFKC", description).upper()
    rules = OUT_RULES if direction == "out" else IN_RULES
    for keyword, account in rules:
        if keyword in text:
            return account
    return None


def to_int(value: str | None) -> int:
    value = (value or "").replace(",", "").strip()
    return int(value) if value else 0


class BankImportRequest(BaseModel):
    csv_text: str


class BankDraft(BaseModel):
    import_key: str
    entry_date: date
    description: str
    direction: Literal["in", "out"]
    amount: int = Field(gt=0)
    account: str | None = None
    already_imported: bool = False


class BankImportCommit(BaseModel):
    drafts: list[BankDraft] = Field(min_length=1)


@app.post("/bank-import/preview", response_model=list[BankDraft])
def preview_bank_import(payload: BankImportRequest, db: Session = Depends(get_db)):
    reader = csv.DictReader(io.StringIO(payload.csv_text.lstrip("\ufeff")))
    if reader.fieldnames is None or not {"日付", "摘要", "出金", "入金"} <= set(reader.fieldnames):
        raise HTTPException(status_code=422, detail="CSVの1行目は「日付,摘要,出金,入金」にしてください")

    drafts = []
    seen: dict[str, int] = {}
    for row_no, row in enumerate(reader, start=2):
        try:
            entry_date = date.fromisoformat((row["日付"] or "").strip().replace("/", "-"))
            out_amount = to_int(row["出金"])
            in_amount = to_int(row["入金"])
        except ValueError:
            raise HTTPException(status_code=422, detail=f"{row_no}行目の日付または金額を読み取れません")

        if out_amount > 0 and in_amount == 0:
            direction, amount = "out", out_amount
        elif in_amount > 0 and out_amount == 0:
            direction, amount = "in", in_amount
        else:
            raise HTTPException(status_code=422, detail=f"{row_no}行目は出金か入金のどちらか一方を入力してください")

        description = (row["摘要"] or "").strip()

        # 同じ内容の明細が同じファイルに複数ある場合も区別できるよう、出現回数を含めてキーを作る
        base = f"{entry_date}|{description}|{direction}|{amount}"
        seen[base] = seen.get(base, 0) + 1
        import_key = hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest()

        drafts.append(
            BankDraft(
                import_key=import_key,
                entry_date=entry_date,
                description=description,
                direction=direction,
                amount=amount,
                account=suggest_account(description, direction),
            )
        )

    # すでに取り込み済みの明細に印をつける
    keys = [d.import_key for d in drafts]
    existing = set(db.scalars(select(JournalEntry.import_key).where(JournalEntry.import_key.in_(keys))))
    for d in drafts:
        d.already_imported = d.import_key in existing
    return drafts


@app.post("/bank-import", status_code=201)
def commit_bank_import(payload: BankImportCommit, db: Session = Depends(get_db)):
    if any(d.account is None for d in payload.drafts):
        raise HTTPException(status_code=422, detail="勘定科目が選ばれていない明細があります")

    names = {d.account for d in payload.drafts if d.account}
    known = set(db.scalars(select(Account.name).where(Account.name.in_(names))))
    unknown = sorted(names - known)
    if unknown:
        raise HTTPException(status_code=422, detail=f"未登録の勘定科目です: {', '.join(unknown)}")

    keys = [d.import_key for d in payload.drafts]
    if db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.import_key.in_(keys))) > 0:
        raise HTTPException(status_code=409, detail="すでに取り込み済みの明細が含まれています")

    # 出金：費用など（借方）／普通預金（貸方）、入金：普通預金（借方）／売掛金など（貸方）
    for d in payload.drafts:
        if d.direction == "out":
            lines = [
                JournalLine(account=d.account, side="debit", amount=d.amount),
                JournalLine(account=BANK_ACCOUNT, side="credit", amount=d.amount),
            ]
        else:
            lines = [
                JournalLine(account=BANK_ACCOUNT, side="debit", amount=d.amount),
                JournalLine(account=d.account, side="credit", amount=d.amount),
            ]
        db.add(
            JournalEntry(
                entry_date=d.entry_date,
                description=d.description,
                import_key=d.import_key,
                lines=lines,
            )
        )

    try:
        db.commit()  # まとめて1つのトランザクションで保存
    except IntegrityError:
        # APIの確認をすり抜けた重複も、データベースの一意制約で防ぐ
        db.rollback()
        raise HTTPException(status_code=409, detail="すでに取り込み済みの明細が含まれています")
    return {"created": len(payload.drafts)}

# ===== デモ環境：起動時にデータが空ならサンプルデータを読み込む =====
if os.getenv("DEMO_MODE") == "1":
    with SessionLocal() as _db:
        if _db.scalar(select(func.count(JournalEntry.id))) == 0:
            load_demo_data(_db)