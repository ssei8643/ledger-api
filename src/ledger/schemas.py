"""APIのリクエスト・レスポンスの形式（Pydanticのモデル）"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from ledger.limits import DESCRIPTION_MAX_LENGTH

# 仕訳の摘要：前後の空白を取り除いたうえで、1文字以上・DBの列の長さ以内
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=DESCRIPTION_MAX_LENGTH)
]


# ===== 勘定科目 =====
class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    category: str


# ===== 仕訳 =====
class JournalLineIn(BaseModel):
    account: str
    side: Literal["debit", "credit"]
    amount: int = Field(gt=0)


class JournalEntryCreate(BaseModel):
    entry_date: date
    description: Description
    lines: list[JournalLineIn] = Field(min_length=2)

    @model_validator(mode="after")
    def check_balanced(self):
        debit = sum(line.amount for line in self.lines if line.side == "debit")
        credit = sum(line.amount for line in self.lines if line.side == "credit")
        if debit != credit:
            raise ValueError(f"借方合計 {debit} と貸方合計 {credit} が一致しません")

        # 同じ科目を借方と貸方の両方に使う仕訳は、打ち消し合うだけで意味がない
        debit_accounts = {line.account for line in self.lines if line.side == "debit"}
        credit_accounts = {line.account for line in self.lines if line.side == "credit"}
        same = sorted(debit_accounts & credit_accounts)
        if same:
            raise ValueError(
                f"同じ勘定科目を借方と貸方の両方に使うことはできません: {', '.join(same)}"
            )
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


# ===== 取消 =====
class ReverseRequest(BaseModel):
    entry_date: date
    reason: str = Field(min_length=1, max_length=100)


# ===== 試算表 =====
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


# ===== 総勘定元帳 =====
class LedgerRow(BaseModel):
    entry_id: int
    entry_date: date
    description: str
    debit: int
    credit: int
    balance: int


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


# ===== テンプレート =====
class TemplateLine(BaseModel):
    account: str
    side: Literal["debit", "credit"]


class JournalTemplate(BaseModel):
    name: str
    description: str
    lines: list[TemplateLine]


# ===== 月別 =====
class MonthlySummary(BaseModel):
    month: str
    revenue: int
    expense: int
    net_income: int


# ===== 銀行明細CSVの取り込み =====
class BankImportRequest(BaseModel):
    csv_text: str


class BankDraft(BaseModel):
    import_key: str
    entry_date: date
    description: Description
    direction: Literal["in", "out"]
    amount: int = Field(gt=0)
    account: str | None = None
    # 誰が推測した科目か（"rule"：キーワードのルール、"ai"：AI、None：推測なし）
    suggested_by: Literal["rule", "ai"] | None = None
    already_imported: bool = False


class BankImportCommit(BaseModel):
    drafts: list[BankDraft] = Field(min_length=1)


# ===== 共通 =====
class CreatedCount(BaseModel):
    """まとめて登録した件数"""

    created: int
