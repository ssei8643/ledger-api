"""帳簿・財務諸表の集計（試算表・総勘定元帳・損益計算書・貸借対照表・月別集計）"""

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ledger.chart_of_accounts import CATEGORY_NORMAL_SIDE, CATEGORY_ORDER
from ledger.errors import NotFoundError
from ledger.models import Account, JournalEntry, JournalLine
from ledger.schemas import (
    BalanceSheet,
    FinancialStatements,
    IncomeStatement,
    LedgerRow,
    MonthlySummary,
    StatementItem,
    TrialBalance,
    TrialBalanceRow,
)

# 科目ごとの借方・貸方の合計を求める式
DEBIT_SUM = func.sum(case((JournalLine.side == "debit", JournalLine.amount), else_=0))
CREDIT_SUM = func.sum(case((JournalLine.side == "credit", JournalLine.amount), else_=0))


# ===== 合計残高試算表 =====
def trial_balance(db: Session) -> TrialBalance:
    stmt = (
        select(JournalLine.account, Account.category, Account.normal_side, DEBIT_SUM, CREDIT_SUM)
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
        is_balanced=(debit_total == credit_total and debit_balance_total == credit_balance_total),
        warning_count=sum(1 for r in rows if r.warning),
    )


# ===== 総勘定元帳 =====
def account_ledger(db: Session, account_name: str) -> list[LedgerRow]:
    account = db.get(Account, account_name)
    if account is None:
        raise NotFoundError("勘定科目が見つかりません")

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
def financial_statements(db: Session) -> FinancialStatements:
    stmt = (
        select(JournalLine.account, Account.category, DEBIT_SUM, CREDIT_SUM)
        .join(Account, Account.name == JournalLine.account)
        .group_by(JournalLine.account, Account.category)
        .order_by(JournalLine.account)
    )

    # 科目ごとの残高を、分類の本来の側を正として計算し、分類ごとにまとめる
    # （減価償却累計額などの評価勘定はマイナスになり、資産の合計から差し引かれる）
    groups: dict[str, list[StatementItem]] = {category: [] for category in CATEGORY_ORDER}
    for account, category, debit, credit in db.execute(stmt).all():
        if CATEGORY_NORMAL_SIDE[category] == "debit":
            amount = debit - credit
        else:
            amount = credit - debit
        if amount != 0:
            groups[category].append(StatementItem(account=account, amount=amount))

    def total(items: list[StatementItem]) -> int:
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


# ===== 月別の収益・費用 =====
def monthly_summary(db: Session) -> list[MonthlySummary]:
    # データベースでは日付ごとに集計し、月へのまとめはPythonで行う。
    # （日付を文字列にして切り出す方法は、SQLiteとPostgreSQLで書き方や結果が変わるため）
    stmt = (
        select(
            JournalEntry.entry_date,
            Account.category,
            JournalLine.side,
            func.sum(JournalLine.amount),
        )
        .select_from(JournalLine)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .join(Account, Account.name == JournalLine.account)
        .where(Account.category.in_(["収益", "費用"]))
        .group_by(JournalEntry.entry_date, Account.category, JournalLine.side)
    )

    totals: dict[str, dict[str, int]] = {}
    for entry_date, category, side, amount in db.execute(stmt).all():
        t = totals.setdefault(entry_date.strftime("%Y-%m"), {"revenue": 0, "expense": 0})
        if category == "収益":
            t["revenue"] += amount if side == "credit" else -amount
        else:
            t["expense"] += amount if side == "debit" else -amount

    return [
        MonthlySummary(
            month=month,
            revenue=t["revenue"],
            expense=t["expense"],
            net_income=t["revenue"] - t["expense"],
        )
        for month, t in sorted(totals.items())
    ]
