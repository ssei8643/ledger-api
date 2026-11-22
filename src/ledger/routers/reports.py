from fastapi import APIRouter

from ledger.deps import DbSession
from ledger.schemas import FinancialStatements, MonthlySummary, TrialBalance
from ledger.services import reports

router = APIRouter(tags=["帳簿・財務諸表"])


@router.get("/trial-balance", response_model=TrialBalance)
def get_trial_balance(db: DbSession):
    return reports.trial_balance(db)


@router.get("/financial-statements", response_model=FinancialStatements)
def get_financial_statements(db: DbSession):
    return reports.financial_statements(db)


@router.get("/monthly-summary", response_model=list[MonthlySummary])
def get_monthly_summary(db: DbSession):
    return reports.monthly_summary(db)
